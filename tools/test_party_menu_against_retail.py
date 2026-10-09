"""Execute original owner-disc menu routines with the real C hook adapter.

Only rendering/audio/stat recalculation callees are stubbed in the isolated VM;
original PHS selection/locks/enumeration, equipment compatibility/list loops,
weapon/accessory inventory transactions and materia roster execution run MIPS.
This is menu-path validation, not an end-to-end playable-game claim.
"""
import argparse
import ctypes
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, kernel_sections
from inspect_ff7_menus import inspect
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0, UC_MIPS_REG_PC

class VM:
    def __init__(self, library, report, data, exe, kernel, extras=1):
        self.lib=library; self.lib.ff7_test_menu_reset(extras)
        self.ram=self.lib.ff7_test_menu_ram(); self.exp=self.lib.ff7_test_menu_expansion()
        self.uc=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
        # Share the test bridge's backing bytes. Host data writes must not call
        # Unicorn mem_write during a code hook (which invalidates its block).
        self.uc.mem_map_ptr(0,0x200000,7,self.ram)
        self.uc.mem_map_ptr(0x1f000000,0x20000,7,self.exp)
        self.uc.mem_write(0x10000,exe[0x800:]);self.uc.mem_write(0x1d0000,data)
        self.uc.mem_write(0x71e44,kernel[6]);self.uc.mem_write(0x738a0,kernel[5])
        self.uc.mem_write(0x491d0,struct.pack('<11I',0,1,2,3,4,5,6,7,8,6,7))
        self.sites={s['address']:s for s in report['sites']}
        self.calls=[]; self.hooks=0
        self.uc.hook_add(UC_HOOK_CODE,self.hook)
        self.reg(29,0x801b0000);self.reg(31,0x80001000)
    def reg(self,r,v=None):
        if v is not None:self.uc.reg_write(UC_MIPS_REG_0+r,v&0xffffffff)
        return self.uc.reg_read(UC_MIPS_REG_0+r)
    def write(self,a,b):self.uc.mem_write(a&0x1fffffff,b)
    def word(self,a,v):self.write(a,struct.pack('<I',v))
    def read(self,a,n):return bytes(self.uc.mem_read(a&0x1fffffff,n))
    def stub(self,*addresses):
        for a in addresses:self.write(a,struct.pack('<II',0x03e00008,0))
    def run(self,start,end=0x80001000,count=100000):
        self.uc.emu_start(start,end,count=count)
        assert self.uc.reg_read(UC_MIPS_REG_PC) in (end,end-4),hex(self.uc.reg_read(UC_MIPS_REG_PC))
    def hook(self,uc,pc,size,_):
        if pc not in self.sites:return
        s=self.sites[pc]
        # Full menus overlap. Runtime contexts distinguish the active overlay.
        if self.read(pc-24,52)!=struct.pack('<13I',*s['guard']):return
        regs=(ctypes.c_uint32*32)(*(self.reg(r) for r in range(32)))
        self.lib.ff7_test_menu_hook(pc,regs)
        for r in range(1,32):
            if self.reg(r)!=regs[r]:self.reg(r,regs[r])
        self.hooks+=1

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',required=True,type=Path)
    parser.add_argument('--disc',required=True,type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    lib=ctypes.CDLL(str(args.library.resolve()))
    for n in ('ff7_test_menu_ram','ff7_test_menu_expansion'):getattr(lib,n).restype=ctypes.c_void_p
    lib.ff7_test_menu_hook.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    lib.ff7_test_menu_portrait.argtypes=[ctypes.c_void_p]
    report=inspect(args.disc);disc=Disc(args.disc)
    try:
        exe=disc.read(next(n for n in disc.files if n.startswith('SCUS_') and '/' not in n))
        kernel=kernel_sections(disc.read('INIT/KERNEL.BIN'))
        phs=disc.read('MENU/FORMMENU.MNU');equip=disc.read('MENU/EQIPMENU.MNU')
        portrait=disc.read('MENU/PCEFI.TIM')
    finally:disc.reader.close()
    # Confirm checked-in guards match this disc, including neighboring words.
    checked=json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/menu.evidence.json').read_text())
    assert report==checked
    cases=[]
    vm=VM(lib,report,phs,exe,kernel)
    lib.ff7_test_menu_portrait(portrait)
    vm.write(0x9cbdc,bytes([0,7,1]));vm.write(0x9d78a,b'\xff\x01')
    vm.stub(0x80020058,0x8001786c,0x80025b8c,0x80025c14,0x80025df8,
            0x80025c94,0x80025cd4,0x80025bd0,0x80025c54,0x80025bf0,
            0x80026448,0x80025bb0)
    # Run the real enumeration loop through the adapter, without unrelated GPU
    # initialization. Its first instruction sets s0=0, v1=reserve-grid pointer.
    vm.write(0x1d3424,b'\xff'*9)
    vm.reg(16,0);vm.reg(3,0x801d3424);vm.reg(4,0x8009cbdc)
    vm.run(0x801d0da8,0x801d0e0c)
    roster=list(vm.read(0x1d3424,9));assert roster==[2,3,4,5,6,8,11,255,255],roster
    cases.append('PHS native availability enumeration + independent added row')
    vm.stub(0x801d0198,0x80020058,0x8001786c)
    vm.word(0x1d2038,1);vm.write(0x1d2129,b'\x02');vm.write(0x1d2128,b'\0')
    vm.reg(31,0x80001000)
    vm.run(0x801d08e0)
    vm.word(0x1d2038,0);vm.write(0x1d2117,b'\x02');vm.reg(31,0x80001000)
    vm.run(0x801d0a00)
    assert vm.read(0x9cbdc,3)==bytes([0,7,11]);assert vm.read(0x1d342a,1)==b'\x01'
    assert lib.ff7_test_menu_observed()==1
    cases.append('PHS real two-click swap: Cloud/Vincent/Sephiroth coexist')
    # Locked active extra must fail its first click with no selected-pointer or
    # active-party mutation. This uses the original native lock mask bit11.
    vm.write(0x9d788,struct.pack('<H',1<<11));vm.word(0x1d3444,0x12345678)
    vm.reg(31,0x80001000);vm.run(0x801d08e0)
    assert vm.read(0x1d3444,4)==struct.pack('<I',0x12345678)
    assert vm.read(0x9cbdc,3)==bytes([0,7,11])
    cases.append('PHS original lock-bit rejection')
    # Original full materia-exchange roster initializer with UI-only callee stub.
    for count in (1,16):
        vm=VM(lib,report,equip,exe,kernel,count)
        vm.stub(0x80026448);vm.write(0x9d78a,b'\xff\x01')
        native_guard=vm.read(0x1df6ec,32)
        vm.run(0x801d5194)
        assert vm.read(0x1df6e8,1)==bytes([9+count])
        assert vm.read(0x1f000090,9+count)==bytes(list(range(9))+list(range(11,11+count)))
        assert vm.read(0x1df6ec,32)==native_guard
    cases.append('Original materia-exchange initializer:10/25 rows, adjacent globals intact')
    # Real inventory listing scans all320 items and applies original masks.
    for guest in (0,7,10,11,12):
        for category,ident in ((0,127),(1,6),(2,0)):
            vm=VM(lib,report,equip,exe,kernel,2)
            vm.write(0x9cbdc,bytes([guest,0,7]));vm.word(0x1d8ae8,0)
            vm.write(0x9cbe0,b'\xff'*640)
            item=ident+(0x80,0x100,0x120)[category]
            vm.write(0x9cbe0,struct.pack('<H',0x200|item))
            if category==2:vm.write(0x71c30,struct.pack('<H',1))
            vm.reg(4,category);vm.run(0x801d0314,0x801d0534)
            compat=10 if guest==11 and category==0 else 0 if guest in (11,12) else guest
            masks=(struct.unpack_from('<H',kernel[5],127*44+14)[0],
                   struct.unpack_from('<H',kernel[6],6*36+18)[0],1)
            expected=(masks[category]>>compat)&1
            assert vm.reg(5)==expected,(guest,category,vm.reg(5),expected)
            assert vm.read(0x9cbe0,2)==struct.pack('<H',0x200|item)
    cases.append('15 original inventory-list eligibility cases, native/flashback masks intact')
    # Weapon/accessory commit MIPS, including original add/remove item routines.
    for guest in (0,7,11,12):
        for offset,start,new,category in ((0x1c,0x801d1990,127,0x80),(0x1e,0x801d1ae4,2,0x120)):
            vm=VM(lib,report,equip,exe,kernel,2)
            record=0x8009c738+guest*132 if guest<11 else 0x9f010000+(guest-11)*132
            vm.write(0x9c738,bytes((i*3)&255 for i in range(9*132)))
            before=vm.read(0x9c738,9*132)
            vm.write(record,bytes(132));vm.write(record+0x40,b'\xff'*64)
            vm.write(record+offset,b'\x01')
            vm.write(0x9cbe0,b'\xff'*640);vm.write(0x9cbe0,struct.pack('<H',0x200|category|new))
            vm.reg(22,guest);vm.reg(2,guest*32);vm.reg(30,0x8009c738);vm.reg(18,new);vm.reg(21,1)
            vm.run(start,0x801d1b18)
            assert vm.read(record+offset,1)==bytes([new])
            inventory=struct.unpack('<320H',vm.read(0x9cbe0,640))
            assert (0x200|category|1) in inventory and (0x200|category|new) not in inventory
            if guest>=11:assert vm.read(0x9c738,9*132)==before
    cases.append('8 original weapon/accessory commit transactions preserve independent/native records and inventory')
    transfers=0
    for source,destination in ((11,0),(7,11),(11,12),(26,7),(0,26)):
        for source_bank in (0,1):
            for destination_bank in (0,1):
                vm=VM(lib,report,equip,exe,kernel,16)
                vm.write(0x1f000090,bytes(list(range(9))+list(range(11,27))))
                record=lambda g:0x8009c738+g*132 if g<11 else 0x9f010000+(g-11)*132
                row=lambda g:g if g<11 else g-2
                for g in list(range(9))+list(range(11,27)):
                    vm.write(record(g),bytes([g])*132)
                vm.word(0x1df6e4,row(source));vm.word(0x1df6e0,source_bank)
                vm.word(0x1df6dc,2);vm.word(0x1d88c8,row(destination));vm.word(0x1d88c4,0)
                vm.word(0x1d88c0,0);vm.write(0x1df673,bytes([destination_bank]));vm.write(0x1df672,b'\x03')
                a=record(source)+0x40+32*source_bank+8
                b=record(destination)+0x40+32*destination_bank+12
                vm.word(a,0x12345601);vm.word(b,0xabcdef02)
                native=bytearray(vm.read(0x9c738,9*132));extra=bytearray(vm.read(0x1f010000,16*132))
                for address,value in ((a,0xabcdef02),(b,0x12345601)):
                    region,base=(native,0x8009c738) if address<0x9f000000 else (extra,0x9f010000)
                    struct.pack_into('<I',region,address-base,value)
                vm.run(0x801d6194,0x801d6328)
                assert vm.read(0x9c738,9*132)==native
                assert vm.read(0x1f010000,16*132)==extra
                transfers+=1
    cases.append(f'{transfers} original cross-character weapon/armor materia swaps preserve full AP words and all other records')
    output={'schema':1,'status':'menu-paths-tested; resident/battle/field integration separate',
            'menus':report['menus'],'guard_sites':len(report['sites']),'passed':cases}
    if args.output:args.output.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))
if __name__=='__main__':main()
