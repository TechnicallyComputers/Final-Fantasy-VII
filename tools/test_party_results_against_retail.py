"""Run original EXP-result tween, drawing and portrait-copy code with C adapters.

Drawing/BIOS services are recorded/stubbed; record lookup and result state
execute original owner-disc MIPS. Live GPU playback is separate acceptance.
"""
import argparse
import ctypes
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc,ROOT,kernel_sections
from inspect_ff7_results import inspect
from inspect_ff7_resident_party import inspect as inspect_resident
from unicorn import Uc,UC_ARCH_MIPS,UC_MODE_MIPS32,UC_MODE_LITTLE_ENDIAN,UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0,UC_MIPS_REG_PC

class VM:
    def __init__(self,lib,report,exe,kernel,hooked=True):
        self.lib=lib;lib.ff7_test_results_reset()
        self.uc=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
        self.uc.mem_map_ptr(0,0x200000,7,lib.ff7_test_results_ram())
        self.uc.mem_map_ptr(0x1f000000,0x20000,7,lib.ff7_test_results_expansion())
        self.write(0x80010000,exe[0x800:]);self.write(0x8009c738,kernel[3])
        self.sites={s['address']:s for s in report['sites']}if hooked else {}
        self.calls=[];self.rects=[];self.hooks=0;self.stubs=set()
        self.reg(28,0x80062d44);self.reg(29,0x801ff000)
        self.uc.hook_add(UC_HOOK_CODE,self.hook)
    def reg(self,n,v=None):
        if v is not None:self.uc.reg_write(UC_MIPS_REG_0+n,v&0xffffffff)
        return self.uc.reg_read(UC_MIPS_REG_0+n)
    def write(self,p,b):self.uc.mem_write(p&0x1fffffff,bytes(b))
    def read(self,p,n):return bytes(self.uc.mem_read(p&0x1fffffff,n))
    def word(self,p,v):self.write(p,struct.pack('<I',v))
    def stub(self,*pcs):
        for pc in pcs:self.stubs.add(pc);self.write(pc,struct.pack('<II',0x03e00008,0x00001021))
    def hook(self,uc,pc,size,_):
        if pc in self.stubs:
            self.calls.append((pc,tuple(self.reg(n)for n in range(4,8)),self.read(self.reg(29)+16,24)))
            if pc==0x800440c8:self.rects.append(struct.unpack('<4H',self.read(self.reg(4),8)))
        if pc not in self.sites:return
        r=(ctypes.c_uint32*32)(*(self.reg(n)for n in range(32)))
        self.lib.ff7_test_results_hook(pc,r)
        for n in range(1,32):
            if r[n]!=self.reg(n):self.reg(n,r[n])
        self.hooks+=1
    def run(self,pc):
        self.reg(31,0x80001000);self.uc.emu_start(pc,0x80001000,count=1000000)
        assert self.uc.reg_read(UC_MIPS_REG_PC)in(0x80001000,0x80000ffc)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--library',required=True,type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    lib=ctypes.CDLL(str(a.library.resolve()))
    for n in('ff7_test_results_ram','ff7_test_results_expansion'):getattr(lib,n).restype=ctypes.c_void_p
    lib.ff7_test_results_hook.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    report=inspect(a.disc);assert report==json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/results.evidence.json').read_text())
    d=Disc(a.disc)
    try:
        boot=next(n for n in d.files if n.startswith('SCUS_')and '/'not in n)
        exe=d.read(boot);kernel=kernel_sections(d.read('INIT/KERNEL.BIN'))
    finally:d.reader.close()
    report['sites']+=inspect_resident(a.disc,boot)['sites']
    cases=[]
    template=bytearray(kernel[3][7*132:8*132]);template[1]=50
    struct.pack_into('<I',template,0x3c,1500);struct.pack_into('<I',template,0x80,321)
    for guest in(11,26):
        for tween in(0,1):
            outputs=[]
            for identity in(7,guest):
                v=VM(lib,report,exe,kernel,hooked=identity>=11)
                for slot,g in enumerate((0,8,identity)):
                    record=0x8009c738+132*g if g<9 else 0x9f010000+132*(g-11)
                    data=bytearray(template);data[0]=g;v.write(record,data)
                    v.word(0x80075d04+slot*4,1600);v.word(0x80075d14+slot*4,1500)
                    v.word(0x80075d24+slot*0x30,1000)
                    v.write(0x80075d28+slot*0x30,struct.pack('<11I',*(1500+100*i for i in range(11))))
                    v.write(0x80075de8+slot,bytes([50]))
                v.write(0x8009cbdc,bytes([0,8,identity]));native=v.read(0x8009c738,9*132)
                v.word(0x80062e24,tween);v.reg(4,0);v.run(0x80015668)
                outputs.append((v.read(0x8009d7e8,36),v.read(0x80062e24,12),v.read(0x80075d04,0xe8)))
                assert v.read(0x8009c738,9*132)==native
                assert v.read(0x8009d7ed+24,1)!=b'\0'
            assert outputs[0]==outputs[1],(guest,tween,outputs)
            cases.append(f'full original EXP tween: proxy{guest}, phase{tween}, all3 party-slot buffers match native row7')
        v=VM(lib,report,exe,kernel)
        for g in(0,8,guest):
            r=0x8009c738+g*132 if g<9 else 0x9f010000+(g-11)*132
            data=bytearray(template);data[0]=g;v.write(r,data)
        v.write(0x8009cbdc,bytes([0,8,guest]));v.word(0x80062ea8,100) # gp+164
        for slot in range(3):
            v.write(0x8009d7ed+12*slot,b'\x32');v.write(0x8009d7ec+12*slot,b'\x20')
            v.word(0x8009d7e8+12*slot,1500);v.word(0x8009d7e4+12*slot,100)
        v.stub(0x80015668,0x8001fa28,0x8001faac,0x8001fa68,0x80015248,0x8004656c,
               0x80026a34,0x80026f44,0x80028e00,0x80028ca0,0x800285ac,0x8001cf3c,0x8001de0c,0x8001e040)
        v.reg(4,0);v.run(0x80021f58)
        name=0x9f010000+(guest-11)*132+16
        assert any(pc==0x80026f44 and r[2]==name for pc,r,_ in v.calls),(guest,v.calls)
        portraits=[(r,stack)for pc,r,stack in v.calls if pc==0x8001cf3c]
        assert len(portraits)==3 and struct.unpack_from('<I',portraits[2][1],16)[0]==15,(guest,portraits)
        cases.append(f'full original result draw: proxy{guest} own name and all3 rows, native party-slot CLUT15')
        v=VM(lib,report,exe,kernel);v.write(0x8009cbdc,bytes([0,8,guest]))
        v.stub(0x80043dd8,0x800440c8,0x80025cd4);v.run(0x80025ed4)
        copies=[(r,stack)for pc,r,stack in v.calls if pc==0x800440c8]
        assert len(copies)==6
        assert copies[4][0][1:3]==(960,408)and copies[5][0][1:3]==(256,495),copies
        assert v.rects[4:]==[(856,448,24,48),(384,9,256,1)],v.rects
        cases.append(f'original portrait copy: proxy{guest}, untouched native destination slot2')
    result={'schema':1,'status':'passed','disc':a.disc.name,'cases':cases,
            'limits':'Drawing/GPU and BIOS calls recorded; live result-screen acceptance separate. No assets emitted.'}
    if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
