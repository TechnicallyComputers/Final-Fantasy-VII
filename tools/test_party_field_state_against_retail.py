"""Original MIPS oracle for independent32-record field model state."""
import argparse,ctypes,gzip,json,struct
from pathlib import Path
from unicorn import Uc,UC_ARCH_MIPS,UC_MODE_MIPS32,UC_MODE_LITTLE_ENDIAN,UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0,UC_MIPS_REG_PC
from inspect_ff7_party import Disc,ROOT
from inspect_ff7_field_state import inspect
from inspect_ff7_animations import decompress_lzs
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    lib=ctypes.CDLL(str(a.library.resolve()))
    for n in('ram','expansion'):getattr(lib,'ff7_test_state_'+n).restype=ctypes.c_void_p
    lib.ff7_test_state_hook.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    lib.ff7_party_field_state_begin.restype=ctypes.c_uint32
    evidence=inspect(a.disc);sites={s['address']:s for s in evidence['sites']}
    assert evidence==json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/field-state.evidence.json').read_text())
    d=Disc(a.disc)
    try:
        exe=d.read(next(n for n in d.files if n.startswith('SCUS_')and '/'not in n))[0x800:]
        field=gzip.decompress(d.read('FIELD/FIELD.BIN')[8:])
        semkin=decompress_lzs(d.read('FIELD/SEMKIN_3.DAT'))
    finally:d.reader.close()
    def vm():
        lib.ff7_test_state_reset();u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
        u.mem_map_ptr(0,0x200000,7,lib.ff7_test_state_ram());u.mem_map_ptr(0x1f000000,0x10000,7,lib.ff7_test_state_expansion())
        u.mem_write(0x10000,exe);u.mem_write(0xa0000,field)
        def hook(uc,pc,size,data):
            if pc not in sites:return
            regs=(ctypes.c_uint32*32)(*(uc.reg_read(UC_MIPS_REG_0+n)for n in range(32)))
            lib.ff7_test_state_hook(pc,regs)
            for n in range(1,32):uc.reg_write(UC_MIPS_REG_0+n,regs[n])
        u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_MIPS_REG_0+29,0x801ff000);return u
    def wr(u,p,b):u.mem_write(p&0x1fffffff,bytes(b))
    def rd(u,p,n):return bytes(u.mem_read(p&0x1fffffff,n))
    def word(u,p,n):wr(u,p,struct.pack('<I',n))
    def run(u,pc,end=0x80001000):
        u.reg_write(UC_MIPS_REG_0+31,0x80001000);u.emu_start(pc,end,count=1000000)
        assert u.reg_read(UC_MIPS_REG_PC)in(end,end-4),hex(u.reg_read(UC_MIPS_REG_PC))
    u=vm();arena=lib.ff7_party_field_state_begin(0x80074ea4,48,16,16);assert arena
    for pc,s in sites.items():
        if s['action']!='BASE':continue
        u.reg_write(UC_MIPS_REG_0+s['register'],0x80070000);run(u,pc,pc+4)
        assert u.reg_read(UC_MIPS_REG_0+s['register'])==arena+s['field_offset']
    # Execute the entire original field initializer with its normal indirect
    # state pointer, comparing a reference allocated array to the mod arena.
    results=[]
    for enhanced in(False,True):
        u=vm();native=bytes((i*37)&255 for i in range(16*132));wr(u,0x80074ea4,native)
        target=lib.ff7_party_field_state_begin(0x80074ea4,48,16,16)if enhanced else 0x80120000
        if not enhanced:wr(u,target,native+b'\0'*(16*132))
        word(u,0x8009c544,target);word(u,0x8009c6dc,0x80110000);word(u,0x8009c6e0,0x80100000)
        wr(u,0x80110000,bytes([2,5,32,32,0,0,0,0,0,2]));run(u,0x800ba7c4)
        results.append(rd(u,target,32*132));assert rd(u,0x80074ea4,16*132)==native
    assert results[0]==results[1]
    # Resident return-to-field capture must read coordinates/status from the
    # relocated leader, including model slots beyond original capacity.
    for index in(0,15,16,31):
        u=vm();arena=lib.ff7_party_field_state_begin(0x80074ea4,48,16,16);native=rd(u,0x80074ea4,16*132)
        wr(u,0x800965e0,struct.pack('<H',index));word(u,arena+132*index+12,123<<12)
        word(u,arena+132*index+16,456<<12);wr(u,arena+132*index+114,struct.pack('<H',789));wr(u,arena+132*index+54,b'\x42')
        run(u,0x800119e4)
        assert rd(u,0x8009d27e,8)==struct.pack('<HHHB',123,456,789,0x42)+b'\0'
        assert rd(u,0x80074ea4,16*132)==native
    # Additional actors do not consume the native CHAR allocation counter.
    # A delayed original actor (as in SEMKIN_3) may still allocate its native
    # model after any/all extras have initialized.
    u=vm();arena=lib.ff7_party_field_state_begin(0x80074ea4,48,16,16)
    word(u,0x8009c544,arena);word(u,0x8009c6dc,0x80110000);wr(u,0x8009c6c4,b'\x05')
    wr(u,0x80110100,b'\xa1\x00');native=rd(u,0x80074ea4,16*132)
    for entity in range(48,64):
        wr(u,0x800722c4,bytes([entity]));wr(u,0x800831fc+2*entity,struct.pack('<H',0x100));run(u,0x800c5740)
        assert rd(u,0x8007eb98+entity,1)==bytes([16+entity-48]) and rd(u,0x8009c6c4,1)==b'\x05'
    wr(u,0x800722c4,b'\x04');wr(u,0x800831fc+8,struct.pack('<H',0x100));run(u,0x800c5740)
    assert rd(u,0x8007eb98+4,1)==b'\x05'and rd(u,0x8009c6c4,1)==b'\x06'
    assert rd(u,0x80074ea4,16*132)==native
    # Replay the actual original SEMKIN_3 CHAR operands and delayed g_sol_1
    # CHAR, comparing all native model states against a no-extra reference.
    script=semkin[28:28+struct.unpack_from('<I',semkin,4)[0]-struct.unpack_from('<I',semkin)[0]]
    entities,models=script[2:4];table=32+8*entities+4*struct.unpack_from('<H',script,6)[0]
    entries=[struct.unpack_from('<H',script,table+64*i)[0]for i in range(entities)]
    assert entities==11 and models==6 and script[entries[4]:entries[4]+3]==b'\xa5\0\0'
    delayed=entries[4]+11;assert script[delayed:delayed+2]==b'\xa1\x01'
    outputs=[]
    for enhanced in(False,True):
        u=vm();target=lib.ff7_party_field_state_begin(0x80074ea4,entities,models,1)if enhanced else 0x80120000
        word(u,0x8009c544,target);word(u,0x8009c6dc,0x80110000);wr(u,0x80110000,script)
        def char(entity,entry):
            wr(u,0x800722c4,bytes([entity]));wr(u,0x800831fc+2*entity,struct.pack('<H',entry));run(u,0x800c5740)
        for entity,entry in enumerate(entries):
            if script[entry]==0xa1:char(entity,entry)
        assert rd(u,0x8009c6c4,1)==b'\x05'
        if enhanced:
            wr(u,0x80110000+len(script),bytes([0xa1,models]));char(entities,len(script))
            assert rd(u,0x8007eb98+entities,1)==bytes([models])and rd(u,0x8009c6c4,1)==b'\x05'
        char(4,delayed);assert rd(u,0x8007eb98+4,1)==b'\x05'and rd(u,0x8009c6c4,1)==b'\x06'
        outputs.append((rd(u,target,models*132),rd(u,0x8007eb98,entities)))
    assert outputs[0]==outputs[1]
    r={'disc':a.disc.name,'status':'passed','cases':['All398 original ADDIU base instructions produce independent field-state addresses','Whole original BA7C4 initializes32 records identically in reference and enhancement arrays; native16-record storage untouched','Whole original resident119E4 return-location snapshot reads relocated model0/15/16/31 coordinates,triangle and direction','Whole original CHAR initializes16 appended entities without consuming native counter; subsequent delayed native CHAR still gets original model5','Actual SEMKIN_3 CHAR operands plus delayed g_sol_1 CHAR: all6 native state records and11 entity mappings equal the no-extra reference after extra creation'],'limits':'Direct base construction scan and isolated original initializer/snapshot/CHAR oracle; Production loader and saturated-field initialization validated separately; live traversal pending'}
    if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n',newline='\n')
    print(json.dumps(r,indent=2))
if __name__=='__main__':main()
