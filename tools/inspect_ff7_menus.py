"""Independently inventory NTSC-U menu instruction seams from owner discs.

No disassembly project/source is consumed. --write emits only small instruction
guards and structural evidence; original menu/TIM assets are never emitted.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
from inspect_ff7_party import Disc, ROOT

BASE = 0x801D0000
EXPECTED = {
    'FORMMENU':'6412f26cbb4ad5df677caf7d29716d62b2b184fcb266bdb2cf05ad73c555a074',
    'EQIPMENU':'433e448de0a5908239df6e50e741fc96e2381a42a0112ce781de9ecf318f8759',
}

def sites(name, data):
    words = struct.unpack('<'+'I'*(len(data)//4), data[:len(data)//4*4])
    found = {}
    def add(offset, action, reg=0):
        found[offset] = (action, reg)
    end = 0x1B00 if name == 'FORMMENU' else 0x8000
    # Verified character stride: (ID * 32 + ID) * 4. The callback substitutes
    # only proxy11's final offset; native IDs and their alias values are intact.
    for i in range(end//4-12):
        a = words[i]
        if a & 0xFFE007FF != 0x140:
            continue
        dst, identity = a >> 11 & 31, a >> 16 & 31
        for j in range(i+1, i+7):
            if words[j] not in ((dst<<21)|(identity<<16)|(dst<<11)|0x21,
                                (identity<<21)|(dst<<16)|(dst<<11)|0x21):
                continue
            for k in range(j+1, j+5):
                if words[k] == (dst<<16)|(dst<<11)|0x80:
                    add(k*4, 'OFFSET', dst)
                    break
            break
    if name == 'FORMMENU':
        for off in (0x1558, 0x1684, 0x17E0):
            add(off, 'PORTRAIT', 16)
        add(0x18E4, 'PORTRAIT_ALIAS', 1)
        add(0x0E08, 'PHS_READY')
        add(0x1A5C, 'PHS_CLOSE')
        add(0x0B78, 'PHS_SWAP')
    else:
        add(0x1AE8, 'OFFSET', 2)  # shared branch tail of accessory swap
        for off in (0x0720, 0x0C48, 0x0F1C, 0x0F7C, 0x1460, 0x14C0,
                    0x1520, 0x6CFC, 0x7C98, 0x7CF4, 0x7D34, 0x7D90):
            add(off, 'ALIAS', (words[off//4]>>21)&31)
        for off, reg in ((0x03C4, 10), (0x046C, 0), (0x0508, 0)):
            add(off, 'ELIGIBILITY', reg)
        # Relocate every use of the exchange roster base. Native list capacity
        # is nine; expansion list has sixteen bytes and count remains <=10.
        for i in range(0x5194//4, 0x6C08//4):
            if words[i] == 0x2421F6EC:
                add(i*4+4, 'LIST_BASE', 1)
        add(0x51A8, 'LIST_CLEAR')
        add(0x51DC, 'LIST_FILL')
        add(0x5210, 'LIST_APPEND')
    result=[]
    for off,(action,reg) in sorted(found.items()):
        guard=words[off//4-6:off//4+7]
        result.append(dict(menu=name,address=BASE+off,expected=words[off//4],
                           action=action,reg=reg,guard=list(guard)))
    return result

def inspect(cue):
    disc=Disc(Path(cue))
    try:
        result={'schema':1,'basis':'owner NTSC-U original MNU bytes, no third-party source',
                'menus':{},'sites':[]}
        for name in ('FORMMENU','EQIPMENU'):
            data=disc.read('MENU/'+name+'.MNU')
            if hashlib.sha256(data).hexdigest()!=EXPECTED[name]:
                raise ValueError('Unsupported original menu image: '+name)
            result['menus'][name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
            result['sites']+=sites(name,data)
        tim=disc.read('MENU/PCEFI.TIM')
        result['portrait']={'path':'MENU/PCEFI.TIM','bytes':len(tim),
                            'sha256':hashlib.sha256(tim).hexdigest(),
                            'image_vram':[856,448,24,48],'clut_vram':[384,9,256,1]}
        result['integration']={
            'plugin':'ff7.party-gameplay; default-off, root owns activation',
            'lifecycle':['ff7_party_menu_init returns allocation success before proxy publication',
                         'ff7_party_menu_restore preserves rewound guest-backed backups/list'],
            'record_abi':'Before verified SLL r,r,2, substitute (independent_record-0x8009C738)>>2 for33*extra_guest. Only specified GPR changes; original instruction/delay semantics continue. Alias load base operand redirects to allocated scratch word containing the extra guest; native alias table remains unchanged.',
            'persistence':'Menu allocation includes VRAM backup marker/data; full game/card/save ownership belongs to shared bridge.',
            'native_caches':{'record_base':'0x801DF6C0','alias_index':'0x801D8B0C',
                             'party_slot':'0x801DF6B0','exchange_list':'0x801DF6EC'},
            'required_resident_adapters':['0x80020058','0x8001786C','0x800206E4','0x80020B68',
                                          '0x80025668','0x800256DC','0x800257CC'],
            'limits':['PHS reserve grid remains nine cells; overflow counted, future paging required beyond capacity.',
                      'Materia exchange uses32 allocated list bytes for9 native+16 added members.',
                      'One additional PHS portrait cell; further distinct nonnative portraits need another bank/paging.',
                      'Battle, field/story, save-slot fallback and full runtime integration are separate acceptance work.'],
        }
        return result
    finally:
        disc.reader.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('cue',type=Path)
    p.add_argument('--write',action='store_true')
    args=p.parse_args(); report=inspect(args.cue)
    if args.write:
        output=['/* Owner-binary guards. Regenerate: tools/inspect_ff7_menus.py CUE --write */']
        for s in report['sites']:
            output.append('{0x%08xu, MENU_%s, %s, %d, {%s}},' %
                          (s['address'],s['menu'],s['action'],s['reg'],
                           ','.join('0x%08xu'%w for w in s['guard'])))
        (ROOT/'src/ff7_party_menu_sites.inc').write_text('\n'.join(output)+'\n')
        (ROOT/'mods/preloaded/packages/ff7.expanded-party/menu.evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'menus':report['menus'],'sites':len(report['sites']),'portrait':report['portrait']},indent=2))

if __name__=='__main__': main()
