"""Evidence and execution tests for original field party banks and reset paths.

Reports candidate integration seams, not an enabled field-model implementation.
Uses only owner-disc binaries. No game asset bytes are emitted to the repository.
"""
import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, EXE_SHA1
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0, UC_MIPS_REG_PC

SITES={
 'FIELD':[(0x800cf5a0,'bank_to_active_entry'),(0x800cf5f4,'bank_to_active_complete'),
          (0x800cf60c,'active_to_bank_entry'),(0x800cf654,'active_to_bank_complete'),
          (0x800cf478,'party_replace_bank_store'),
          (0x800bb1f0,'party_model_map_read'),(0x800ceb40,'leader_model_map_read'),
          (0x800d34f0,'restore_party_alias_read'),(0x800d34f8,'restore_party_native_range'),
          (0x800d350c,'restore_party_record_stride')],
 'RETAIL':[(0x80011dbc,'selected_new_game_after_native_reset'),
           (0x80033b68,'native_party_reset_complete')]}
FUNCTIONS={'FIELD':[(0x800cf368,0x800cf4cc),(0x800cf4cc,0x800cf5a0),
                  (0x800cf5a0,0x800cf60c),(0x800cf60c,0x800cf66c),
                  (0x800cf66c,0x800cf6c0),(0x800cf6c0,0x800cf718),
                  (0x800bb1b4,0x800bb3a8),(0x800ceb20,0x800ceb94),
                  (0x800d348c,0x800d3548)],
           'RETAIL':[(0x80033a90,0x80033b70),(0x80011bb4,0x80011c1c),
                     (0x80014934,0x80014980)]}

def inspect(cue):
    d=Disc(cue)
    try:
        exe=d.read(next(n for n in d.files if n.startswith('SCUS_')and '/'not in n))
        field=gzip.decompress(d.read('FIELD/FIELD.BIN')[8:])
    finally:d.reader.close()
    if hashlib.sha1(exe).hexdigest()!=EXE_SHA1:raise ValueError('Unsupported executable')
    images={'RETAIL':(exe[0x800:],0x80010000),'FIELD':(field,0x800a0000)}
    report={'schema':1,'basis':'Independent original-disc MIPS inspection and execution',
            'images':{},'sites':[],'functions':[]}
    for name,(data,base) in images.items():
        report['images'][name]={'base':base,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        for pc,role in SITES[name]:
            words=list(struct.unpack_from('<13I',data,pc-base-24))
            report['sites'].append(dict(image=name,address=pc,expected=words[6],role=role,guard=words))
        for start,end in FUNCTIONS[name]:
            report['functions'].append(dict(image=name,start=start,end_exclusive=end,
               sha256=hashlib.sha256(data[start-base:end-base]).hexdigest()))
    cases=[]
    def machine():
        u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN);u.mem_map(0,0x200000)
        for data,base in images.values():u.mem_write(base&0x1fffffff,data)
        u.reg_write(UC_MIPS_REG_0+29,0x801ff000);u.reg_write(UC_MIPS_REG_0+31,0x80001000)
        return u
    def run(u,pc,end=0x80001000):
        u.emu_start(pc,end,count=100000)
        assert u.reg_read(UC_MIPS_REG_PC) in (end,end-4)
    for guest in (11,26):
        for start,source,dest in ((0x800cf60c,0x9cbdc,0x9d391),(0x800cf5a0,0x9d391,0x9cbdc)):
            u=machine();u.mem_write(source,bytes([0,7,guest]));u.mem_write(dest,b'\x00\xff\xff')
            run(u,start);assert bytes(u.mem_read(dest,3))==bytes([0,7,guest])
            assert bytes(u.mem_read(source,3))==bytes([0,7,guest])
            if start==0x800cf5a0:assert bytes(u.mem_read(0x71e34,1))==b'\x01'
    cases.append('Both complete original field bank transfers preserve Cloud/Vincent/proxy11 or26 without native aliasing')
    u=machine();u.mem_write(0x9d288,b'\xaa'*1280);u.mem_write(0x9cbdc,b'\x0b\x07\x00')
    run(u,0x80033a90)
    assert bytes(u.mem_read(0x9cbdc,3))==bytes(u.mem_read(0x9d391,3))==b'\0\xff\xff'
    assert bytes(u.mem_read(0x9d78a,2))==b'\x01\0'
    cases.append('Complete native reset clears story-variable bank, selects Cloud alone in both party banks and availability bit0')
    for selected in (0,1,2):
        u=machine();u.reg_write(UC_MIPS_REG_0+2,selected);u.reg_write(UC_MIPS_REG_0+17,1)
        u.mem_write(0x9cbdc,b'\x0b\x07\x00');u.mem_write(0x9d391,b'\x07\x0b\x00')
        # Isolate kernel CD reload/settings reset, while executing the entire
        # native party reset and initial-story/map defaults normally.
        for pc in (0x80014934,0x80026258):u.mem_write(pc&0x1fffffff,struct.pack('<II',0x03e00008,0))
        visited=[];u.hook_add(UC_HOOK_CODE,lambda uc,pc,size,arg:visited.append(pc))
        run(u,0x80011d9c,0x80011dc4)
        assert (0x80011dbc in visited)==(selected==1)
        assert bytes(u.mem_read(0x9cbdc,3))==(b'\0\xff\xff'if selected==1 else b'\x0b\x07\x00')
        if selected==1:assert bytes(u.mem_read(0x9d27a,2))==b'\x74\0'
    cases.append('Original title-result branch executes11DBC only for result1; resets party and starts map0x74, skips for0/2')
    report['observations']={
      'stored_bank':{'ram':0x8009d391,'bytes':3,'offset_from_8009c6e4':0xcad,
        'writes':['CF60C copies current party through generic remove/add helpers',
                  'CF368 merges requested party then writes bank atCF478',
                  'Field script member-add/remove operations also mutate this bank'],
        'policy':'Canonicalize this exact bank in save metadata; do not rewrite unrelated save-map variables'},
      'new_game':{'seam':0x80011dbc,'basis':'After menu result1, kernel section3 reload14934, settings26258 and party/story reset33A90; before initial map defaults11BB4',
        'caution':'33A90 also runs before title menu at11D8C, so its return alone is not a new-game-only notification'},
      'remaining_field':[
        '8009AD30 is a native character-to-field-entity map: BB1F0 enables party models; CEB40 selects leader entity',
        'Battle presentation10 is not a field entity index or portable field model. Per-field assets/entity policy remain unresolved',
        'D348C full-heal path calls already adapted resident heal functions but additionally aliases ID atD34F0, native<9 guardD34F8 and132-byte strideD350C to clear record status+1F',
        'More field script operations read bank IDs and map through8009AD30; do not globally substitute native ID10',
        'Community0xBAB offset was not established as a party bank by this inspection; only CAD is verified here']}
    report['execution_tests']=cases
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--write',action='store_true');a=p.parse_args();r=inspect(a.disc)
    path=ROOT/'mods/preloaded/packages/ff7.expanded-party/field-party.evidence.json'
    if a.write:path.write_text(json.dumps(r,indent=2)+'\n')
    else:assert r==json.loads(path.read_text()),'Disc evidence differs'
    print(json.dumps({'images':r['images'],'cases':r['execution_tests']}))
if __name__=='__main__':main()
