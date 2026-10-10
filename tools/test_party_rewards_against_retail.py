"""Execute original owner-disc BATRES with the production guarded rewards adapter.

The active-award phase isolates resident AP delivery (separately adapted by the
resident module). Growth, RNG, record conversion, reserve awards and writeback
execute original instructions. This is not a live gameplay acceptance test.
"""
import argparse
import ctypes
import gzip
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, kernel_sections
from inspect_ff7_rewards import inspect
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0, UC_MIPS_REG_PC

class VM:
    def __init__(self,lib,report,exe,overlay,kernel,count=16,growth=0):
        self.lib=lib;lib.ff7_test_rewards_reset(count,growth)
        self.uc=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
        self.uc.mem_map_ptr(0,0x200000,7,lib.ff7_test_rewards_ram())
        self.uc.mem_map_ptr(0x1f000000,0x20000,7,lib.ff7_test_rewards_expansion())
        self.write(0x80010000,exe[0x800:]);self.write(0x801b0000,overlay)
        self.write(0x80082268,kernel[2]);self.write(0x8009c738,kernel[3])
        self.sites={s['address']:s for s in report['sites']};self.ap=[]
        self.uc.hook_add(UC_HOOK_CODE,self.hook)
        self.reg(28,0x80062d44);self.reg(29,0x801ff000)
        self.word(0x80062e18,0) # original RNG stream index (gp+0xd4)
    def reg(self,n,value=None):
        if value is not None:self.uc.reg_write(UC_MIPS_REG_0+n,value&0xffffffff)
        return self.uc.reg_read(UC_MIPS_REG_0+n)
    def write(self,a,b):self.uc.mem_write(a&0x1fffffff,bytes(b))
    def read(self,a,n):return bytes(self.uc.mem_read(a&0x1fffffff,n))
    def word(self,a,v):self.write(a,struct.pack('<I',v))
    def half(self,a,v):self.write(a,struct.pack('<H',v))
    def stub(self,*pcs):
        for pc in pcs:self.write(pc,struct.pack('<II',0x03e00008,0x00001021))
    def run(self,pc,end=0x80001000):
        self.reg(31,0x80001000);self.uc.emu_start(pc,end,count=2000000)
        assert self.uc.reg_read(UC_MIPS_REG_PC) in (end,end-4),hex(self.uc.reg_read(UC_MIPS_REG_PC))
    def hook(self,uc,pc,size,_):
        if pc==0x800a4acc:self.ap.append((self.reg(4),self.reg(5)))
        if pc not in self.sites:return
        regs=(ctypes.c_uint32*32)(*(self.reg(n)for n in range(32)))
        self.lib.ff7_test_rewards_hook(pc,regs)
        for n in range(1,32):
            if regs[n]!=self.reg(n):self.reg(n,regs[n])

def rec(g):return 0x8009c738+g*132 if g<9 else 0x9f010000+(g-11)*132
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--library',required=True,type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    lib=ctypes.CDLL(str(a.library.resolve()))
    for n in ('ff7_test_rewards_ram','ff7_test_rewards_expansion'):getattr(lib,n).restype=ctypes.c_void_p
    lib.ff7_test_rewards_hook.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    report=inspect(a.disc)
    assert report==json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/rewards.evidence.json').read_text())
    d=Disc(a.disc)
    try:
        exe=d.read(next(n for n in d.files if n.startswith('SCUS_')and '/'not in n))
        overlay=gzip.decompress(d.read('BATTLE/BATRES.X')[8:]);kernel=kernel_sections(d.read('INIT/KERNEL.BIN'))
    finally:d.reader.close()
    def vm(**kw):return VM(lib,report,exe,overlay,kernel,**kw)
    template=bytearray(kernel[3][7*132:8*132]);template[1]=1
    struct.pack_into('<I',template,0x3c,0)
    cases=[];growth_cases=0
    for row in (0,7,8):
        for exp in (0,1,10000,50000000,999999999):
            for g in (11,26):
                outputs=[]
                for identity in (row,g):
                    v=vm(growth=row);data=bytearray(template);data[0]=identity
                    v.write(rec(identity),data);native=v.read(0x8009c738,9*132)
                    v.reg(4,rec(identity));v.reg(5,exp);v.reg(6,0xffffffff);v.run(0x801b0ef8)
                    result=v.read(rec(identity),132);assert result[0]==identity
                    assert result[1]<=99 and int.from_bytes(result[0x2e:0x30],'little')<=9999
                    assert int.from_bytes(result[0x32:0x34],'little')<=999
                    if identity>=11:assert v.read(0x8009c738,9*132)==native
                    outputs.append(result[1:])
                assert outputs[0]==outputs[1],(row,exp,g)
                growth_cases+=1
    cases.append(f'{growth_cases} complete original growth differentials: rows0/7/8, proxies11/26, XP0..999999999, caps99/9999/999')
    for status in (0,1,0x4000):
        for g in (11,26):
            v=vm();v.stub(0x800a4acc);v.write(0x8009cbdc,bytes([0,7,g]))
            for slot,identity in enumerate((0,7,g)):
                data=bytearray(template);data[0]=identity;v.write(rec(identity),data)
                v.write(0x8009d84c+slot*0x440,b'\x10')
                v.word(0x800f83e0+slot*0x68,status if slot==2 else 0)
                v.write(0x800f5e67+slot*0x34,b'\x03')
            before=[v.read(rec(i),132)for i in range(9)]
            v.word(0x8009d7d8,10000);v.word(0x8009d7dc,123)
            v.word(v.reg(29)+0x18,0x1ff);v.run(0x801b07cc,0x801b0938)
            for i in range(9):
                if i not in (0,7):assert v.read(rec(i),132)==before[i]
            assert int.from_bytes(v.read(rec(g)+0x3c,4),'little')==(0 if status else 10000)
            assert int.from_bytes(v.read(rec(g)+0x24,2),'little')==int.from_bytes(template[0x24:0x26],'little')+3
            assert v.ap==[(0,123),(1,123)]+([]if status else[(2,123)])
    cases.append('6 original active-award phases: Cloud/Vincent/extra, award exactly once, death/petrify exclusion, kills, AP argument routing')
    for n in (1,16):
        v=vm(count=n);v.write(0x8009cbdc,bytes([0,7,11]));v.word(0x8009d7d8,10000)
        for i in range(n):
            data=bytearray(template);data[0]=11+i;v.write(rec(11+i),data)
        before=v.read(0x8009c738,9*132);v.reg(4,0);v.run(0x801b0d14)
        assert v.read(0x8009c738,9*132)==before
        for i in range(n):assert int.from_bytes(v.read(rec(11+i)+0x3c,4),'little')==(0 if i==0 else 5000)
    cases.append('complete reserve half-XP loop for1/16 extras; active extra excluded, native unavailable records untouched')
    for g in (11,26):
        v=vm();v.write(0x80163790,bytes([0,7,g]));v.write(0x8009cbdc,bytes([0,7,g]))
        for slot,identity in enumerate((0,7,g)):
            data=bytearray(template);data[0]=identity;v.write(rec(identity),data)
            v.word(0x800f840c+slot*0x68,321+slot);v.half(0x800f8408+slot*0x68,65+slot)
            v.word(0x800f83e0+slot*0x68,0x30);v.half(0x800f5e68+slot*0x34,200+slot)
        before=[v.read(rec(i),132)for i in range(9)]
        v.reg(4,0);v.reg(5,0);v.run(0x801b09c0)
        for slot,identity in enumerate((0,7,g)):
            assert v.read(rec(identity)+0x2c,2)==struct.pack('<H',321+slot)
            assert v.read(rec(identity)+0x30,2)==struct.pack('<H',65+slot)
            assert v.read(rec(identity)+0x1f,1)==b'\x30';assert v.read(rec(identity)+0xf,1)==bytes([200+slot])
        for i in range(9):
            if i not in(0,7):assert v.read(rec(i),132)==before[i]
        backup=bytes([g])+bytes((i*17)&255 for i in range(1,132));v.write(0x80167938,backup)
        native=v.read(0x8009c738,9*132);v.half(0x8016376a,0x40);v.reg(4,0);v.reg(5,0);v.run(0x801b09c0)
        assert v.read(rec(g),132)==backup;assert v.read(0x8009c738,9*132)==native
    cases.append('whole HP/MP/status/limit-meter writeback and flagged132-byte backup restore for proxies11/26 alongside Cloud/Vincent')
    output={'disc':a.disc.name,'cases':cases,'status':'passed','limits':'Isolated original-MIPS oracle; AP implementation covered by resident module; live results UI and gameplay acceptance pending'}
    if a.output:a.output.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))
if __name__=='__main__':main()
