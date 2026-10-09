"""Execute original resident character paths with the production bridge.

Uses owner-disc executable/kernel bytes, shared guest memory and real C hooks.
Exercises names, armor/weapon slot queries and derived-stat recalculation; any
unsupported callees/paths are reported instead of counted as gameplay proof.
"""
import argparse
import ctypes
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, kernel_sections
from inspect_ff7_resident_party import inspect
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0, UC_MIPS_REG_PC


class VM:
    def __init__(self,lib,exe,kernel,sites):
        self.lib=lib;lib.ff7_test_game_reset()
        self.uc=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
        self.uc.mem_map_ptr(0,0x200000,7,lib.ff7_test_game_ram())
        self.uc.mem_map_ptr(0x1f000000,4096,7,lib.ff7_test_game_expansion())
        self.uc.mem_write(0x10000,exe[0x800:])
        self.uc.mem_write(0x491d0,struct.pack('<11I',0,1,2,3,4,5,6,7,8,6,7))
        for address,data in ((0x9c738,kernel[3]),(0x738a0,kernel[5]),
                             (0x71e44,kernel[6]),(0x71c24,kernel[7]),(0x730d0,kernel[8])):
            self.uc.mem_write(address,data)
        self.sites={s['address']:s for s in sites};self.hooks=0;self.trace=[]
        self.uc.hook_add(UC_HOOK_CODE,self.hook)
        self.reg(28,0x80062d44);self.reg(29,0x801a0000);self.reg(31,0x80001000)
    def reg(self,n,value=None):
        if value is not None:self.uc.reg_write(UC_MIPS_REG_0+n,value&0xffffffff)
        return self.uc.reg_read(UC_MIPS_REG_0+n)
    def write(self,address,data):self.uc.mem_write(address&0x1fffffff,bytes(data))
    def read(self,address,size):return bytes(self.uc.mem_read(address&0x1fffffff,size))
    def hook(self,uc,pc,size,_):
        word=int.from_bytes(self.read(pc,4),'little')
        if word>>26 in (40,41,43):
            immediate=word&65535;immediate=immediate-65536 if immediate&32768 else immediate
            address=(self.reg(word>>21&31)+immediate)&0x1fffffff
            if 0x9e0d4<=address<0x9e0d8:
                self.trace.append([hex(pc),hex(address),hex(self.reg(word>>16&31))])
        site=self.sites.get(pc)
        if not site:return
        assert self.read(pc-24,52)==struct.pack('<13I',*site['guard'])
        registers=(ctypes.c_uint32*32)(*(self.reg(n) for n in range(32)))
        self.lib.ff7_test_game_hook(pc,registers)
        for n in range(1,32):
            if self.reg(n)!=registers[n]:self.reg(n,registers[n])
        self.hooks+=1
    def run(self,pc):
        self.reg(31,0x80001000)
        self.uc.emu_start(pc,0x80001000,count=1000000)
        assert self.uc.reg_read(UC_MIPS_REG_PC) in (0x80001000,0x80000ffc)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--library',required=True,type=Path)
    p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    lib=ctypes.CDLL(str(args.library.resolve()))
    for name in ('ff7_test_game_ram','ff7_test_game_expansion'):
        getattr(lib,name).restype=ctypes.c_void_p
    lib.ff7_test_game_hook.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    lib.ff7_test_game_record.argtypes=[ctypes.c_uint8];lib.ff7_test_game_record.restype=ctypes.c_uint32
    disc=Disc(args.disc)
    try:
        boot=next(n for n in disc.files if n.startswith('SCUS_') and '/' not in n)
        exe=disc.read(boot);kernel=kernel_sections(disc.read('INIT/KERNEL.BIN'))
    finally:disc.reader.close()
    report=inspect(args.disc,boot)
    checked=json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/resident.evidence.json').read_text())
    assert report['sites']==checked['sites']
    count=0
    for guest in (0,7,9,10,11,12):
        vm=VM(lib,exe,kernel,report['sites'])
        vm.reg(4,guest);vm.run(0x800257cc)
        record=lib.ff7_test_game_record(guest)
        assert vm.reg(2)==record+0x10,(guest,hex(vm.reg(2)),hex(record))
        count+=1
        for pc,offset,table,stride in ((0x80025668,0x1d,0x80071e4d,36),
                                       (0x800256dc,0x1c,0x800738bc,44)):
            vm.write(0x8009cbdc,bytes([0,7,guest]));vm.reg(4,2);vm.run(pc)
            equipment=vm.read(record+offset,1)[0]
            assert vm.reg(2)==table+equipment*stride,(guest,hex(pc),hex(vm.reg(2)))
            count+=1
    # Real resident stat derivation and materia recalculation, including original
    # callees. Inspect record and native party separately; no graphics needed.
    stats=[]
    for guest in (0,7,10,11,12):
        vm=VM(lib,exe,kernel,report['sites'])
        vm.write(0x8009cbdc,bytes([0,7,guest]))
        record=lib.ff7_test_game_record(guest)
        # Use the legal original template for this profile, retaining its proxy.
        row=7 if guest>=10 else guest
        template=bytearray(kernel[3][row*132:(row+1)*132]);template[0]=guest
        vm.write(record,template)
        before=vm.read(0x8009c738,9*132)
        vm.reg(4,2);vm.run(0x80020058)
        vm.reg(4,2);vm.run(0x8001786c)
        after=vm.read(record,132)
        if guest>=11:assert vm.read(0x8009c738,9*132)==before
        hp,mp=struct.unpack_from('<HH',after,0x38)
        assert 0<hp<=9999 and 0<mp<=999,(guest,hp,mp)
        derived=vm.read(0x8009d84c+2*0x440,0x440)
        # Equivalent stock character path is the oracle for every derived field,
        # including materia AP and all base-record writes. Preserve only the
        # deliberate independent identity byte when normalizing the comparison.
        baseline=VM(lib,exe,kernel,report['sites'])
        baseline.sites={}
        native=10 if guest>=10 else guest
        native_record=0x8009c738+(7 if native==10 else native)*132
        template[0]=native
        baseline.write(native_record,template)
        baseline.write(0x8009cbdc,bytes([0,7,native]))
        baseline.reg(4,2);baseline.run(0x80020058)
        baseline.reg(4,2);baseline.run(0x8001786c)
        expected=bytearray(baseline.read(native_record,132));expected[0]=guest
        assert after==expected,(guest,after.hex(),expected.hex())
        original_derived=baseline.read(0x8009d84c+2*0x440,0x440)
        assert derived==original_derived,(guest,derived[:32].hex(),original_derived[:32].hex(),
            [(hex(i),a,b) for i,(a,b) in enumerate(zip(derived,original_derived)) if a!=b],vm.trace,baseline.trace)
        stats.append(dict(guest=guest,hp=hp,mp=mp,hooks=vm.hooks))
    result=dict(schema=1,status='original resident paths tested; battle/field/save lifecycle separate',
                disc=boot,guard_sites=len(report['sites']),accessor_cases=count,
                recalculation=stats)
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
