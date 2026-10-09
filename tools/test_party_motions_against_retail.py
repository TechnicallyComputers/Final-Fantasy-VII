"""Run generated paired motions through original PSX action/bitstream code."""
import argparse,ctypes,json,struct,math
from pathlib import Path
from inspect_ff7_party import Disc,ROOT,image_data,kernel_sections
from inspect_ff7_animations import decompress_lzs,sections
from inspect_ff7_battle import inspect as battle_evidence
from inspect_ff7_motions import inspect
from test_party_battle_against_retail import VM

class Pose(ctypes.Structure):
    _fields_=[('position',ctypes.c_int16*3),('angle',(ctypes.c_uint16*3)*48)]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    lib=ctypes.CDLL(str(a.library.resolve()))
    for n in('ram','expansion'):getattr(lib,'ff7_test_battle_'+n).restype=ctypes.c_void_p
    lib.ff7_test_battle_hook.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    lib.ff7_motion_decode_frame.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint,ctypes.c_uint,ctypes.POINTER(Pose)]
    ev=inspect(a.disc);assert ev==json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/motion.evidence.json').read_text())
    report=battle_evidence(a.disc);report['sites']+=ev['sites']
    d=Disc(a.disc)
    try:
        images={n:image_data('BATTLE/'+n+'.X',d.read('BATTLE/'+n+'.X'))for n in('BATINI','BATTLE')}
        exe=d.read(next(n for n in d.files if n.startswith('SCUS_')and '/'not in n));kernel=kernel_sections(d.read('INIT/KERNEL.BIN'))
        original=decompress_lzs(d.read('ENEMY6/SEFIROS.LZS'))
    finally:d.reader.close()
    def vm(slot=0,guest=11):
        v=VM(lib,report,images,exe,kernel);v.uc.mem_map(0x1f800000,4096)
        v.write(0x801b0000,original);v.write(0x801636b8+16*slot,bytes([guest]));v.reg(4,slot);v.run(0x800b5c1c)
        return v,0x80103200+0xf000*slot
    def word(v,p):return struct.unpack('<I',v.read(p,4))[0]
    def half(v,p):return struct.unpack('<H',v.read(p,2))[0]
    def pose(v,p,rot):
        return (struct.unpack('<hhh',v.read(p+40,6)),[[x&4095 for x in struct.unpack('<3H',v.read(p+52*j+32,6))]for j in range(rot)])
    def expected(v,model,motion,frame,bank):
        offset=word(v,model+12+4*(motion+52*bank));where=(model+offset)&0xffffffff
        size=half(v,where+2)+5;data=v.read(where,size);out=Pose()
        assert lib.ff7_motion_decode_frame(data,len(data),1 if bank else 48,frame,ctypes.byref(out))
        return tuple(out.position),[list(out.angle[j])for j in range(1 if bank else 48)]
    def state(v,slot,motion,action):
        actor=0x801518e4+0xb9c*slot
        v.write(actor,b'\0'*0x174);v.write(actor+2,struct.pack('<H',action));v.write(actor+14,struct.pack('<HH',motion,48))
        v.write(actor+0x27,b'\x80');v.write(0x800fa714+64*slot,b'\1\0');v.word(0x800fa6d8+64*slot,0)
        return actor
    def step(v,model,slot):v.reg(4,slot);v.reg(5,model+12);v.reg(6,model);v.run(0x800cd400)
    cases=[]
    # Original resident rotation matrices establish the PSX Euler convention.
    # Both roots must receive the SAME world transform; simply adding Z to the
    # weapon's local Euler angle would detach/rotate it incorrectly.
    v,model=vm();worst=0
    def matrix(angles):
        v.write(0x801e1000,struct.pack('<3H',*angles));v.reg(4,0x801e1000);v.reg(5,0x801e1100);v.run(0x8003bf8c)
        values=struct.unpack('<9h',v.read(0x801e1100,18));return [values[j:j+3]for j in(0,3,6)]
    for role,(target,source,frame)in enumerate(((1,0,0),(15,0,0),(11,5,4))):
        for bank in range(2):
            offset=struct.unpack_from('<I',original,12+4*(source+52*bank))[0];seed=Pose()
            assert lib.ff7_motion_decode_frame(original[offset:],len(original)-offset,1 if bank else 48,frame,ctypes.byref(seed))
            original_matrix=matrix(seed.angle[0])
            for f in range(30):
                triangle=min(f,29-f);t=f/29;t=t*t*(3-2*t)
                angle=56+triangle if role==0 else (round(1024*t)if role==1 else -24)
                rad=angle*math.tau/4096;c,s=math.cos(rad),math.sin(rad)
                reference=[[c*original_matrix[0][j]-s*original_matrix[1][j]for j in range(3)],
                           [s*original_matrix[0][j]+c*original_matrix[1][j]for j in range(3)],original_matrix[2]]
                actual=matrix(expected(v,model,target,f,bank)[1][0])
                error=max(abs(actual[i][j]-reference[i][j])for i in range(3)for j in range(3));worst=max(worst,error)
                assert error<12,(role,bank,f,error)
    cases.append('180 generated root matrices match original resident RotMatrix8003BF8C under common body/weapon world roll; maximum coefficient error %.3f/4096'%worst)
    for slot,guest in((0,11),(1,12),(2,26)):
        v,model=vm(slot,guest)
        assert v.read(model+35388,1)==b'\1' and v.read(model+35392,1)==b'\x0f'
        assert v.read(0x801b0000,len(original))==original
        for motion,action in((1,1),(15,2),(11,0)):
            actor=state(v,slot,motion,action)
            for frame in range(30):
                step(v,model,slot)
                assert pose(v,actor+0x174,48)==expected(v,model,motion,frame,0),(slot,motion,frame,'body')
                assert pose(v,0x800fa6e0+64*slot,1)==expected(v,model,motion,frame,1),(slot,motion,frame,'weapon')
            assert word(v,actor+0x74)==0 and word(v,0x800fa6d8+64*slot)==0
    cases.append('270 whole CD400 calls/540 paired decoded frames across all3 battle slots: generated low-HP,death,guard poses match every original decoder position/rotation; independent source staging unchanged')
    # Actual original queue insertion, not a fabricated command-to-animation ID.
    v,model=vm();actor=state(v,0,0,0);v.write(0x800f6934,b'\xff'*512)
    def queue(command):
        v.write(0x801e0000,bytes([6,0,0,command,0,0,1,0]));v.reg(4,0x801e0000);v.run(0x800a3d4c)
    queue(19);assert word(v,0x800f83e4)&32
    for frame in range(8):
        step(v,model,0);assert pose(v,actor+0x174,48)==expected(v,model,11,frame,0)
        assert pose(v,0x800fa6e0,1)==expected(v,model,11,frame,1)
    # Rewind owns the generated bytes and the selected-role/bitstream cursors.
    saved_ram=v.read(0,0x200000);saved_extra=v.read(0x1f000000,0x20000)
    step(v,model,0);next_pose=(pose(v,actor+0x174,48),pose(v,0x800fa6e0,1))
    v.write(0,saved_ram);v.write(0x1f000000,saved_extra);lib.ff7_party_battle_restore()
    step(v,model,0);assert (pose(v,actor+0x174,48),pose(v,0x800fa6e0,1))==next_pose
    queue(1);assert not word(v,0x800f83e4)&32
    step(v,model,0);assert pose(v,actor+0x174,48)==expected(v,model,0,0,0)
    assert pose(v,0x800fa6e0,1)==expected(v,model,0,0,1)
    cases.append('Whole original queue800A3D4C sets Defend0x13 flag and clears it for next Attack; two guarded decoder seams select paired guard and reset both cursors on return to idle')
    # Whole original action interpreter consumes the changed low-HP/death script.
    v,model=vm();settings=model+struct.unpack_from('<I',original,8)[0]
    # Runtime model setup relocates settings/action table pointers; fixture here
    # supplies those loader outputs without changing the interpreter or scripts.
    for i in range(74):v.word(settings+0x68+4*i,settings+word(v,settings+0x68+4*i))
    for action,motion in((1,1),(2,15)):
        actor=state(v,0,0,action);v.write(actor+0x3b,b'\1')
        v.reg(4,0);v.reg(5,settings+0x68);v.reg(6,model+12);v.reg(7,model)
        v.run(0x800c7c4c)
        assert half(v,actor+14)==motion,(action,half(v,actor+14))
        assert pose(v,actor+0x174,48)==expected(v,model,motion,0,0),(action,'first-frame')
        for frame in range(1,30):
            v.reg(4,0);v.reg(5,settings+0x68);v.reg(6,model+12);v.reg(7,model);v.run(0x800c7c4c)
            assert pose(v,actor+0x174,48)==expected(v,model,motion,frame,0),(action,frame)
        if action==2:
            last=pose(v,actor+0x174,48)
            for _ in range(5):
                v.reg(4,0);v.reg(5,settings+0x68);v.reg(6,model+12);v.reg(7,model);v.run(0x800c7c4c)
                assert pose(v,actor+0x174,48)==last,'Death script did not hold final pose'
    cases.append('Whole original action interpreterC7C4C selects generated motion1 for low-HP action1 and generated motion15 for death action2; all30 frames execute and F1 holds final death pose')
    actor=state(v,0,0,0);v.write(actor+0x3b,b'\1');v.write(0x800f6934,b'\xff'*512);queue(19)
    for frame in range(20):
        v.reg(4,0);v.reg(5,settings+0x68);v.reg(6,model+12);v.reg(7,model);v.run(0x800c7c4c)
        assert half(v,actor+14)==0 and pose(v,actor+0x174,48)==expected(v,model,11,frame,0)
        assert pose(v,0x800fa6e0,1)==expected(v,model,11,frame,1)
    cases.append('Original idle-action interpreter plus actual queued Defend selects the new guard for20 paired frames without assigning a fictitious defend action')
    v,model=vm(0,10);assert v.read(model,51420)==original[:51420]
    cases.append('Native flashback identity10 remains byte-for-byte original')
    for corrupt in('asset','guard'):
        v,model=vm();v.write(model,original[:51420]);v.write(model+51420,b'\xa5'*32)
        if corrupt=='asset':v.write(model+500,bytes([original[500]^1]))
        else:v.word(ev['sites'][0]['address']+4,0)
        before=v.read(model,51452);regs=(ctypes.c_uint32*32)();regs[16]=0
        lib.ff7_test_battle_hook(0x800b5c68,regs)
        assert v.read(model,51452)==before
    cases.append('Generated guest bytes/cursors/selected role restore with RAM snapshot; corrupt source or decoder guard leaves original model and trailing allocation canary unchanged')
    result={'disc':a.disc.name,'status':'passed','cases':cases,'limits':ev['visual_limits']}
    if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n',newline='\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
