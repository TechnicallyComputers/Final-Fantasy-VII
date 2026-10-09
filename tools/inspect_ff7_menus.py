"""Independently inventory NTSC-U menu instruction seams from owner discs.

No disassembly project/source is consumed. --write emits only small instruction
guards and structural evidence; original menu/TIM assets are never emitted.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
from inspect_ff7_party import Disc, ROOT, image_data

BASE = 0x801D0000
EXPECTED = {
    'FORMMENU':'6412f26cbb4ad5df677caf7d29716d62b2b184fcb266bdb2cf05ad73c555a074',
    'EQIPMENU':'433e448de0a5908239df6e50e741fc96e2381a42a0112ce781de9ecf318f8759',
    'STATMENU':'02cf64051b7f6b56b639dabbfcd87c5faaa5848000303dbef9f0849ebebd3c66',
    'ITEMMENU':'0a3635b5c15bb91c23af3c035ecb2e77c8667fcc0ce6c3fd5a713a83adcc0361',
    'MGICMENU':'d29856358872b51e2e2256e403d2cba4628523c02e1846e17e3352b10011636d',
}

def sites(name, data):
    words = struct.unpack('<'+'I'*(len(data)//4), data[:len(data)//4*4])
    found = {}
    def add(offset, action, reg=0):
        found[offset] = (action, reg)
    end = {'FORMMENU':0x1B00,'EQIPMENU':0x8000,'STATMENU':0,'ITEMMENU':0x3260,'MGICMENU':0x2928}[name]
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
                if words[k] == (dst<<16)|(dst<<11)|0x80 or (name in ('ITEMMENU','MGICMENU') and words[k]&0xffe007ff==0x80 and words[k]>>16&31==dst):
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
    elif name == 'STATMENU':
        add(0x0BC0,'ALIAS',1)
        add(0x0BD4,'OFFSET',2)
        add(0x0FA0,'ALIAS',1)
        add(0x0FFC,'OFFSET',8)
        add(0x11B0,'ALIAS',1)
        # SLL a1,v0,2 needs the SOURCE v0 redirected; destination differs.
        add(0x11C0,'OFFSET',2)
        add(0x12A0,'OFFSET',2) # common gauge read after all color branches
        add(0x1364,'OFFSET',17)
    elif name == 'MGICMENU':
        for off in (0x1ba4,0x1cb8,0x1dcc,0x2104,0x228c,0x2414):add(off,'ALIAS',1)
    elif name == 'ITEMMENU':
        add(0x1f2c,'ITEM_LIMIT_MESSAGE')
        add(0x2ae0,'STORY_RETURN_RECORD')
        add(0x2af0,'STORY_RETURN_MASK')
        add(0x2be8,'STORY_RETURN_NEXT')
        add(0x2c18,'STORY_REMOVE_RECORD',6)
        add(0x2c24,'STORY_MASK',6)
        add(0x2c94,'STORY_MORE',6)
        add(0x2dc4,'STORY_SCAN_RECORD',18)
        add(0x2dd4,'STORY_MASK',18)
        add(0x2e2c,'STORY_MORE',18)
    elif name == 'EQIPMENU':
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
        for name in EXPECTED:
            data=disc.read('MENU/'+name+'.MNU')
            if hashlib.sha256(data).hexdigest()!=EXPECTED[name]:
                raise ValueError('Unsupported original menu image: '+name)
            result['menus'][name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
            if name=='STATMENU':
                result['menus'][name]['functions']=[{'address':BASE+start,'end':BASE+end,'sha256':hashlib.sha256(data[start:end]).hexdigest()}for start,end in ((0x0b74,0x0d28),(0x0d28,0x116c),(0x116c,0x14e0))]
                result['menus'][name]['contract']='Eight pre-load/pre-stride adapters route gear,materia,EXP,next-level EXP,limit level/gauge/status and equipment-derived hit/defense/evasion to independent records; party slot801D1E1C and derived1088-byte-per-slot caches remain native. Callback PC and all GPRs except named source operand preserved.'
            elif name in ('ITEMMENU','MGICMENU'):
                ranges=((0x0d24,0x0dcc),(0x0e80,0x296c),(0x2974,0x2f00),(0x2f00,0x3018),(0x3018,0x3138),(0x3138,0x3228))if name=='ITEMMENU'else((0x498,0x2928),)
                result['menus'][name]['functions']=[{'address':BASE+start,'end':BASE+end,'sha256':hashlib.sha256(data[start:end]).hexdigest()}for start,end in ranges]
                result['menus'][name]['contract']=('Direct target132-byte source strides for status/Source items and single-record gear/materia helpers. Original inventory transactions retained. Stock final-limit manuals retain rejection for extras; message-address operand alone changes to bounded authored text at menu allocation+200. Wutai story modes15/16: nine guarded loop-head/mask/boundary adapters append registered independent records after native0..8 selection/removal and after native8..0 return. Native availability bits,48-ranked selection,exact packed AP-word removal,native inventory fallback and192-byte D180 bank remain original. Extras participate even when reserved; no native slot/availability bit is borrowed. Temporary party/gear/materia helper3018 uses native8009D180 scratch and3138 restores it; mid-transaction save policy belongs to lifecycle owner.'if name=='ITEMMENU'else'Six caster alias loads and six132-byte level strides; Cure1/2/3 single/all retain native slot-derived magic attack,target iteration and resident MP/HP routines. Extra guests do not inherit stockID10 free-MP exception. Resident subtraction final offsets258A0/25A28 and addition25968/25AF0 required.')
            result['sites']+=sites(name,data)
        tim=disc.read('MENU/PCEFI.TIM')
        boot=next(n for n in disc.files if n.startswith('SCUS_')and '/'not in n)
        resident,resident_base=image_data(boot,disc.read(boot))
        # Owner-binary dispatch chain identifies this as story menu modes15/16,
        # not an ordinary user-selected Item/Materia menu operation.
        assert struct.unpack_from('<2I',resident,0x800100a0-resident_base)==(0x800123e0,0x800123f0)
        calls=((0x800123e0,0x80024ecc),(0x800123f0,0x80024f04),
               (0x80024eec,0x801d2d74),(0x80024f24,0x801d2e84))
        for pc,target in calls:
            assert struct.unpack_from('<I',resident,pc-resident_base)[0]==0x0c000000|((target&0x0fffffff)>>2)
        item=disc.read('MENU/ITEMMENU.MNU')
        item_calls=((0x801d2d10,0x801d2c00),(0x801d2e58,0x801d2cdc),(0x801d2eb8,0x801d2abc))
        for pc,target in item_calls:
            assert struct.unpack_from('<I',item,pc-BASE)[0]==0x0c000000|((target&0x0fffffff)>>2)
        result['story_materia']={
            'modes':{'15':'rank and confiscate at most48 materia','16':'return to free equipment slots, then inventory'},
            'resident_calls':[{'address':pc,'target':target}for pc,target in calls],
            'item_calls':[{'address':pc,'target':target}for pc,target in item_calls],
            'storage':{'candidate_buffer':0x801d3f60,'native_saved_bank':0x8009d180,'entries':48,'entry_bytes':4,'inventory':0x8009ce60,'inventory_entries':200},
            'ordering':'Select/remove native0..8 subject to originalD78A availability, then registered extras, then inventory; return native8..0 first, then registered extras, then original inventory insertion',
            'guards':'All9 story contexts must match before any story adapter changes a register; loop progress lives only in guest GPRs, no host iterator or allocation',
            'clobbers':{'STORY_SCAN_RECORD':['s3','s4'],'STORY_REMOVE_RECORD':['a3','t0'],'STORY_MASK':['v0'],'STORY_MORE':['v0'],'STORY_RETURN_RECORD':['t0','t3','t4'],'STORY_RETURN_MASK':['v0'],'STORY_RETURN_NEXT':['t1']},
            'policy':'All registered extras participate, including reserve members; no native availability or alias-table slot is reused; packed materia/AP and native bank format unchanged',
            'label_reference':'https://wiki.ffrtt.ru/index.php/FF7/Field/Script/Opcodes/49_MENU',
            'basis':'Implementation and addresses independently derived from owner binaries; external opcode label identifies the Wutai story event only'}
        result['portrait']={'path':'MENU/PCEFI.TIM','bytes':len(tim),
                            'sha256':hashlib.sha256(tim).hexdigest(),
                            'image_vram':[856,448,24,48],'clut_vram':[384,9,256,1]}
        result['integration']={
            'plugin':'ff7.party-gameplay; default-off, root owns activation',
            'lifecycle':['ff7_party_menu_init returns allocation success before proxy publication',
                         'ff7_party_menu_restore preserves rewound guest-backed backups/list'],
            'record_abi':'Before verified SLL destination,source,2, substitute (independent_record-0x8009C738)>>2 for33*extra_guest in the SOURCE register. Only specified GPR changes; original instruction/delay semantics continue. Alias load base operand redirects to allocated scratch word containing the extra guest; native alias table remains unchanged.',
            'persistence':'Menu allocation includes VRAM backup marker/data; full game/card/save ownership belongs to shared bridge.',
            'native_caches':{'record_base':'0x801DF6C0','alias_index':'0x801D8B0C',
                             'party_slot':'0x801DF6B0','exchange_list':'0x801DF6EC'},
            'required_resident_adapters':['0x80020058','0x8001786C','0x800206E4','0x80020B68',
                                          '0x80025668','0x800256DC','0x800257CC','0x80025800','0x800258BC','0x80025988','0x80025A44'],
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
        (ROOT/'src/ff7_party_menu_sites.inc').write_text('\n'.join(output)+'\n',newline='\n')
        (ROOT/'mods/preloaded/packages/ff7.expanded-party/menu.evidence.json').write_text(json.dumps(report,indent=2)+'\n',newline='\n')
    print(json.dumps({'menus':report['menus'],'sites':len(report['sites']),'portrait':report['portrait']},indent=2))

if __name__=='__main__': main()
