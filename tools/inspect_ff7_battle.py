"""Generate guarded battle seams from original owner-disc NTSC-U overlays."""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, image_data

EXPECTED={'BATINI':'0731ada119bf4e505cd0ff3a82ab35b772db6b2d88b8ee1606d16d4843a0d087',
          'BATTLE':'94a0c251c98197a6b902068082180ce244a8b4ecd93792298816a486880a2e7b'}

SITES = {
 'BATINI': [(0x801b09c4,'INITIAL_RECORD',0),(0x801b0fa0,'REFRESH_RECORD',0)],
 'BATTLE': [(0x800a609c,'AI_ALIAS',0),(0x800a60b8,'AI_HEADER',0),
            (0x800c5fdc,'MODEL',0),(0x800b3d08,'EXTENT',0),
            (0x800b3b3c,'EXTENT',1),(0x800b3c08,'EXTENT',2),
            (0x800b5c68,'MOTIONS',0),(0x800a36f8,'ARENA_RECORD',0)]
}
for pc,reg in [(0x800dd638,1),(0x800e242c,2),(0x800e2574,2),
               (0x800e25c0,2),(0x800e34ec,1),(0x800e4424,2)]:
    SITES['BATTLE'].append((pc,'ALIAS',reg))
# Explicit reviewed record strides; no speculative blanket instruction rewrite.
# Includes battle names, post-battle names, and Battle Square record mutations.
for pc,reg in [(0x800dd648,2),(0x800e243c,2),(0x800e2584,6),
 (0x800e25d4,2),(0x800e34fc,2),(0x800e4434,2),(0x800e6034,2),
 (0x800e62cc,2),(0x800e62f4,3),(0x800e6344,4),(0x800e6388,3),
 (0x800e63c4,3),(0x800e6400,3),(0x800e643c,3),(0x800e6478,2),
 (0x800e64d4,2),(0x800e6540,2),(0x800e6588,2)]:
    SITES['BATTLE'].append((pc,'OFFSET',reg))

FUNCTIONS = {'BATINI': [(0x801b08c0,0x801b0f08),(0x801b0f08,0x801b1120),
                          (0x801b11bc,0x801b137c)],
             'BATTLE': [(0x800a5fb0,0x800a6000),(0x800a6000,0x800a61d4),
                        (0x800c5e94,0x800c60f4),(0x800b3ab8,0x800b3b84),
                        (0x800b3b84,0x800b3c50),(0x800b3cd0,0x800b3d38),
                        (0x800b5c1c,0x800b5cd4)]}

def inspect(cue):
    disc=Disc(Path(cue))
    try:
        result={'schema':1,'basis':'Original owner-disc bytes; independent MIPS operand analysis',
                'overlays':{},'sites':[],'functions':[]}
        for name in SITES:
            data,base=image_data('BATTLE/'+name+'.X',disc.read('BATTLE/'+name+'.X'))
            if hashlib.sha256(data).hexdigest()!=EXPECTED[name]:raise ValueError('Unsupported original '+name)
            result['overlays'][name]={'base':base,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            for pc,action,reg in sorted(SITES[name]):
                off=pc-base
                guard=list(struct.unpack_from('<13I',data,off-24))
                result['sites'].append(dict(overlay=name,address=pc,expected=guard[6],
                                          action=action,reg=reg,guard=guard))
            for start,end in FUNCTIONS[name]:
                result['functions'].append(dict(overlay=name,start=start,end_exclusive=end,
                    sha256=hashlib.sha256(data[start-base:end-base]).hexdigest()))
        from inspect_ff7_animations import decompress_lzs,sections,SEPHIROTH_SHA256,actions
        raw=disc.read('ENEMY6/SEFIROS.LZS')
        if hashlib.sha256(raw).hexdigest()!=SEPHIROTH_SHA256:raise ValueError('Unsupported Sephiroth asset')
        unpacked=decompress_lzs(raw);chunks,offsets=sections(unpacked)
        body=struct.unpack_from('<I',unpacked,len(chunks)*4-64)[0]
        result['motion_preparation']={'source_sha256':SEPHIROTH_SHA256,'body_bytes':body,
          'body_crc32':zlib.crc32(unpacked[:body]),'model_slot_capacity':61440,
          'pointer_aliases':[{'offset':4+4*(2+bank+target),'before':offsets[2+bank+target],
                              'after':offsets[2+bank+source]}
                            for bank in(0,52)for target,source in((8,5),(9,12),(10,12))],
          'damage_bytes':[offsets[1]+actions(chunks[1])[action]['settings_offset']+delta
                          for action,delta in((5,0),(6,0),(6,1),(7,0))],
          'policy':'profile.motion_policy==FF7_PARTY_MOTION_SEPHIROTH; new actor instance only',
          'generated_policy':'motion.evidence.json: separate guest-owned paired low-HP/death/defend motions derived from own poses; original decoder/rotation/command oracles',
          'limitations':'Procedural posture,floor contact and weapon grip require visual review; custom limits pending'}
        result['integration']={
          'plugin':'ff7.party-gameplay, developer default-off; shared activation owns lifecycle',
          'lifecycle':['ff7_party_battle_init allocates guest-owned AI/extent scratch and three independent motion arenas',
                       'ff7_party_battle_restore retains guest-backed bytes; no host character state'],
          'abi':{'INITIAL_RECORD':'v1=record(fp)-t1; original ADDU executes, including branch delay slot',
            'REFRESH_RECORD':'s1=record(a3) before original byte load',
            'ARENA_RECORD':'v1=record(a3)-0x8009C738 before native nine-record search and HP/MP writeback',
            'AI_ALIAS':'at points to FF byte through existing signed offset; s3 proxy unchanged',
            'AI_HEADER':'a0 points to27 FF halfwords, proxy s3 unchanged; original dispatcher returns no personal script',
            'MODEL':'v0=profile.presentation only when actor at s2 is extra, preserving native weapon variants11..15',
            'EXTENT':'first: a0,v1; others: v0,v1 point to extent selected through sorted actor-slot pair',
            'ALIAS':'specified load base points to scratch word containing proxy, native alias table untouched',
            'OFFSET':'specified source GPR becomes(record-0x8009C738)>>2 before original SLL by2',
            'MOTIONS':'s0 actor slot selects newly copied body; exact CRC and decoder guards; fallback pointers/damage bytes plus paired generated-motion pointers/low-HP/death scripts; no GPR changes'},
          'pending':['Limit moves/policy; BATINI skips limit setup for IDs>=9 and resident80015AFC safely returns127',
                     'Procedural motion visual validation and full battle/reward/field lifecycle',
                     'Personal AI intentionally absent; native characters retain their original scripts'],
        }
        return result
    finally:disc.reader.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disc',required=True,type=Path);parser.add_argument('--write',action='store_true')
    args=parser.parse_args();report=inspect(args.disc)
    if args.write:
        dest=ROOT/'mods/preloaded/packages/ff7.expanded-party/battle.evidence.json'
        dest.write_text(json.dumps(report,indent=2)+'\n',newline='\n')
        lines=['/* Generated from owner-disc instruction words by inspect_ff7_battle.py. */']
        for s in report['sites']:
            lines.append(' {0x%08xu,%s,%du,{%s}},' % (s['address'],s['action'],s['reg'],
                           ','.join('0x%08xu'%w for w in s['guard'])))
        (ROOT/'src/ff7_party_battle_sites.inc').write_text('\n'.join(lines)+'\n',newline='\n')
    print(json.dumps({'overlays':report['overlays'],'sites':len(report['sites'])}))
if __name__=='__main__':main()
