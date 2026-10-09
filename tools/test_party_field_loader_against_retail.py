"""Exercise production field injection and original CHAR/PC/DFANM handlers.

Files come from the mounted owner image; no extracted art is emitted. This is
an isolated loader/opcode oracle, not a visual or whole-story acceptance test.
"""
import argparse,ctypes,gzip,json,struct
from pathlib import Path
from unicorn import Uc,UC_ARCH_MIPS,UC_MODE_MIPS32,UC_MODE_LITTLE_ENDIAN,UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0,UC_MIPS_REG_PC
from inspect_ff7_party import Disc,ROOT
from inspect_ff7_animations import decompress_lzs
from inspect_ff7_field_loader import inspect

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',type=Path,required=True)
    p.add_argument('--library',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    lib=ctypes.CDLL(str(a.library.resolve()));lib.ff7_test_loader_reset()
    for n in('ram','expansion','gpu'):getattr(lib,'ff7_test_loader_'+n).restype=ctypes.c_void_p
    lib.ff7_test_loader_file.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32]
    lib.ff7_test_loader_hook.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    d=Disc(a.disc);keep=[]
    try:
        field=gzip.decompress(d.read('FIELD/FIELD.BIN')[8:]);dat=decompress_lzs(d.read('FIELD/MD1STIN.DAT'))
        for name in ['FIELD/MD1STIN.BSX','FIELD/NIVL.BSX']+[n for n in d.files if n.endswith('.BCX')]:
            b=ctypes.create_string_buffer(d.read(name));keep.append(b);lba,size=d.files[name]
            lib.ff7_test_loader_file(name.encode(),b,size,lba)
        lba,size=d.files['FIELD/MD1STIN.BSX']
    finally:d.reader.close()
    uc=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
    for base,length,name in((0,0x200000,'ram'),(0x1f000000,0x20000,'expansion'),(0x800000,0x600000,'gpu')):
        uc.mem_map_ptr(base,length,7,getattr(lib,'ff7_test_loader_'+name)())
    def wr(p,b):uc.mem_write(p&0x1fffffff,bytes(b))
    def rd(p,n):return bytes(uc.mem_read(p&0x1fffffff,n))
    def word(p,v):wr(p,struct.pack('<I',v))
    def readword(p):return struct.unpack('<I',rd(p,4))[0]
    def reg(n,v=None):
        if v is not None:uc.reg_write(UC_MIPS_REG_0+n,v&0xffffffff)
        return uc.reg_read(UC_MIPS_REG_0+n)
    def call_hook(pc):
        regs=(ctypes.c_uint32*32)(*(reg(n)for n in range(32)));lib.ff7_test_loader_hook(pc,regs)
        for n in range(1,32):reg(n,regs[n])
    report=inspect(a.disc);fieldsites=json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/field-hooks.evidence.json').read_text())
    sites={s['address']for s in report['sites']+fieldsites['sites']}
    uc.hook_add(UC_HOOK_CODE,lambda u,pc,size,data:call_hook(pc)if pc in sites else None)
    def run(pc,end=0x80001000):
        reg(31,0x80001000);uc.emu_start(pc,end,count=1000000)
        assert uc.reg_read(UC_MIPS_REG_PC)==end,hex(uc.reg_read(UC_MIPS_REG_PC))
    wr(0x800a0000,field);wr(0x80114fe4,dat);metadata=struct.unpack_from('<I',dat,24)[0]
    word(0x8007e770,metadata);word(0x8008357c,metadata+4);word(0x8004a62c,0x80140000)
    wr(0x8009a05c,b'\x74\0')
    assert (readword(0x800da5c8+24*0x74),readword(0x800da5cc+24*0x74))==(lba,size)
    reg(6,0x80115000);reg(29,0x801ff000);before=rd(0x80114fe4,len(dat));call_hook(0x800ba534)
    assert reg(6)!=0x80115000,('preparation rejected',lib.ff7_test_loader_rejects())
    script=reg(6);models=readword(0x8007e770);assert rd(0x80114fe4,len(dat))==before
    assert rd(script+2,2)==bytes([dat[30]+1,dat[31]+1]);assert readword(0x8004a62c)==0x80800000
    reg(17,0x801b0000);call_hook(0x800ac484);assert reg(17)==0x80900000
    entity=dat[30];model=dat[31];table=32+8*(entity+1)+4*struct.unpack_from('<H',dat,34)[0]
    entry=struct.unpack('<H',rd(script+table+64*entity,2))[0]
    # Real opcode handlers; the original field has already allocated its fixed
    #32 model-state slots. Fixtures set only current entity/cursor and leader.
    word(0x8009c6dc,script);word(0x8009c544,0x80074ea4);word(0x8009c6e0,0x80100000)
    wr(0x8009ad30,b'\xff'*9);wr(0x8007eb98,b'\xff'*64);wr(0x800722c4,bytes([entity]))
    wr(0x8009c6c4,bytes([model])) # native CHARs precede appended entity
    wr(0x800831fc+2*entity,struct.pack('<H',entry));wr(0x8009cbdc,b'\x0b\x00\x07');wr(0x8009d391,b'\x0b\x00\x07')
    native=rd(0x8009ad30,9)
    run(0x800c5740);assert rd(0x8007eb98+entity,1)==bytes([model])
    run(0x800ceb94);assert lib.ff7_party_field_entity(11)==entity
    assert rd(0x8009ad30,9)==native and rd(0x8010002a,2)==bytes([model,0])
    run(0x800c5898)
    assert struct.unpack('<H',rd(0x800831fc+2*entity,2))[0]==entry+7
    snapshot=[rd(base,n)for base,n in((0,0x200000),(0x1f000000,0x20000),(0x800000,0x600000))]
    # Failed preparation on next field restores prior native workspace; no
    # model/script publication. Changed original instruction rejects outright.
    word(0x8007e770,metadata);word(0x8008357c,metadata+4);reg(6,0x80115000);word(0x800da5cc+24*0x74,size+1)
    call_hook(0x800ba534);assert reg(6)==0x80115000 and readword(0x8004a62c)==0x80140000
    reg(17,0x801b0000);call_hook(0x800ac484);assert reg(17)==0x801b0000
    word(0x800ba534,0);call_hook(0x800ba534);assert lib.ff7_test_loader_rejects()==2
    for (base,n),data in zip(((0,0x200000),(0x1f000000,0x20000),(0x800000,0x600000)),snapshot):wr(base,data)
    lib.ff7_party_field_loader_restore();lib.ff7_party_field_restore()
    reg(17,0x801b0000);call_hook(0x800ac484);assert reg(17)==0x80900000
    assert lib.ff7_party_field_entity(11)==entity
    result={'disc':a.disc.name,'status':'passed','extent_table':'Original FIELD bytes at800DA5C8; MD1STIN tuple matches owner ISO directly, never synthesized','cases':['Production owned-disc preparation publishes expanded script/model metadata and separate GPU arenas; all original DAT bytes preserved','Original A1 CHAR, A0 PC and A2 DFANM execute for appended entity; logical proxy11 binds separate model and selects leader without native mapping writes','Extent mismatch restores original workspace and leaves next field unmodified; exact instruction mismatch rejects','Restoring guest RAM/Expansion1/GPU arena snapshot recovers prepared field and independent entity; callback preserves arbitrary incoming CPU PC'],'limitations':'Isolated actor init; full story-script scheduling, pose rendering, walking/following, field transitions and application rewind acceptance need live validation'}
    if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
