"""Compare the production checksum/preview adapter with original PSX code.

Owner-disc assets stay local. This tests original instructions and C hooks;
BIOS file I/O and a live save-menu playthrough remain separate validation.
"""
import argparse
import ctypes
import json
import random
import struct
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, image_data, kernel_sections
from inspect_ff7_game_save import inspect
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0, UC_MIPS_REG_PC

class VM:
    def __init__(self, lib, exe, menu, kernel, sites):
        self.lib=lib;lib.ff7_test_game_save_reset()
        self.uc=Uc(UC_ARCH_MIPS, UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
        self.uc.mem_map_ptr(0, 0x200000, 7, lib.ff7_test_game_save_ram())
        self.uc.mem_map_ptr(0x1f000000, 0x10000, 7, lib.ff7_test_game_save_expansion())
        for name, raw in (('SCUS_941.63',exe),('MENU/SAVEMENU.MNU',menu)):
            data, base=image_data(name,raw);self.write(base,data)
        self.write(0x8009c738,kernel[3]);self.sites={s['address']:s for s in sites};self.hooks=0
        self.uc.hook_add(UC_HOOK_CODE,self.hook)
        self.reg(28,0x80062d44);self.reg(29,0x801a0000)
    def reg(self,n,value=None):
        if value is not None:self.uc.reg_write(UC_MIPS_REG_0+n,value&0xffffffff)
        return self.uc.reg_read(UC_MIPS_REG_0+n)
    def write(self,p,data):self.uc.mem_write(p&0x1fffffff,bytes(data))
    def read(self,p,size):return bytes(self.uc.mem_read(p&0x1fffffff,size))
    def hook(self,uc,pc,size,_):
        if pc not in self.sites:return
        s=self.sites[pc];assert self.read(pc-24,52)==struct.pack('<13I',*s['guard'])
        regs=(ctypes.c_uint32*32)(*(self.reg(n) for n in range(32)))
        self.lib.ff7_test_game_save_hook(pc,regs)
        for n in range(1,32):
            if regs[n]!=self.reg(n):self.reg(n,regs[n])
        self.hooks+=1
    def run(self,pc):
        self.reg(31,0x80001000);self.uc.emu_start(pc,0x80001000,count=1000000)
        assert self.uc.reg_read(UC_MIPS_REG_PC) in (0x80001000,0x80000ffc)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--library',type=Path,required=True)
    p.add_argument('--disc',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    lib=ctypes.CDLL(str(a.library.resolve()))
    for name in ('ff7_test_game_save_ram','ff7_test_game_save_expansion'):getattr(lib,name).restype=ctypes.c_void_p
    lib.ff7_test_game_save_hook.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    lib.ff7_native_save_checksum.argtypes=[ctypes.c_void_p];lib.ff7_native_save_checksum.restype=ctypes.c_uint16
    disc=Disc(a.disc)
    try:
        boot=next(n for n in disc.files if n.startswith('SCUS_') and '/' not in n)
        exe=disc.read(boot);menu=disc.read('MENU/SAVEMENU.MNU');kernel=kernel_sections(disc.read('INIT/KERNEL.BIN'))
    finally:disc.reader.close()
    evidence=inspect(a.disc);checked=json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/game-save.evidence.json').read_text())
    assert evidence['sites']==checked['sites']
    checksums=[];rng=random.Random(94163)
    for index in range(8):
        vm=VM(lib,exe,menu,kernel,[])
        data=bytearray(rng.randbytes(4340)) if index else bytearray(4340)
        vm.write(0x8009c6e4,data);vm.reg(4,4336);vm.reg(5,0x8009c6e8);vm.run(0x801d1950)
        expected=lib.ff7_native_save_checksum(bytes(data))
        assert vm.reg(2)==expected,(index,vm.reg(2),expected)
        checksums.append(expected)
    previews=[]
    for guest in (0,7,11):
        vm=VM(lib,exe,menu,kernel,evidence['sites'])
        row=7 if guest==11 else guest
        template=kernel[3][row*132:(row+1)*132]
        vm.write(0x80140000,template)
        vm.write(0x8009cbdc,bytes([guest,255,255]));vm.write(0x8009d85c,struct.pack('<4H',321,456,78,123))
        vm.run(0x801d224c);actual=vm.read(0x8009c6e8,28);hooks=vm.hooks
        baseline=VM(lib,exe,menu,kernel,[])
        baseline.write(0x8009cbdc,bytes([row,255,255]));baseline.write(0x8009d85c,struct.pack('<4H',321,456,78,123))
        baseline.run(0x801d224c);expected=bytearray(baseline.read(0x8009c6e8,28));expected[1]=guest
        assert actual==expected,(guest,actual.hex(),expected.hex())
        previews.append(dict(guest=guest,hooks=hooks))
    result=dict(schema=1,disc=boot,checksum_cases=checksums,preview_cases=previews,
        scope='Original SAVEMENU checksum and full preview function; synthetic card lifecycle C tests separate; live BIOS save UI pending')
    if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
