"""Owner-disc limit lookup/menu/battle/progression instruction evidence."""
import argparse,hashlib,json,struct
from pathlib import Path
from inspect_ff7_party import Disc,ROOT,image_data,kernel_sections
EXPECTED={
 'EXE':'7c2e9bacbb914200e7dfaa1972886aebeb258ab8db4c24548d18b319b849d7c8',
 'BATINI':'0731ada119bf4e505cd0ff3a82ab35b772db6b2d88b8ee1606d16d4843a0d087',
 'BATRES':'138b71b4c6843eb77a7909263f12166aea597ab8a694dc8ef10a39afe58cc35e',
 'BATTLE':'94a0c251c98197a6b902068082180ce244a8b4ecd93792298816a486880a2e7b',
 'LIMTMENU':'31483a299e28c7298a44541e18ac43a6395e4e17786b70a67f78d66f41771138'}
FIXED={
 'EXE':[(0x80015b34,'GET',0)],
 'BATINI':[(0x801b0c98,'INIT_ENABLE',0),(0x801b0ce0,'DIVISOR',0)],
 'BATRES':[(0x801b1804,'LEARN_ENABLE',0),(0x801b1828,'KILLS_TABLE',0),(0x801b1894,'LEARN_ENABLE',0),(0x801b18b4,'USES_TABLE',0),(0x801b1918,'MASTERY',0)],
 'BATTLE':[(0x800a77cc,'COMMAND',0),(0x800a7b60,'ACTION',0)],
 'LIMTMENU':[(0x801d1084,'MENU_ATTACK',0),(0x801d1290,'MENU_ATTACK',0)]}
def inspect(cue):
 d=Disc(Path(cue))
 try:
  exe=d.read(next(n for n in d.files if n.startswith('SCUS_')and '/'not in n))
  images={'EXE':(exe[0x800:],0x80010000)}
  for n in ('BATINI','BATRES','BATTLE'):
   b,_=image_data('BATTLE/'+n+'.X',d.read('BATTLE/'+n+'.X'));images[n]=(b,0x800a0000 if n=='BATTLE'else 0x801b0000)
  images['LIMTMENU']=(d.read('MENU/LIMTMENU.MNU'),0x801d0000)
  growth=kernel_sections(d.read('INIT/KERNEL.BIN'))[2]
  assert all(not 96<=growth[56*identity+12+bit]-128<103 for identity in range(9)for bit in range(12))
 finally:d.reader.close()
 result={'schema':1,'basis':'Original owner-disc bytes; independently analyzed instruction operands','images':{},'sites':[]}
 for n,(data,base)in images.items():
  result['images'][n]={'base':base,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
  if result['images'][n]['sha256']!=EXPECTED[n]:raise ValueError('Unsupported original revision: '+n)
  found={a:(act,r)for a,act,r in FIXED[n]}
  if n=='LIMTMENU':
   words=struct.unpack('<%dI'%(len(data)//4),data[:len(data)//4*4])
   for off in (0x1f4,0x390,0x4ac,0x754,0x97c,0xde4,0xf7c,0xfc8,0x1030,0x1104,0x1214):
    assert words[off//4]>>26 in(35,36),(hex(off),hex(words[off//4]))
    found[base+off]=('ALIAS',words[off//4]>>21&31)
   for i in range(0x1320//4-12):
    a=words[i]
    if a&0xffe007ff!=0x140:continue
    dst,identity=a>>11&31,a>>16&31
    for j in range(i+1,i+7):
     if words[j] not in((dst<<21)|(identity<<16)|(dst<<11)|0x21,(identity<<21)|(dst<<16)|(dst<<11)|0x21):continue
     for k in range(j+1,j+5):
      if words[k]&0xffe007ff==0x80 and words[k]>>16&31==dst:found[base+k*4]=('OFFSET',dst);break
     break
  for pc,(action,reg)in sorted(found.items()):
   guard=list(struct.unpack_from('<13I',data,pc-base-24));result['sites'].append(dict(image=n,address=pc,action=action,reg=reg,expected=guard[6],guard=guard))
 data,base=images['EXE'];result['name_filter']={'address':0x80015248,'words':list(struct.unpack_from('<13I',data,0x5248)),'end':0x800155a4,'sha256':hashlib.sha256(data[0x5248:0x55a4]).hexdigest()}
 table=images['LIMTMENU'][0][0x1324:0x1324+128*28]
 assert table[96*28:103*28]==b'\xff'*(7*28)
 result['reserved_ids']={'first':96,'count':7,'original_28byte_entries':'all FF; native nine-character GetLimit maps never reference these IDs'}
 result['runtime_contract']={
  'plugin':'ff7.party-gameplay; developer default-off; all 32 instruction sites plus function filter80015248 required',
  'allocation':'1024 bytes aligned16 via psx_mod_alloc_guest_memory; guest-owned immutable tables/strings participate in whole RAM snapshots; no host progression state',
  'profile':'Trailing FF7PartyProfile.limit_policy:0 unchanged,1 Sephiroth. Only registered extra identities use custom progression; native0..10 and global alias table unchanged. Current policy registry implements one sword policy; future policy IDs require their own verified attack-ID reservations and table allocation.',
  'registers':{'GET':'a0=guest,a1=learned bit; changes v1 before native move v0,v1',
   'INIT_ENABLE':'fp=guest,s3=record,s0=derived; changes v0 and builds derived limit cache',
   'DIVISOR':'fp=guest,a0=native growth-divisor base; changes v0 so following addition addresses guest table',
   'LEARN_ENABLE':'t1=guest; changes v0 only',
   'KILLS_TABLE/USES_TABLE':'t1=guest,v1=native table base; changes v0 before addition',
   'MASTERY':'a0=record,a3=learned mask,t3=accumulated kills; OR final bit into a3 only after all six prerequisite bits and320 kills',
   'COMMAND':'a1=actor slot,v1=raw limit ID; changes v0 only for matching profile move',
   'ACTION':'s6=guest,s2=limit ID; changes v0 to valid own action20/21',
   'MENU_ATTACK':'v1=embedded attack entry pointer; redirects v1 for own active guest and reserved ID',
   'ALIAS/OFFSET':'changes only the explicitly listed register at the pre-load/pre-final-stride instruction',
   'name_filter':'a0=3,a1=reserved limit ID,a2=0(description) or8(name); handled call changes v0 only, framework returns to existing ra; no stack or native record writes'},
  'pc':'Instruction callbacks preserve incoming CPU.pc; callback address is authoritative. They never synthesize a link return. Name filter uses framework handled-call return.',
  'record_persistence':'Uses existing independent132-byte record: selected level0E,gauge0F,learned mask22,kills24,level1/2/3 use counts26/28/2A. Existing canonical save codec carries all bytes; no new save-format version. New game initializes level1,empty gauge,bit0 and zero counters. Canonical load ORs only bit0 for matching known limit policies to migrate earlier extended saves; preserves selected level,gauge,all counters and other learned bits.',
  'progression':'Second moves require8/7/6 uses at levels1/2/3; first moves at levels2/3 require80/160 cumulative kills; final requires all six earlier bits and320 cumulative kills. Native counter saturation retained. Native menu confirmation changes level and clears gauge.',
  'visual_scope':'Seven mod-authored sword techniques reuse two existing own-rig actions20/21. Every referenced body/weapon motion is present. This is not seven bespoke choreographies, Octaslash, Supernova, or an imported limit effect. Balance and live targeting/camera/visual acceptance remain provisional.',
  'attacks':'IDs96..102; bits0,1,3,4,6,7,9; powers48,32,64,48,96,64,128 in native /16 physical formula; alternating single target0x13 and all targets0x17 (final all). No MP cost, element/status/additional effect. Damage formula0x11, external effectFF, default cameraFFFF. Names/descriptions and attack records authored in code; no owned asset bytes committed.'}
 result['functions']={}
 for n,start,end in [('EXE',0x80015afc,0x80015b44),('BATRES',0x801b17cc,0x801b193c),('LIMTMENU',0x801d11a8,0x801d1320),('BATINI',0x801b08c0,0x801b0f08),('BATTLE',0x800a778c,0x800a784c),('BATTLE',0x800a79cc,0x800a80dc)]:
  b,base=images[n];result['functions'][hex(start)]={'image':n,'end':end,'sha256':hashlib.sha256(b[start-base:end-base]).hexdigest()}
 return result
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',type=Path,required=True);p.add_argument('--write',action='store_true');a=p.parse_args();r=inspect(a.disc)
 if a.write:
  (ROOT/'mods/preloaded/packages/ff7.expanded-party/limit.evidence.json').write_text(json.dumps(r,indent=2)+'\n',newline='\n')
  out=['/* Generated from owner disc by inspect_ff7_limits.py. */']
  for s in r['sites']:out.append('{0x%08xu,L_%s,%d,{%s}},'%(s['address'],s['action'],s['reg'],','.join('0x%08xu'%x for x in s['guard'])))
  (ROOT/'src/ff7_party_limit_sites.inc').write_text('\n'.join(out)+'\n',newline='\n')
 print(json.dumps({'images':r['images'],'sites':len(r['sites'])}))
if __name__=='__main__':main()
