"""Inventory resident EXP-result display seams from original owned NTSC-U discs."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, image_data

SITES=[(0x80015700,'RECORD_SCAN',0),(0x800222d0,'RESULT_ALIAS',1),
       (0x800245e8,'RESULT_ALIAS',2),(0x80025f20,'PORTRAIT_COPY',16)]
FUNCTIONS=[(0x80015668,0x800159b0),(0x80021f58,0x80022b5c),
           (0x80025ed4,0x8002603c)]
def inspect(cue):
    d=Disc(Path(cue))
    try:
        boot=next(n for n in d.files if n.startswith('SCUS_')and '/'not in n)
        raw=d.read(boot);data,base=image_data(boot,raw)
    finally:d.reader.close()
    r={'schema':1,'basis':'Original owner-disc MIPS operands and execution',
       'sites':[],'functions':[]}
    for pc,action,reg in sorted(SITES):
        words=list(struct.unpack_from('<13I',data,pc-base-24))
        r['sites'].append(dict(address=pc,action=action,reg=reg,expected=words[6],guard=words))
    for start,end in FUNCTIONS:
        r['functions'].append(dict(start=start,end_exclusive=end,
            sha256=hashlib.sha256(data[start-base:end-base]).hexdigest()))
    r['contract']={'plugin':'ff7.party-gameplay, default-off',
      'record_search':'Original EXP tween searches one independent record; native nine-record search remains unchanged',
      'aliases':'LW/LBU operands point to proxy scratch, retaining logical identity; final strides select independent records',
      'portraits':'Shared profile atlas preparation; original GPU copy uses atlas index and original party destination; draw retains party-slot CLUT/UVs',
      'state':'Original party-slot EXP buffers and guest-owned registry; no new host gameplay state',
      'dependencies':'Resident alias80021EE0 and record strides800225EC/800227A4; each shared plugin address registered once',
      'limits':'Existing limit announcement is memory-safe; custom learning remains separate'}
    return r
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--write',action='store_true');a=p.parse_args();r=inspect(a.disc)
    if a.write:
        (ROOT/'mods/preloaded/packages/ff7.expanded-party/results.evidence.json').write_text(json.dumps(r,indent=2)+'\n')
        (ROOT/'src/ff7_party_results_sites.inc').write_text('/* Generated from original owner-disc resident words. */\n'+'\n'.join(
            ' {0x%08xu,%s,%d,{%s}},'%(s['address'],s['action'],s['reg'],','.join('0x%08xu'%w for w in s['guard']))for s in r['sites'])+'\n')
    print(json.dumps({'sites':len(r['sites']),'functions':r['functions']}))
if __name__=='__main__':main()
