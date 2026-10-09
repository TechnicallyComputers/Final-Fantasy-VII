"""Synchronize independently inventoried party seams into native generation.

Multiple overlays can share an address. C hooks retain full instruction/context
guards; native generation needs only the sorted unique address union.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'mods/preloaded/packages/ff7.expanded-party'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    paths=[EVIDENCE/'resident.evidence.json',EVIDENCE/'menu.evidence.json']
    if (EVIDENCE/'battle.evidence.json').exists(): paths.append(EVIDENCE/'battle.evidence.json')
    if (EVIDENCE/'game-save.evidence.json').exists(): paths.append(EVIDENCE/'game-save.evidence.json')
    if (EVIDENCE/'rewards.evidence.json').exists(): paths.append(EVIDENCE/'rewards.evidence.json')
    if (EVIDENCE/'field-hooks.evidence.json').exists(): paths.append(EVIDENCE/'field-hooks.evidence.json')
    if (EVIDENCE/'results.evidence.json').exists(): paths.append(EVIDENCE/'results.evidence.json')
    if (EVIDENCE/'field-loader.evidence.json').exists(): paths.append(EVIDENCE/'field-loader.evidence.json')
    if (EVIDENCE/'field-state.evidence.json').exists(): paths.append(EVIDENCE/'field-state.evidence.json')
    if (EVIDENCE/'motion.evidence.json').exists(): paths.append(EVIDENCE/'motion.evidence.json')
    sites=set()
    for path in paths:
        for site in json.loads(path.read_text(encoding='utf-8'))['sites']:
            address=site['address']
            sites.add(int(address,0) if isinstance(address,str) else address)
    for site in sites:
        if site & 3 or not 0x80000000<=site<0x80200000:
            raise ValueError('invalid instruction site: '+hex(site))
    block='mod_instruction_sites = [\n'+''.join('    "0x%08X",\n'%pc for pc in sorted(sites))+']'
    path=ROOT/'game.toml'
    original=path.read_text(encoding='utf-8')
    pattern=r'mod_instruction_sites\s*=\s*\[[\s\S]*?\]'
    if re.search(pattern,original): updated=re.sub(pattern,lambda _:block,original)
    else:
        marker='\n[runtime]'
        comment='\n# Exact instruction seams for expanded-party adapters. Regenerate this list\n# with tools/sync_party_instruction_sites.py after updating owner-binary evidence.\n'
        updated=original.replace(marker,'\n'+comment+block+'\n'+marker,1)
    if args.check and updated!=original:
        print('party instruction sites drifted; run tools/sync_party_instruction_sites.py',file=sys.stderr)
        return 1
    if not args.check: path.write_text(updated,encoding='utf-8',newline='\n')
    print(f'{len(sites)} guarded party instruction sites agree with native config')
    return 0


if __name__=='__main__': raise SystemExit(main())
