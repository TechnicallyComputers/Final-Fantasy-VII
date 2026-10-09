"""Generate independently reviewed original field record/entity mapping guards."""
import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc,ROOT

READS=[0x800bb1f0,0x800c318c,0x800c3274,0x800c335c,0x800c7ccc,
       0x800c8250,0x800c8618,0x800ca2c8,0x800ca814,0x800cd478,
       0x800ceb40,0x800cefd0,0x800cfefc,0x800cff5c,0x800cffc4,
       0x800cfff0,0x800d00c8,0x800d0250,0x800d02f0,0x800d0350,
       0x800d037c,0x800d0454,0x800d0560,0x800d0ba8]
SITES=[(p,'ENTITY_READ')for p in READS]+[(0x800cec0c,'ENTITY_WRITE'),
       (0x800ced54,'ENTITY_WRITE'),(0x800baf00,'ENTITY_RESET'),
       (0x800d34f0,'HEAL_ALIAS'),(0x800d34fc,'HEAL_RANGE'),(0x800d350c,'HEAL_OFFSET')]

def inspect(cue):
    d=Disc(cue)
    try:data=gzip.decompress(d.read('FIELD/FIELD.BIN')[8:])
    finally:d.reader.close()
    digest=hashlib.sha256(data).hexdigest()
    if digest!='2962d813743a1904faf0843f4a32d1cfece8de12233f9afb8b552556c56000dd':raise ValueError('Unsupported FIELD revision')
    r={'schema':1,'basis':'Original owner-disc MIPS operands, no decompiled source',
       'image':{'base':0x800a0000,'bytes':len(data),'sha256':digest},'sites':[]}
    for pc,action in sorted(SITES):
        words=list(struct.unpack_from('<13I',data,pc-0x800a0000-24))
        if action.startswith('ENTITY_')and action!='ENTITY_RESET':
            assert words[4]==0x2421ad30 and words[5]>>26==0
            assert words[6]>>26==(40 if action=='ENTITY_WRITE' else 36)
        r['sites'].append(dict(address=pc,action=action,expected=words[6],guard=words))
    r['contract']={'plugin':'ff7.party-gameplay, developer default-off',
      'lifecycle':['ff7_party_field_init allocates32 guest bytes; shared gameplay activation must call it',
                   'Original BAF00 per-field reset clears extra bindings; restore preserves guest-backed rewind state'],
      'clobbers':{'HEAL_ALIAS':'v0 points to independent proxy alias scratch',
        'HEAL_RANGE':'v0=1 before original BEQZ for extra, keeping v1 logical proxy intact',
        'HEAL_OFFSET':'v0=(record-8009C738)>>2 before original SLL',
        'ENTITY_READ/WRITE':'at redirected to extra-owned map cell; logical ID register untouched unless native instruction itself overwrites it',
        'ENTITY_RESET':'No GPR changes; clears extra entity map'},
      'binding':'Canonical-ID API accepts already-created mod-owned entity/model only; validates counts, native and extra collisions. Original A0 PC stores for extra IDs share validation.',
      'pending':['No automatic Sephiroth BSX extraction/model/entity injection yet',
                 'Unbound extras read255; some native script paths assume a model exists, so broad story-script safety is not claimed',
                 'Binding API caller owns entity creation/profile matching; no existing NPC is selected or commandeered',
                 'Live field controls, followers, map transitions and story events require acceptance testing'],
      'native_map':'AD30..AD38 only9bytes, initialized by BAF00..BAF1C; battle model presentation is deliberately unused'}
    return r

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--write',action='store_true');a=p.parse_args();r=inspect(a.disc)
    if a.write:
        (ROOT/'mods/preloaded/packages/ff7.expanded-party/field-hooks.evidence.json').write_text(json.dumps(r,indent=2)+'\n')
        (ROOT/'src/ff7_party_field_sites.inc').write_text('/* Generated from original owner-disc FIELD words. */\n'+'\n'.join(
          ' {0x%08xu,%s,{%s}},'%(s['address'],s['action'],','.join('0x%08xu'%w for w in s['guard']))for s in r['sites'])+'\n')
    print(json.dumps({'image':r['image'],'sites':len(r['sites'])}))
if __name__=='__main__':main()
