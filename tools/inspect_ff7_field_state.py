"""Inventory and guard original132-byte field-state base constructions.

This scans original executable/overlay words, not decompiled source. All
selected instructions are ADDIU r,r,first-record-offset after LUI r,8007 with
no intervening write to r. Runtime also requires that exact source value.
"""
import argparse,gzip,hashlib,json,struct
from pathlib import Path
from inspect_ff7_party import Disc,ROOT
EXPECTED={'FIELD/FIELD.BIN':'2962d813743a1904faf0843f4a32d1cfece8de12233f9afb8b552556c56000dd',
          'resident':'7c2e9bacbb914200e7dfaa1972886aebeb258ab8db4c24548d18b319b849d7c8'}
def destination(word):
    op=word>>26
    if op==0:return word>>11&31
    if op in(1,2,3,4,5,6,7,40,41,42,43,46):return -1
    return word>>16&31
def inspect(cue):
    d=Disc(cue)
    try:
        data={'FIELD/FIELD.BIN':(0x800a0000,gzip.decompress(d.read('FIELD/FIELD.BIN')[8:])),
              'resident':(0x80010000,d.read(next(n for n in d.files if n.startswith('SCUS_')and '/'not in n))[0x800:])}
        audited=[]
        for name in d.files:
            if not name.endswith(('.X','.MNU','.BIN')):continue
            raw=d.read(name)
            if raw[8:11]==b'\x1f\x8b\x08':body=gzip.decompress(raw[8:])
            elif name.endswith('.MNU'):body=raw
            else:continue
            words=struct.unpack('<%dI'%(len(body)//4),body[:len(body)//4*4]);hits=[]
            for i,w in enumerate(words):
                rs=w>>21&31
                if w>>26 in(9,13,32,33,35,36,37,40,41,43)and 0x4ea4<=(w&65535)<0x56e4 and any(words[j]==(0x3c008007|rs<<16)for j in range(max(0,i-6),i)):
                    hits.append(i*4)
            assert (name=='FIELD/FIELD.BIN'and len(hits)==395)or not hits,(name,hits)
            audited.append(name)
    finally:d.reader.close()
    sites=[];images=[]
    for name,(base,raw)in data.items():
        digest=hashlib.sha256(raw).hexdigest();assert digest==EXPECTED[name]
        images.append({'name':name,'base':base,'bytes':len(raw),'sha256':digest})
        words=struct.unpack('<%dI'%(len(raw)//4),raw)
        for i,w in enumerate(words):
            rs=w>>21&31;rt=w>>16&31;imm=w&65535
            if w>>26 not in(9,13)or not 0x4ea4<=imm<0x4f28:continue
            lui=[j for j in range(max(0,i-6),i)if words[j]==(0x3c008007|rs<<16)]
            if not lui:continue
            assert w>>26==9 and rs==rt and all(destination(words[j])!=rs for j in range(lui[-1]+1,i))
            pc=base+4*i
            # Entry a1 stays native until loader preparation commits. Otherwise
            # a previous field's active flag could alter a failed next load.
            if pc==0x800a1e3c:continue
            sites.append({'address':pc,'expected':w,'register':rs,'field_offset':imm-0x4ea4,
                          'lui_address':base+4*lui[-1],'guard':list(words[i-6:i+7]),'image':name,'action':'BASE'})
    for pc,action,register in((0x800c576c,'ENTITY_LOAD',3),(0x800c5780,'ENTITY_STORE',1)):
        base,raw=data['FIELD/FIELD.BIN'];words=struct.unpack_from('<13I',raw,pc-base-24)
        sites.append({'address':pc,'expected':words[6],'register':register,'guard':list(words),'image':'FIELD/FIELD.BIN','action':action})
    sites.sort(key=lambda x:x['address']);assert len(sites)==400
    return {'schema':1,'images':images,'audited_overlays':sorted(audited),'native_base':0x80074ea4,'stride':132,'capacity':32,'sites':sites,
      'contract':['Allocator-owned32-record field state array; logical entity/model numbers unchanged','Active guest flag gates all direct references; global8009C544 receives same array through BA534 a1','BASE callbacks only change the ADDIU destination/source register when its incoming value is80070000; PC/return address preserved','Two CHAR counter callbacks address guest scratch for appended entities only; native counter is unchanged, including delayed native CHAR creation','13 original words verified per instruction; all contexts verified before publishing a new field','Four resident return-location snapshot accesses remain routed even while another overlay is loaded','A1E3C excluded; preparation failure must leave entry a1 native']}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',type=Path,required=True);p.add_argument('--write',action='store_true');a=p.parse_args();r=inspect(a.disc)
    path=ROOT/'mods/preloaded/packages/ff7.expanded-party/field-state.evidence.json'
    if a.write:
        path.write_text(json.dumps(r,indent=2)+'\n',newline='\n')
        (ROOT/'src/ff7_party_field_state_sites.inc').write_text('/* Original owner-disc field-state sites; inspect_ff7_field_state.py. */\n'+''.join('{0x%08xu,%du,%s,{%s}},\n'%(s['address'],s['register'],s['action'],','.join('0x%08xu'%w for w in s['guard']))for s in r['sites']),newline='\n')
    else:assert r==json.loads(path.read_text())
    print(json.dumps({'status':'verified','sites':len(r['sites'])}))
if __name__=='__main__':main()
