"""Inventory record-address seams from the owner's original NTSC-U executable.

Emit small instruction guards only; no third-party disassembly or source and
no game assets. The matched multiply is the verified 132-byte character stride.
Each emitted seam includes context for review and an independent MIPS oracle.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, image_data


def inspect(cue, boot):
    disc = Disc(Path(cue))
    try:
        raw = disc.read(boot)
        data, base = image_data(boot, raw)
    finally:
        disc.reader.close()
    words = struct.unpack('<'+'I'*(len(data)//4), data)
    found = {}
    # Verified native code, excluding adjacent constants and data. Every
    # candidate must consume the stride as a native-record-relative address.
    for i in range((0x800110c0-base)//4, (0x8002ee00-base)//4):
        word = words[i]
        if word & 0xffe007ff != 0x140:
            continue
        dst, identity = word >> 11 & 31, word >> 16 & 31
        for j in range(i+1, i+7):
            if words[j] not in ((dst<<21)|(identity<<16)|(dst<<11)|0x21,
                                (identity<<21)|(dst<<16)|(dst<<11)|0x21):
                continue
            for k in range(j+1, j+5):
                final = words[k]
                if final & 0xffe007ff == 0x80 and final >> 16 & 31 == dst:
                    # Stock-record base constants in nearby addressing code.
                    context = words[max(i-24,0):k+17]
                    uses_records = any(w >> 26 == 9 and w & 0xffff in
                        range(0xc738,0xc7bc) for w in context)
                    if uses_records:
                        found[k] = ('OFFSET',dst)
                    break
            break
    # Alias-table loads may keep a permanent table base across a loop. Detect
    # only LW zero-offset paths with the original alias base in nearby code;
    # runtime additionally checks the exact effective alias-table address.
    for i in range((0x800110c0-base)//4, (0x8002ee00-base)//4):
        w = words[i]
        if w >> 26 != 35 or w & 0xffff:
            continue
        nearby = words[max(0,i-18):i]
        if any(v & 0xfc00ffff == 0x240091d0 for v in nearby):
            found[i] = ('ALIAS',w >> 21 & 31)
    # Equipment-attack contribution uses two alias indirections. Its a0 table
    # base survives a branch beyond the local scan window; both second loads
    # must resolve a proxy rather than read the word after the native table.
    for pc in (0x8001fc20,0x8001fc7c):
        i=(pc-base)//4
        if words[i]!=0x8c430000: raise ValueError('equipment contribution seam changed')
        found[i]=('ALIAS',2)
    # Full heal recalculates correctly before these separate final record stores.
    # Original whole-function FIELD oracle proved both writeback paths.
    for pc in (0x80025968,0x80025af0):
        i=(pc-base)//4
        if words[i]!=0x00021080:raise ValueError('full-heal writeback seam changed')
        found[i]=('OFFSET',2)
    sites = []
    for i,(action,reg) in sorted(found.items()):
        sites.append(dict(address=base+i*4,expected=words[i],action=action,
                          reg=reg,guard=list(words[i-6:i+7])))
    return dict(schema=1,basis='owner NTSC-U original resident executable bytes',
                boot_sha256=hashlib.sha256(raw).hexdigest(),sites=sites)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('cue',type=Path)
    p.add_argument('--boot',default='SCUS_941.63')
    p.add_argument('--write',action='store_true')
    args=p.parse_args()
    report=inspect(args.cue,args.boot)
    if args.write:
        out=['/* Owner-binary guards: tools/inspect_ff7_resident_party.py CUE --write */']
        for s in report['sites']:
            out.append('{0x%08xu, %s, %d, {%s}},' % (s['address'],s['action'],s['reg'],
                ','.join('0x%08xu'%w for w in s['guard'])))
        (ROOT/'src/ff7_party_resident_sites.inc').write_text('\n'.join(out)+'\n')
        (ROOT/'mods/preloaded/packages/ff7.expanded-party/resident.evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'sites':len(report['sites']),
                      'aliases':sum(s['action']=='ALIAS' for s in report['sites']),
                      'boot_sha256':report['boot_sha256']},indent=2))


if __name__=='__main__': main()
