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
from collections import Counter
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
        self.sites={}
        resident=json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/resident.evidence.json').read_text())
        for s in report['sites']+resident['sites']:self.sites.setdefault(s['address'],[]).append(s)
        self.capture=set();self.trace=[]
        self.calls=[]; self.hooks=0
        self.uc.hook_add(UC_HOOK_CODE,self.hook)
        self.reg(29,0x801b0000);self.reg(31,0x80001000)
    def reg(self,r,v=None):
        if v is not None:self.uc.reg_write(UC_MIPS_REG_0+r,v&0xffffffff)
        return self.uc.reg_read(UC_MIPS_REG_0+r)
    def write(self,a,b):self.uc.mem_write(a&0x1fffffff,bytes(b))
    def word(self,a,v):self.write(a,struct.pack('<I',v))
    def read(self,a,n):return bytes(self.uc.mem_read(a&0x1fffffff,n))
    def stub(self,*addresses):
        for a in addresses:self.write(a,struct.pack('<II',0x03e00008,0))
    def run(self,start,end=0x80001000,count=100000):
        self.uc.emu_start(start,end,count=count)
        assert self.uc.reg_read(UC_MIPS_REG_PC) in (end,end-4),hex(self.uc.reg_read(UC_MIPS_REG_PC))
    def hook(self,uc,pc,size,_):
        if pc in self.capture:self.trace.append((pc,tuple(self.reg(r)for r in range(4,8)),self.read(self.reg(29)+16,12)))
        if pc not in self.sites:return
        # Full menus overlap. Runtime contexts distinguish the active overlay.
        if not any(self.read(pc-24,52)==struct.pack('<13I',*s['guard'])for s in self.sites[pc]):return
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
        status=disc.read('MENU/STATMENU.MNU')
        item_overlay=disc.read('MENU/ITEMMENU.MNU');magic_overlay=disc.read('MENU/MGICMENU.MNU')
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
    # Execute complete STAT gear, EXP/limit and derived-stat drawing functions.
    # Capture only rendering/name-lookup leaves; all native address arithmetic,
    # status-color branches and kernel equipment contributions remain original.
    status_cases=0
    leaves=(0x80021280,0x80026f44,0x801d0964,0x800285ac,0x80015248,0x80028ca0,0x80028e00,0x80026a34)
    def status_vm(guest,slot,gauge,condition):
        v=VM(lib,report,status,exe,kernel,16);v.stub(*leaves);v.capture=set(leaves)
        v.write(0x8009cbdc,bytes([0,7,1]));v.write(0x8009cbdc+slot,bytes([guest]));v.word(0x801d1e1c,slot)
        for g in range(9):
            r=bytearray(132);r[0]=g;r[14]=1;r[15]=4;r[0x1e]=255
            struct.pack_into('<II',r,0x3c,642+g,0);v.write(0x8009c738+132*g,r)
        rec=0x8009c738+132*(7 if guest==10 else guest)if guest<11 else 0x9f010000+132*(guest-11)
        r=bytearray(132);r[0]=guest;r[14]=3;r[15]=gauge;r[0x1c:0x1f]=bytes([127,10,3]);r[0x1f]=condition;r[0x21]=87
        struct.pack_into('<I',r,0x3c,320438);struct.pack_into('<I',r,0x80,15493)
        v.write(rec,r)
        for s in range(3):
            derived=bytearray(0x440);derived[2:8]=bytes([21+s,31+s,41+s,51+s,61+s,71+s]);struct.pack_into('<4H',derived,8,177+s,129+s,153+s,164+s)
            v.write(0x8009d84c+s*0x440,derived)
        return v,rec
    for slot in range(3):
        for gauge,condition in((255,0),(73,0),(73,16),(73,32)):
            baseline=None
            for guest in(7,10,11,26):
                v,rec=status_vm(guest,slot,gauge,condition)
                native=v.read(0x8009c738,9*132);extra=v.read(0x9f010000,16*132);derived=v.read(0x8009d84c,3*0x440)
                v.reg(4,8);v.reg(5,70);v.run(0x801d0b74)
                assert [regs[0]for pc,regs,stack in v.trace if pc==0x80021280]==[255,266,291]
                assert [regs[3]for pc,regs,stack in v.trace if pc==0x801d0964]==[rec+0x40,rec+0x60]
                v.trace=[];v.reg(4,8);v.run(0x801d116c)
                assert [regs[2]for pc,regs,stack in v.trace if pc==0x80028e00]==[320438,15493,3]
                bars=[(regs[2],stack)for pc,regs,stack in v.trace if pc==0x800285ac]
                assert bars[0][0]==61*gauge//256 and bars[1][0]==87
                v.trace=[];v.reg(4,8);v.reg(5,70);v.run(0x801d0d28)
                numbers=[regs[2]for pc,regs,stack in v.trace if pc==0x80028e00]
                if baseline is None:baseline=(numbers,bars)
                else:assert (numbers,bars)==baseline,(guest,slot,numbers,baseline)
                assert v.read(0x8009c738,9*132)==native and v.read(0x9f010000,16*132)==extra
                assert v.read(0x8009d84c,3*0x440)==derived and v.read(0x801d1e1c,4)==struct.pack('<I',slot)
                status_cases+=1
    cases.append(f'{status_cases} whole original STAT gear/EXP/limit/status/derived-stat drawing paths: nativeVincent,flashback10,extra11/26 across3 slots and4 gauge/status branches; own equipment/materia/EXP agree with equivalent native records, all records and derived caches unchanged')
    def actual_record(g):return 0x8009c738+132*(g if g<9 else g-3)if g<11 else 0x9f010000+132*(g-11)
    def heal_vm(overlay,guest):
        v=VM(lib,report,overlay,exe,kernel,16);v.write(0x8009cbdc,bytes([0,guest,7]))
        for g in range(9):v.write(0x8009c738+132*g,bytes([g])+b'\0'*131)
        for slot,g in enumerate((0,guest,7)):
            rec=actual_record(g);v.write(rec,bytes([g,50]));v.write(rec+0x2c,struct.pack('<4H',1000,9999,100,600))
            derived=0x8009d84c+slot*0x440;v.write(derived+0x10,struct.pack('<4H',1000,9999,100,600));v.write(derived+0xc,struct.pack('<H',129))
        return v
    item_cases=0
    for guest in(0,7,11,26):
        for item_id in(0,1,3,4,13,14,71,72,73,74,75,76):
            v=heal_vm(item_overlay,guest);v.stub(0x801d01e8,0x80020058,0x8001786c)
            v.write(0x8009cbe0,b'\xff'*640);v.write(0x8009cbe0,struct.pack('<H',item_id|(10<<9)))
            v.write(0x801d3e0b,b'\1');v.write(0x80062d7c,b'\x20\0');rec=actual_record(guest)
            native=bytearray(v.read(0x8009c738,9*132));extra=bytearray(v.read(0x9f010000,16*132));inventory=v.read(0x8009cbe0,640)
            v.run(0x801d1c08,0x801d293c)
            region,base=(native,0x8009c738)if guest<11 else(extra,0x9f010000)
            if item_id in(0,1):struct.pack_into('<H',region,rec-base+0x2c,1000+(100 if item_id==0 else 500))
            elif item_id in(3,4):struct.pack_into('<H',region,rec-base+0x30,200 if item_id==3 else 600)
            elif item_id in(13,14):region[rec-base+0x1f]=32 if item_id==13 else 16
            else:region[rec-base+8+item_id-71]=1
            assert v.read(0x8009c738,9*132)==native,(guest,item_id,'native')
            assert v.read(0x9f010000,16*132)==extra,(guest,item_id,'extra')
            assert v.read(0x8009cbe0,640)==struct.pack('<H',item_id|(9<<9))+inventory[2:]
            item_cases+=1
    cases.append(f'{item_cases} original ITEM confirm+dispatch paths execute Potion/Hi-Potion/Ether/Turbo Ether,Hyper/Tranquilizer and all6 Sources with real resident HP/MP writes and native inventory consumption; only selected native/extra record changes')
    magic_cases=0
    for guest in(7,10,11,26):
        for start,constant,all_targets in((0x801d1b30,110,False),(0x801d1c44,660,False),(0x801d1d58,1760,False),
                                         (0x801d2090,110,True),(0x801d2218,660,True),(0x801d23a0,1760,True)):
            v=heal_vm(magic_overlay,guest);v.word(0x801d2ae8,1);v.write(0x801d2a99,b'\0');v.reg(17,0x801d2a99)
            v.reg(22,0);v.word(v.reg(29)+0x40,0x801e0000);v.write(0x801e0001,b'\5')
            before_native=v.read(0x8009c738,9*132);before_extra=v.read(0x9f010000,16*132)
            v.run(start,0x801d28ec)
            power=((129+50)*12+2*constant)//3 if all_targets else (129+50)*6+constant
            assert struct.unpack('<H',v.read(actual_record(guest)+0x30,2))[0]==(100 if guest==10 else 95),(guest,hex(start),'MP')
            for slot,g in enumerate((0,guest,7)):
                expected=1000+(power if all_targets or slot==0 else 0)
                # Native7 appears twice in this intentionally aliased baseline;
                # its final cached HP remains equal for both slots.
                assert struct.unpack('<H',v.read(0x8009d85c+slot*0x440,2))[0]==expected,(guest,hex(start),slot)
                assert struct.unpack('<H',v.read(actual_record(g)+0x2c,2))[0]==expected,(guest,hex(start),g,'recordHP')
            if guest>=11:
                wanted=bytearray(before_extra);struct.pack_into('<H',wanted,132*(guest-11)+0x30,95)
                if all_targets:struct.pack_into('<H',wanted,132*(guest-11)+0x2c,1000+power)
                assert v.read(0x9f010000,16*132)==wanted
                wanted=bytearray(before_native)
                for g in([0,7]if all_targets else[0]):struct.pack_into('<H',wanted,132*g+0x2c,1000+power)
                assert v.read(0x8009c738,9*132)==wanted
            magic_cases+=1
    cases.append(f'{magic_cases} original MGIC Cure/Cure2/Cure3 single/all branches use own level+derived magic attack,spend own MP and write healed HP through real resident adapters; native flashback10 free-MP exception preserved')
    for guest in(0,7,11,26):
        v=heal_vm(item_overlay,guest);rec=actual_record(guest)
        v.write(0x8009cbe0,b'\xff'*640);v.write(0x8009ce60,b'\xff'*800)
        materia=struct.pack('<16I',*(0x12340000+i for i in range(1,17)));v.write(rec+0x40,materia);v.write(rec+0x1e,b'\3')
        native=bytearray(v.read(0x8009c738,9*132));extra=bytearray(v.read(0x9f010000,16*132))
        v.reg(4,guest);v.run(0x801d2f00)
        region,base=(native,0x8009c738)if guest<11 else(extra,0x9f010000)
        region[rec-base+0x40:rec-base+0x80]=b'\xff'*64;region[rec-base+0x1e]=255
        assert v.read(0x8009c738,9*132)==native and v.read(0x9f010000,16*132)==extra
        assert v.read(0x8009ce60,800)==materia+b'\xff'*(800-64)
        assert v.read(0x8009cbe0,640)==struct.pack('<H',512+0x123)+b'\xff'*638
        # Temporary party/equipment/materia backup helper keeps its original
        # native scratch contract; the paired restore must restore every byte.
        v=heal_vm(item_overlay,guest);rec=actual_record(guest);v.write(rec+0x1c,bytes([127,10]));v.write(rec+0x40,materia)
        v.write(0x8009ce60,struct.pack('<3I',0x12345601,0x45678902,0x89abcd03))
        native=v.read(0x8009c738,9*132);extra=v.read(0x9f010000,16*132);party=v.read(0x8009cbdc,3);bag=v.read(0x8009ce60,800)
        v.reg(4,guest);v.run(0x801d3018)
        assert v.read(rec+0x40,64)==b'\xff'*64 and v.read(rec+0x1c,1)==b'\0'
        assert v.read(0x8009d180,3)==party
        v.reg(4,guest);v.run(0x801d3138)
        assert v.read(0x8009c738,9*132)==native and v.read(0x9f010000,16*132)==extra
        assert v.read(0x8009cbdc,3)==party and v.read(0x8009ce60,800)==bag
    cases.append('Original ITEM single-record unequip returns all16 materia/AP words and accessory to native inventories; paired party/equipment/materia backup+restore round-trips native0/7 and extras11/26 without altering other records')
    # Wutai story mode15/16: original rank selection, exact-word removal,
    # native bank and return policy, with only the guarded roster loops extended.
    story_cases=0
    for extras in (0,1,16):
        for available in (0,0x81,0x1ff):
            for total in (12,72):
                v=VM(lib,report,item_overlay,exe,kernel,extras)
                records=[0x8009c738+132*i for i in range(9)]+[0x9f010000+132*i for i in range(extras)]
                for i,rec in enumerate(records):
                    v.write(rec,bytes([i])+b'\0'*131)
                    v.write(rec+0x1c,bytes([127,10])) # valid native slot descriptors
                    v.write(rec+0x40,b'\xff'*64)
                v.write(0x8009ce60,b'\xff'*800);v.write(0x8009d78a,struct.pack('<H',available))
                addresses=[rec+0x40+4*j for rec in records for j in range(16)]
                # Spread packed words across native, extra and bag, including
                # exact duplicates; unselected native records are sentinels too.
                positions=[rec+0x40+4*j for j in range(4) for rec in records]
                positions += [0x8009ce60+4*j for j in range(200)]
                for i,pos in enumerate(positions[:total]):
                    serial=i//2;v.word(pos,((serial+100)<<8)|(serial%70))
                if extras==16:
                    ranks=v.read(0x801d3834,256);best=max(range(90),key=lambda x:ranks[x])
                    v.word(records[-1]+0x40,0x12340000|best)
                native_before=v.read(0x8009c738,9*132)
                def words(places):return [struct.unpack('<I',v.read(p,4))[0]for p in places]
                def owned():return Counter(x for x in words(addresses+[0x8009ce60+4*j for j in range(200)])if x!=0xffffffff)
                eligible=[rec+0x40+4*j for i,rec in enumerate(records)if i>=9 or available&(1<<i) for j in range(16)]
                eligible += [0x8009ce60+4*j for j in range(200)]
                eligible_words=[x for x in words(eligible)if x!=0xffffffff]
                stock_snapshot=v.read(0,0x200000)if not extras else None
                before=owned();v.run(0x801d2d74,count=3000000)
                stolen=[x for x in words([0x8009d180+4*j for j in range(48)])if x!=0xffffffff]
                assert len(stolen)==min(48,len(eligible_words)),(extras,available,total,len(stolen))
                assert owned()+Counter(stolen)==before,(extras,available,total,'theft conservation')
                ranks=v.read(0x801d3834,256)
                expected_ranks=sorted((ranks[x&255]for x in eligible_words),reverse=True)[:48]
                assert sorted((ranks[x&255]for x in stolen),reverse=True)==expected_ranks
                # The original8->0 return priority wins before any extra slot.
                v.reg(31,0x80001000);v.run(0x801d2e84,count=3000000)
                assert owned()==before,(extras,available,total,'return conservation')
                if available and total==12 and stolen:
                    last_native=max(i for i in range(9)if available&(1<<i))
                    assert struct.unpack('<I',v.read(records[last_native]+0x40,4))[0]==stolen[0]

                for i in range(9):
                    if not available&(1<<i):assert v.read(records[i],132)==native_before[132*i:132*(i+1)]
                if not available and extras and stolen:
                    # Registered independent records have real equipment slots;
                    # mode16 must use them before its original bag fallback.
                    assert v.read(records[9]+0x40,4)!=b'\xff'*4
                assert v.read(0x8009d78a,2)==struct.pack('<H',available)
                if not extras:
                    spans=((0x8009c738,9*132),(0x8009ce60,800),(0x8009d180,192))
                    expected=[v.read(p,n)for p,n in spans]
                    baseline=VM(lib,report,item_overlay,exe,kernel,0);baseline.sites={}
                    baseline.write(0,stock_snapshot);baseline.run(0x801d2d74,count=3000000)
                    baseline.reg(31,0x80001000);baseline.run(0x801d2e84,count=3000000)
                    assert [baseline.read(p,n)for p,n in spans]==expected
                story_cases+=1
    cases.append(f'{story_cases} original Wutai mode15/16 whole theft+return transactions:0/1/16 extras,native availability masks,under/over48 candidates,rank cutoff,exact packed-AP duplicates; materia multiset conserved and unavailable native records untouched')
    for guest in(11,26):
        for item_id in range(87,95):
            v=heal_vm(item_overlay,guest);v.stub(0x801d01e8,0x801d0e4c,0x8001f6c0);v.capture={0x801d0e4c}
            v.write(0x8009cbe0,b'\xff'*640);v.write(0x8009cbe0,struct.pack('<H',item_id|(10<<9)))
            v.write(0x801d3e0b,b'\1');v.write(0x80062d7c,b'\x20\0')
            native=v.read(0x8009c738,9*132);extra=v.read(0x9f010000,16*132);inventory=v.read(0x8009cbe0,640)
            v.run(0x801d1c08,0x801d293c)
            pointers=[regs[0]for pc,regs,stack in v.trace if pc==0x801d0e4c]
            assert len(pointers)==1 and v.read(pointers[0],22)==bytes(ord(c)-32 for c in 'Cannot use this item.')+b'\xff',(guest,item_id,pointers)
            assert v.read(0x8009c738,9*132)==native and v.read(0x9f010000,16*132)==extra and v.read(0x8009cbe0,640)==inventory
    cases.append('All8 stock final-limit manuals reject extra11/26 without consuming inventory or modifying learned bits; bounded authored refusal replaces unsafe raw-proxy-indexed native message')
    output={'schema':1,'status':'menu-paths-tested; resident/battle/field integration separate',
            'menus':report['menus'],'guard_sites':len(report['sites']),'passed':cases}
    if args.output:args.output.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))
if __name__=='__main__':main()
