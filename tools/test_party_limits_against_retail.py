"""Original PSX limit lookup, menu, battle setup/dispatch and learning oracle."""
import argparse,ctypes,json,struct
from pathlib import Path
from inspect_ff7_party import Disc,ROOT,image_data,kernel_sections
from inspect_ff7_limits import inspect
from inspect_ff7_battle import inspect as battle_report
from inspect_ff7_animations import decompress_lzs,model_inventory
from test_party_battle_against_retail import VM
from test_party_motions_against_retail import Pose
from unicorn.mips_const import UC_MIPS_REG_PC
class LimitVM(VM):
 def __init__(self,lib,ev,report,images,exe,kernel,menu,batres=False):
  lib.ff7_test_limit_reset(16);super().__init__(lib,report,images,exe,kernel)
  assert lib.ff7_party_limit_init();self.limits={s['address']:s for s in ev['sites'] if s['image']!='BATRES' or batres}
  self.write(0x801d0000,menu);self.reg(28,0x80062d44)
  if batres:self.write(0x801b0000,images['BATRES'][0])
 def hook(self,uc,pc,size,data):
  super().hook(uc,pc,size,data)
  if not hasattr(self,'limits'):return
  if pc in self.limits:
   regs=(ctypes.c_uint32*32)(*(self.reg(i)for i in range(32)));self.lib.ff7_test_limit_hook(pc,regs)
   for i in range(1,32):
    if regs[i]!=self.reg(i):self.reg(i,regs[i])
  if pc==0x80015248:
   regs=(ctypes.c_uint32*32)(*(self.reg(i)for i in range(32)))
   if self.lib.ff7_test_limit_filter(regs):self.reg(2,regs[2]);uc.reg_write(UC_MIPS_REG_PC,self.reg(31))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
 lib=ctypes.CDLL(str(a.library.resolve()))
 for n in('ram','expansion'):getattr(lib,'ff7_test_battle_'+n).restype=ctypes.c_void_p
 for n in('ff7_test_battle_hook','ff7_test_limit_hook'):getattr(lib,n).argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
 lib.ff7_test_limit_filter.argtypes=[ctypes.POINTER(ctypes.c_uint32)]
 lib.ff7_test_limit_data.restype=ctypes.c_uint32
 lib.ff7_motion_decode_frame.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint,ctypes.c_uint,ctypes.POINTER(Pose)]
 ev=inspect(a.disc);assert ev==json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/limit.evidence.json').read_text());report=battle_report(a.disc)
 d=Disc(a.disc)
 try:
  exe=d.read(next(n for n in d.files if n.startswith('SCUS_')and '/'not in n));kernel=kernel_sections(d.read('INIT/KERNEL.BIN'));menu=d.read('MENU/LIMTMENU.MNU')
  images={n:(image_data('BATTLE/'+n+'.X',d.read('BATTLE/'+n+'.X'))[0],0x800a0000 if n=='BATTLE'else 0x801b0000)for n in('BATRES','BATINI','BATTLE')}
  model_raw=d.read('ENEMY6/SEFIROS.LZS');model_data=decompress_lzs(model_raw);inventory=model_inventory(model_raw)
 finally:d.reader.close()
 def vm(batres=False):
  ordered={n:images[n]for n in('BATTLE','BATRES','BATINI')};return LimitVM(lib,ev,report,ordered,exe,kernel,menu,batres)
 def half(v,p):return struct.unpack('<H',v.read(p,2))[0]
 def word(v,p):return struct.unpack('<I',v.read(p,4))[0]
 # First-release preset: Masamune/Crescent Arc only; no level2-4 or mastery slot.
 bits=[0,1];ids=[96,97]+[127]*10
 cases=[];v=vm();original=v.read(0x8009c738,9*132);kg=v.read(0x80082268,len(kernel[2]))
 for guest in list(range(11))+[11,12,26]:
  for bit in range(12):
   v.reg(4,guest);v.reg(5,bit);v.run(0x80015afc)
   expected=kernel[2][guest*56+12+bit]-128 if guest<9 else (127 if guest<11 else ids[bit])
   assert v.reg(2)==expected,(guest,bit,v.reg(2),expected)
 assert v.read(0x80082268,len(kg))==kg and v.read(0x8009c738,len(original))==original
 cases.append('Original GetLimit returns twelve policy slots for extras11/12/26; all native0..10 outputs and kernel/records unchanged')
 # Native learning executes with policy threshold tables and independent records.
 for guest in(11,26):
  v=vm(True);rec=0x9f010000+132*(guest-11);v.write(rec,bytes([guest]));v.write(rec+14,b'\1');v.write(rec+0x22,b'\1\0')
  def learn(kills,uses):v.reg(4,rec);v.reg(5,kills);v.reg(6,uses);v.run(0x801b17cc);return v.reg(2)
  assert learn(79,7)==0;assert half(v,rec+0x24)==79 and half(v,rec+0x26)==7
  assert learn(1,1)==0x02;assert half(v,rec+0x22)==0x03
  assert learn(1000,1000)==0;assert half(v,rec+0x22)==0x03
  # Diagnostic higher levels: unpublished thresholds never learn bits3..9.
  for level,counter in((2,0x28),(3,0x2a),(4,None)):
   v.write(rec+14,bytes([level]));assert learn(20000,20000)==0;assert half(v,rec+0x22)==0x03
   if counter:assert half(v,rec+counter)==20000
  v.write(rec+0x22,b'\xdb\0');assert learn(65535,65535)==0;assert half(v,rec+0x22)==0xdb
  assert half(v,rec+0x24)==65535
 cases.append('Whole original BATRES learning increments and saturates own kills/uses, learns Crescent Arc after eight level1 uses; levels2-4 and final mastery never learn in the release preset')
 for level in range(1,5):
  v=vm();v.write(0x8009cbdc,bytes([0,7,11]));v.write(0x8009c746,b'\1');v.write(0x8009c738+7*132+14,b'\1');rec=0x9f010000;v.write(rec+14,bytes([level]));before=v.read(0x8009c738,9*132)
  v.run(0x801d11a8);cache=0x8009d8f8+2*0x440
  assert v.read(cache,3)==bytes(ids[3*(level-1):3*level]),(level,v.read(cache,3).hex())
  for j,id in enumerate(ids[3*(level-1):3*level]):
   if id!=127:assert v.read(cache+8+j*28,28)==v.read(lib.ff7_test_limit_data()+64+(id-96)*28,28)
  assert v.read(0x8009c738,9*132)==before
 cases.append('Whole original LIMTMENU cache builder preserves native Cloud/Vincent and copies independent custom attack records for allfour selected levels')
 for level in range(1,5):
  v=vm();v.stub(0x801d002c,0x8001f6c0);v.write(0x8009cbdc,bytes([0,7,26]));rec=0x9f010000+15*132
  v.write(rec+14,b'\x01\xff');v.write(rec+0x22,b'\xdb\x02');v.word(0x801d2410,2);v.word(0x801d2320,2)
  v.write(0x801d2366,bytes([(level-1)%2,(level-1)//2]));v.write(0x80062d7c,b'\x20\0');before=v.read(0x8009c738,9*132)
  v.run(0x801d0ed8,0x801d116c)
  assert v.read(rec+14,2)==bytes([level,0])
  assert v.read(0x8009d8f8+2*0x440,3)==bytes(ids[3*(level-1):3*level])
  assert v.read(0x8009c738,9*132)==before
 cases.append('Original menu confirmation block sets allfour levels and clears only extra26 gauge; own attack cache and native Cloud/Vincent records remain independent')
 v=vm()
 for ordinal in range(7):
  for kind,stride,base in((8,32,288),(0,64,512)):
   if ordinal>=len(bits):
    regs=(ctypes.c_uint32*32)();regs[4]=3;regs[5]=96+ordinal;regs[6]=kind
    assert not lib.ff7_test_limit_filter(regs);continue
   v.reg(4,3);v.reg(5,96+ordinal);v.reg(6,kind);v.run(0x80015248)
   assert v.reg(2)==lib.ff7_test_limit_data()+base+stride*ordinal
   assert 255 in v.read(v.reg(2),stride)
 cases.append('Guarded native string function returns generated encoded names and descriptions for Masamune/Crescent Arc and declines the five unreleased reserved IDs')
 # The native command preparer rejects raw IDs >=96 without our exact adapter.
 # Keep the actual gauge consumption/use count/event path, including native IDs.
 for guest,raw,enabled in((0,0,True),(7,52,True),(10,96,False),(11,96,True),(26,97,True),(11,98,False),(26,102,False),(11,103,False)):
  v=vm();v.write(0x801636d8,bytes([guest]));context=0x801e0000;v.word(0x80063014,context)
  v.word(context,2);v.word(context+0x10,raw);v.write(0x800f5ed0,b'\xff\0');v.write(0x800f5ecc,b'\x05')
  v.write(0x800f83d0,b'\x08\0') # Original battle flag suppresses only visual event enqueue.
  before=v.read(0x800f5e60,2*0x34);v.run(0x800a778c)
  assert word(v,context+0x2c)==raw+(128 if enabled else 0)
  assert half(v,0x800f5ed0)==(0 if enabled else 255)
  assert v.read(0x800f5ecc,1)==bytes([6 if enabled else 5])
  assert v.read(0x800f5e60,2*0x34)==before
 cases.append('Whole native Limit command preparer converts own IDs96/97, consumes only actor gauge and increments own use counter; Cloud/Vincent/flashback, unreleased98..102 and unknown IDs preserve stock behavior')
 # Original attack-data resolver finds selected limit and routes own valid script.
 for ordinal,bit in enumerate(bits):
  v=vm();v.write(0x801636b8,b'\x0b');v.write(0x8009cbdc,bytes([11,0,7]));rec=0x9f010000;v.write(rec+14,bytes([bit//3+1]));v.run(0x801d11a8)
  context=0x801e0000;v.word(0x80063014,context);v.word(context,0);v.word(context+0x28,20);v.word(context+0x2c,128+96+ordinal);v.word(context+0x14,0xffffffff)
  v.run(0x800a79cc)
  assert word(v,context+0x20)==(20 if ordinal==0 else 21),(ordinal,word(v,context+0x20))
  assert word(v,context+0x40)==0x11 and word(v,context+0x48)==[48,32][ordinal]
  assert word(v,context+0x24)==255
 cases.append('Whole original battle attack-data resolver executes Masamune and Crescent Arc, retains actual Limit command20 and maps valid own-rig action20/21; no external limit effect index requested')
 # Original physical formula: native target/defend modifiers remain operational.
 v=vm();context=0x801e0000;v.word(0x80063014,context)
 damages=[]
 for power in(16,32,48,64,96,128):
  v.write(context,b'\0'*0x250)
  for off,value in((4,50),(0x4c,100),(0x48,power),(0x6c,65535),(0x208,3),(0x28,20),(0xb8,1)):v.word(context+off,value)
  v.run(0x800ad944);damages.append(word(v,context+0x214))
 assert all(a<b for a,b in zip(damages,damages[1:])),damages
 cases.append('Whole original physical damage formula accepts powers16..128 and preserves normal physical modifiers: '+str(damages))
 # Full original BATINI initializes policy divisor,gauge and learned menu counts.
 for guest in(11,26):
  v=vm();v.stub(0x800a4ba4,0x800a4e80,0x800b108c,0x800155a4)
  v.write(0x8009cbdc,bytes([0,7,guest]))
  for g in range(9):v.write(0x8009c738+132*g,bytes([g]))
  for slot,g in enumerate((0,7,guest)):
   rec=0x8009c738+132*g if g<9 else 0x9f010000+132*(g-11)
   v.write(rec+1,b'\x32');v.write(rec+6,b'\x21');v.write(rec+14,b'\x01\xff');v.write(rec+0x1c,bytes([0,0,255]));v.write(rec+0x22,b'\x03\0');v.write(rec+0x40,b'\xff'*64)
   derived=0x8009d84c+slot*0x440;v.write(derived+0x10,struct.pack('<HHHH',1000,1200,200,300));v.write(derived+0x4c,b'\xff'*96);v.write(derived+0x108,b'\xff'*768)
   for i,cmd in enumerate((1,2,3,4)):v.write(derived+0x4c+i*6,bytes([cmd,7,0,0,0,0]))
  before=v.read(0x8009c738,9*132);v.run(0x801b08c0)
  assert v.read(0x8009c738,9*132)==before
  assert word(v,0x800f5e60+2*0x34+0x1c)==140
  assert half(v,0x800f5e60+2*0x34+8)==255
  assert v.read(0x8009d8f8+2*0x440+6,1)==b'\2'
 cases.append('Whole original BATINI enables independent full gauge,policy divisor and two learned level1 techniques alongside Cloud/Vincent')
 v=vm();v.uc.mem_map(0x1f800000,4096);v.write(0x801b0000,model_data);v.write(0x801636b8,b'\x0b');v.reg(4,0);v.run(0x800b5c1c)
 model=0x80103200;actor=0x801518e4;settings=model+struct.unpack_from('<I',model_data,8)[0]
 def state(motion,action):
  v.write(actor,b'\0'*0x174);v.write(actor+2,struct.pack('<H',action));v.write(actor+14,struct.pack('<HH',motion,48));v.write(actor+0x27,b'\x80')
  v.write(0x800fa714,b'\1\0');v.word(0x800fa6d8,0)
 def pose(p,rot):return (struct.unpack('<hhh',v.read(p+40,6)),[[x&4095 for x in struct.unpack('<3H',v.read(p+52*j+32,6))]for j in range(rot)])
 def expected(motion,frame,bank):
  where=(model+word(v,model+12+4*(motion+52*bank)))&0xffffffff;data=v.read(where,half(v,where+2)+5);out=Pose()
  assert lib.ff7_motion_decode_frame(data,len(data),1 if bank else 48,frame,ctypes.byref(out))
  return tuple(out.position),[list(out.angle[j])for j in range(1 if bank else 48)]
 frames=0
 for motion in sorted(set(inventory['actions'][20]['motion_ids']+inventory['actions'][21]['motion_ids'])):
  state(motion,20)
  for frame in range(inventory['motions'][motion]['frames']):
   v.reg(4,0);v.reg(5,model+12);v.reg(6,model);v.run(0x800cd400)
   assert pose(actor+0x174,48)==expected(motion,frame,0),(motion,frame,'body')
   assert pose(0x800fa6e0,1)==expected(motion,frame,1),(motion,frame,'weapon')
   frames+=1
 for i in range(74):v.word(settings+0x68+4*i,settings+word(v,settings+0x68+4*i))
 dispatched=[]
 for action in(20,21):
  state(0,action);v.write(actor+0x3b,b'\1');v.reg(4,0);v.reg(5,settings+0x68);v.reg(6,model+12);v.reg(7,model)
  v.run(0x800c7c4c);dispatched.append(half(v,actor+14))
 assert dispatched==[26,3],dispatched
 cases.append(f'Original C7C4C dispatches own strike/sweep actions20/21 to motions26/3; original CD400 decodes every frame of all8 referenced motions ({frames} body+weapon pairs) identically to independent bitstream decoder')
 result={'status':'passed','disc':a.disc.name,'cases':cases,'limits':'Original code oracle; live visual acceptance and additional authored choreography remain separate'}
 if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n',newline='\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
