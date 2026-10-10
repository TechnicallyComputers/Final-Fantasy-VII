"""Inventory save lifecycle seams from the owner's original SAVEMENU bytes."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, image_data

SITES=((0x801d22cc,'PREVIEW_OFFSET'),(0x801d2900,'PREPARE'),
       (0x801d49b0,'LOADED'),(0x801d2a14,'FINISHED'),(0x801d1f1c,'PREVIEW_READ'))

def inspect(cue):
    disc=Disc(Path(cue))
    try:
        raw=disc.read('MENU/SAVEMENU.MNU')
        boot=next(n for n in disc.files if n.startswith('SCUS_') and '/' not in n)
        executable=disc.read(boot)
    finally:disc.reader.close()
    data,base=image_data('MENU/SAVEMENU.MNU',raw)
    sites=[]
    for pc,action in sorted(SITES):
        guard=list(struct.unpack_from('<13I',data,pc-base-24))
        sites.append(dict(address=pc,action=action,expected=guard[6],guard=guard))
    text,text_base=image_data(boot,executable)
    pc=0x80011dbc;guard=list(struct.unpack_from('<13I',text,pc-text_base-24))
    if guard[6]!=0x0c0046ed:raise ValueError('Unsupported new-game seam')
    sites.append(dict(address=pc,action='NEW_GAME',expected=guard[6],guard=guard))
    return dict(schema=1,basis='owner NTSC-U original SAVEMENU bytes',
                sha256=hashlib.sha256(raw).hexdigest(),base=base,sites=sites,
                load_function_hashes=[dict(start=a,end_exclusive=b,sha256=hashlib.sha256(data[a-base:b-base]).hexdigest())
                    for a,b in ((0x801d1f40,0x801d2150),(0x801d1950,0x801d19c4),(0x801d3ab0,0x801d4c38))],
                new_game=dict(address=pc,boot=boot,sha256=hashlib.sha256(executable).hexdigest(),
                    basis='Title result1 only, after native kernel/settings/party reset; field-party.evidence.json'),
                checksum=dict(start=0x801d1950,end_exclusive=0x801d19c4,
                    bytes=4336,polynomial='0x1021',initial='0xFFFF',complement=True),
                lifecycle=dict(outgoing_file='0x801E6F38',native_map='0x8009C6E4',
                    file_bytes=8192,map_bytes=4340,map_offset=512,
                    identity='exact bu00/bu10 filename and one-block allocated directory',
                    publish='full packet equality; never attach metadata to a partial packet',
                    load_success=dict(address=0x801d49b0,expected=0x0c074ad6,filename='caller SP-0x30',
                        basis='1F40 frame0x68, filename+0x38;1950 checksum is stackless;4988 native CRC equality branches to49B0; error/file failures do not reach this seam; restore before2B58 can overwrite old frame'),
                    rewind='pending packet and payload in snapshot-owned Enhancement1'),
                preview_read=dict(address=0x801d1f1c,function=0x801d1d40,cache='0x801E3864+84*(s2&15)',filename='SP+0x38',
                    basis='1D40 opens bu00/bu10 file s2, copies its 0x54-byte header to the list cache and reaches1F1C only on success; party preview bytes5..7 hold the native fallback for an extended slot'))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cue',type=Path)
    p.add_argument('--write',action='store_true');a=p.parse_args();r=inspect(a.cue)
    if a.write:
        lines=['/* Original owner-disc guards: tools/inspect_ff7_game_save.py CUE --write */']
        for s in r['sites']:
            lines.append('{0x%08xu,%s,{%s}},'%(s['address'],s['action'],
                ','.join('0x%08xu'%w for w in s['guard'])))
        (ROOT/'src/ff7_party_game_save_sites.inc').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
        (ROOT/'mods/preloaded/packages/ff7.expanded-party/game-save.evidence.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(sites=len(r['sites']),sha256=r['sha256']),indent=2))
if __name__=='__main__':main()
