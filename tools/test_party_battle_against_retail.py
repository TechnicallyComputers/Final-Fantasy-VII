"""Run original PSX battle routines with the real guarded C adapter.

This isolated oracle checks identity/record/AI/asset routing. It is not a visual
or end-to-end battle acceptance test. Owner disc assets remain local.
"""
import argparse
import ctypes
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, image_data, kernel_sections
from inspect_ff7_battle import inspect
from inspect_ff7_animations import decompress_lzs,model_inventory
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0, UC_MIPS_REG_PC

class VM:
    def __init__(self,lib,report,images,exe,kernel,count=16):
        self.lib=lib;lib.ff7_test_battle_reset(count)
        self.uc=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
        self.uc.mem_map_ptr(0,0x200000,7,lib.ff7_test_battle_ram())
        self.uc.mem_map_ptr(0x1f000000,0x20000,7,lib.ff7_test_battle_expansion())
        self.write(0x80010000,exe[0x800:])
        for data,base in images.values():self.write(base,data)
        for base,index in [(0x800707c0,0),(0x800708c0,1),(0x80082268,2),
                           (0x80071e44,6),(0x800738a0,5),(0x800722c4,7)]:self.write(base,kernel[index])
        self.write(0x800491d0,struct.pack('<11I',0,1,2,3,4,5,6,7,8,6,7))
        self.sites={s['address']:s for s in report['sites']};self.calls=[]
        self.uc.hook_add(UC_HOOK_CODE,self.hook)
        self.reg(29,0x801ff000);self.reg(31,0x80001000)
    def reg(self,r,v=None):
        if v is not None:self.uc.reg_write(UC_MIPS_REG_0+r,v&0xffffffff)
        return self.uc.reg_read(UC_MIPS_REG_0+r)
    def write(self,a,b):self.uc.mem_write(a&0x1fffffff,bytes(b))
    def word(self,a,v):self.write(a,struct.pack('<I',v))
    def read(self,a,n):return bytes(self.uc.mem_read(a&0x1fffffff,n))
    def stub(self,*addresses):
        for a in addresses:self.write(a,struct.pack('<II',0x03e00008,0x00001021))
    def run(self,start,end=0x80001000,count=200000):
        self.reg(31,0x80001000);self.uc.emu_start(start,end,count=count)
        assert self.uc.reg_read(UC_MIPS_REG_PC) in (end,end-4),hex(self.uc.reg_read(UC_MIPS_REG_PC))
    def hook(self,uc,pc,size,_):
        if pc==0x80033e74:self.calls.append(tuple(self.reg(r)for r in range(4,8)))
        if pc not in self.sites:return
        regs=(ctypes.c_uint32*32)(*(self.reg(r)for r in range(32)))
        self.lib.ff7_test_battle_hook(pc,regs)
        for r in range(1,32):
            if regs[r]!=self.reg(r):self.reg(r,regs[r])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',required=True,type=Path);parser.add_argument('--disc',required=True,type=Path)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    lib=ctypes.CDLL(str(args.library.resolve()))
    for n in ('ff7_test_battle_ram','ff7_test_battle_expansion'):getattr(lib,n).restype=ctypes.c_void_p
    lib.ff7_test_battle_hook.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    report=inspect(args.disc)
    checked=json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/battle.evidence.json').read_text())
    assert report==checked,'Unsupported battle revision'
    d=Disc(args.disc)
    try:
        images={n:image_data('BATTLE/'+n+'.X',d.read('BATTLE/'+n+'.X'))for n in ('BATINI','BATTLE')}
        exe=d.read(next(p for p in d.files if p.startswith('SCUS_')and '/'not in p))
        kernel=kernel_sections(d.read('INIT/KERNEL.BIN'));lba,size=d.files['ENEMY6/SEFIROS.LZS']
        seph=d.read('ENEMY6/SEFIROS.LZS')
    finally:d.reader.close()
    lib.ff7_test_battle_extent(lba,size);cases=[]
    # Full original battle record initializer and refresh. External action queue,
    # sound and status notification routines are isolated; original BATINI stat,
    # equipment/accessory, commands and materia routines execute normally.
    for added in (11,26):
        vm=VM(lib,report,images,exe,kernel)
        vm.stub(0x800a4ba4,0x800a4e80,0x800b108c,0x800155a4)
        vm.write(0x8009cbdc,bytes([0,7,added]))
        for g in range(9):vm.write(0x8009c738+g*132,bytes([g]))
        for slot,g in enumerate((0,7,added)):
            rec=0x8009c738+g*132 if g<9 else 0x9f010000+(g-11)*132
            vm.write(rec+1,bytes([30+slot]));vm.write(rec+6,b'\x21');vm.write(rec+14,b'\x01')
            vm.write(rec+0x1c,bytes([0,0,255]));vm.write(rec+0x22,b'\x01\0')
            vm.write(rec+0x40,b'\xff'*64)
            derived=0x8009d84c+slot*0x440
            vm.write(derived+0x10,struct.pack('<HHHH',1000+slot,1200+slot,200+slot,300+slot))
            vm.write(derived+0x4c,b'\xff'*96);vm.write(derived+0x108,b'\xff'*768)
            for i,cmd in enumerate((1,2,3,4)):
                vm.write(derived+0x4c+i*6,bytes([cmd,7,0,0,0,0]))
        before=vm.read(0x8009c738,9*132);vm.run(0x801b08c0)
        assert vm.read(0x8009c738,9*132)==before,'Battle init changed native records'
        for slot,g in enumerate((0,7,added)):
            rec=0x8009c738+g*132 if g<9 else 0x9f010000+(g-11)*132
            assert vm.read(0x800f5e60+slot*0x34,4)==struct.pack('<I',rec)
            assert vm.read(0x801636b8+slot*16,1)==bytes([g])
            assert vm.read(0x800f83e8+slot*0x68,1)==bytes([g])
            assert vm.read(0x800f840c+slot*0x68,4)==struct.pack('<I',1000+slot)
            assert [vm.read(0x8009d898+slot*0x440+i*6,1)[0]for i in range(4)]==[1,2,3,4]
            vm.write(rec+0x2c,struct.pack('<H',700+slot));vm.write(rec+0x30,struct.pack('<H',70+slot))
        vm.stub(0x801b1734);vm.run(0x801b0f08)
        for slot in range(3):
            assert vm.read(0x800f840c+slot*0x68,4)==struct.pack('<I',700+slot)
            assert vm.read(0x800f8408+slot*0x68,2)==struct.pack('<H',70+slot)
        cases.append(f'whole BATINI init/refresh and normal Attack/Magic/Summon/Item command list: extra{added} + Cloud/Vincent')
    # Full original personal-AI dispatcher, all16 extras and all16 script roles.
    for g in range(11,27):
        vm=VM(lib,report,images,exe,kernel)
        vm.write(0x801636b8,bytes([g]));before=vm.read(0x800e7a58,32)
        for role in range(16):
            vm.reg(4,0);vm.reg(5,role);vm.reg(6,0);vm.run(0x800a6000)
        assert vm.read(0x800e7a58,32)==before
    cases.append('256 whole original personal-AI dispatch calls return without original Sephiroth scripts or out-of-range table reads')
    # Full model sorting. Native IDs remain logical; only model pair receives10.
    # Exercise two extra members sharing one presentation independently.
    for guests in ((0,7,11),(26,0,7),(11,12,0),(1,7,11)):
        vm=VM(lib,report,images,exe,kernel)
        for slot,g in enumerate(guests):vm.write(0x801636b8+slot*16,bytes([g]))
        vm.run(0x800c5e94)
        pairs=[struct.unpack('<HH',vm.read(0x800fa9c4+i*4,4))for i in range(3)]
        assert [p[0]for p in pairs]==sorted(p[0]for p in pairs)
        for model,slot in pairs:
            if guests[slot]>=11:assert model==10,(guests,pairs)
        assert [vm.read(0x801636b8+i*16,1)[0]for i in range(3)]==list(guests)
    cases.append('whole model sorter: Cloud/Vincent + added member, two extras sharing presentation, native variant paths preserved')
    # Execute each original async model CD argument block with actor-pair2
    # pointing to an extra. CD handler records arguments without doing I/O.
    for start,end,pair in ((0x800b3cec,0x800b3d28,0),(0x800b3b18,0x800b3b54,1),(0x800b3be4,0x800b3c20,2)):
        vm=VM(lib,report,images,exe,kernel);vm.stub(0x80033e74,0x800b7fb4)
        vm.write(0x801636d8,b'\x0b');vm.write(0x800fa9c4+pair*4,struct.pack('<HH',10,2))
        vm.run(start,end)
        assert vm.calls[-1][:3]==(lba,(size+2047)&~2047,0x801b0000),vm.calls
    cases.append('all3 original asynchronous model load paths request the profile asset extent and unchanged stage buffer')
    # Original arena continuation copies each live actor's HP/MP back into its
    # own persistent record. Verify the extra is not silently skipped by9cap.
    vm=VM(lib,report,images,exe,kernel);vm.write(0x8009cbdc,bytes([0,7,11]))
    for g in range(9):vm.write(0x8009c738+132*g,bytes([g]))
    expected_native=bytearray(vm.read(0x8009c738,9*132))
    for slot,g in enumerate((0,7,11)):
        vm.word(0x800f840c+slot*0x68,900+slot)
        vm.write(0x800f8408+slot*0x68,struct.pack('<H',90+slot))
        if g<9:
            struct.pack_into('<H',expected_native,132*g+0x2c,900+slot)
            struct.pack_into('<H',expected_native,132*g+0x30,90+slot)
    vm.run(0x800a36dc,0x800a3768)
    assert vm.read(0x8009c738,9*132)==bytes(expected_native)
    assert vm.read(0x9f01002c,2)==struct.pack('<H',902)
    assert vm.read(0x9f010030,2)==struct.pack('<H',92)
    cases.append('original arena continuation HP/MP writeback reaches independent extra record and only selected native records')
    # Original memcpy/weapon loader and guarded preparation; native flashback
    # Sephiroth is untouched. No expanded asset buffer or recompression needed.
    unpacked=decompress_lzs(seph);prep=report['motion_preparation'];body=prep['body_bytes']
    expected=bytearray(unpacked[:body])
    for edit in prep['pointer_aliases']:struct.pack_into('<I',expected,edit['offset'],edit['after'])
    for offset in prep['damage_bytes']:expected[offset]=5
    for slot,g in ((0,11),(1,12),(2,26),(0,10)):
        vm=VM(lib,report,images,exe,kernel);vm.write(0x801b0000,unpacked)
        vm.write(0x801636b8+slot*16,bytes([g]));dest=0x80103200+slot*0xf000
        vm.write(dest+body,b'\xa5'*32);vm.reg(4,slot);vm.run(0x800b5c1c)
        assert vm.read(dest,body)==(bytes(expected)if g>=11 else unpacked[:body])
        assert vm.read(dest+body,32)==b'\xa5'*32
        assert vm.read(0x801b0000,len(unpacked))==unpacked,'Source staging asset changed'
    cases.append('whole original body/weapon load: exact six relative-pointer + four damage-byte changes; allocation/skeleton/textures/nativeSeph intact')
    # Consume every reused frame through the original full animation-step and
    # bitstream decoder, including paired weapon motions. Alias and source must
    # yield identical bone poses, position and decoder state at every frame.
    vm=VM(lib,report,images,exe,kernel);dest=0x80103200;vm.write(dest,bytes(expected))
    inventory=model_inventory(seph)
    def decode(motion):
        vm.write(0x801518f2,struct.pack('<HH',motion,48));vm.write(0x800fa714,struct.pack('<H',1))
        vm.write(0x8015190b,b'\x80');vm.word(0x80151958,0);vm.word(0x800fa6d8,0)
        vm.write(0x80151a58,b'\0'*(48*52));vm.write(0x800fa6e0,b'\0'*52)
        frames=inventory['motions'][5 if motion in (5,8) else 12]['frames'];poses=[]
        for _ in range(frames):
            vm.reg(4,0);vm.reg(5,dest+12);vm.reg(6,dest);vm.run(0x800cd400)
            poses.append((vm.read(0x80151a58,48*52),vm.read(0x800fa6e0,52),
                          vm.read(0x80151958,4),vm.read(0x800fa6d8,4)))
        return poses
    for alias,source in ((8,5),(9,12),(10,12)):assert decode(alias)==decode(source)
    cases.append('124 original animation-step calls decode all cover/item fallback frames identically to own source motion, body and weapon paired')
    # Modified assets fail atomically before any preparation write.
    vm=VM(lib,report,images,exe,kernel);vm.write(0x801636b8,b'\x0b')
    corrupt=bytearray(unpacked[:body]);corrupt[500]^=1;vm.write(dest,corrupt)
    regs=(ctypes.c_uint32*32)();regs[16]=0;lib.ff7_test_battle_hook(0x800b5c68,regs)
    assert vm.read(dest,body)==bytes(corrupt)
    cases.append('whole-body CRC mismatch leaves every asset byte untouched')
    result={'status':'passed','disc':args.disc.name,'cases':cases,'limitations':report['integration']['pending']}
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
