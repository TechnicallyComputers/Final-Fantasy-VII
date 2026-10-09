"""Evidence for original defend flag and paired battle-motion decoder seams."""
import argparse,hashlib,json,struct
from pathlib import Path
from inspect_ff7_party import Disc,ROOT,image_data

def inspect(cue):
    d=Disc(cue)
    try:
        raw,base=image_data('BATTLE/BATTLE.X',d.read('BATTLE/BATTLE.X'))
        exe=d.read(next(n for n in d.files if n.startswith('SCUS_')and '/'not in n))[0x800:]
    finally:d.reader.close()
    rows=[]
    for pc in(0x800cd458,0x800cd4cc):
        words=struct.unpack_from('<13I',raw,pc-base-24)
        rows.append({'address':pc,'expected':words[6],'context_start':pc-24,'context_words':list(words),'register':2})
    assert raw[0x4c:0x50]==b'\0'*4
    assert struct.unpack_from('<I',raw,0x3e30)[0]==0x34030013
    assert struct.unpack_from('<I',raw,0x3e6c)[0]==0x34420020
    return {'schema':1,'image':'BATTLE/BATTLE.X','sha256':hashlib.sha256(raw).hexdigest(),'sites':rows,
      'functions':[{'start':a,'end_exclusive':b,'sha256':hashlib.sha256(raw[a-base:b-base]).hexdigest()}for a,b in((0x800a3d4c,0x800a3e98),(0x800cd400,0x800cd558),(0x800d376c,0x800d3994))],
      'resident_rotation':{'start':0x8003bf8c,'end_exclusive':0x8003c218,'sha256':hashlib.sha256(exe[0x2bf8c:0x2c218]).hexdigest(),'convention':'Rx*Ry*Rz; root transform pre-multiplies a world Z roll and extracts this order for both independent body and weapon roots'},
      'defend':{'command':19,'flags_base':0x800f83e4,'actor_stride':104,'mask':32,'proof':'Original queue insertion clears bit0x20 for ordinary commands and sets it for command0x13; original physical-damage path800ADB00 tests same flag and halves damage. Command default800A004C selects idle action0, not a distinct defend script.'},
      'contract':['Two seams are two instructions after LH v0, so native load delay has completed','Require independently prepared extra slot,matching body/table pointers, motion0 and idle action0; use actual original defend flag','Select generated motion11 in v0 at body and weapon pointer lookups; do not change logical action or original flashback','Reset both guest bitstream cursors together when selecting or leaving guard stance; all generated motion storage and role control rewind in guest RAM'],
      'visual_limits':['Procedural root roll and paired own-pose synthesis require live visual review for floor contact,weapon grip and cloth','No authored kneeling,ragdoll,cloth simulation or custom limit effects claimed']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',type=Path,required=True);p.add_argument('--write',action='store_true');a=p.parse_args();r=inspect(a.disc)
    path=ROOT/'mods/preloaded/packages/ff7.expanded-party/motion.evidence.json'
    if a.write:
        path.write_text(json.dumps(r,indent=2)+'\n',newline='\n')
        (ROOT/'src/ff7_party_motion_sites.inc').write_text('/* Original owned-disc decoder guards; inspect_ff7_motions.py. */\n'+''.join('{0x%08xu,{%s}},\n'%(s['address'],','.join('0x%08xu'%w for w in s['context_words']))for s in r['sites']),newline='\n')
    else:assert r==json.loads(path.read_text())
    print(json.dumps({'status':'verified','sites':len(r['sites'])}))
if __name__=='__main__':main()
