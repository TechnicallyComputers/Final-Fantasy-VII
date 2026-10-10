"""Inventory Sephiroth's original field assets without extracting/distributing art.

Layout references are the primary reverse-engineering notes at the URLs below.
Model-relative skeleton offsets are independently confirmed by original FIELD
instructions AC534..AC544; no decompiled game or viewer source is used.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc,ROOT
from inspect_ff7_animations import decompress_lzs

REFERENCES=['https://wiki.ffrtt.ru/index.php/FF7/Field/BSX',
            'https://wiki.ffrtt.ru/index.php/FF7/Field/Field_Script',
            'https://wiki.ffrtt.ru/index.php/FF7/Field/Script/Opcodes/A1_CHAR']
CANDIDATES=[('NIVL','cefiros',3),('NIVL_B1','cefirth',1),('NIVL_B2','cefirth',1)]

def inventory(dat,bsx,entity_name,index):
    # Seven absolute original DAT pointers. Section1 starts after the28-byte
    # pointer table; section7 contains a4-byte header and8-byte model entries.
    pointers=struct.unpack_from('<7I',dat);script=dat[28:]
    if script[:2]!=b'\x02\x05':raise ValueError('Unknown script revision')
    nentities,nmodels=script[2:4];akaos=struct.unpack_from('<H',script,6)[0]
    names=[script[32+8*i:40+8*i].rstrip(b'\0').decode('ascii')for i in range(nentities)]
    entity=names.index(entity_name);table=32+8*nentities+4*akaos
    entry=struct.unpack_from('<H',script,table+64*entity)[0]
    if script[entry:entry+2]!=bytes([0xa1,index]):raise ValueError('Candidate no longer defines expected visible model')
    # The index is also checked against visible entities in original init order,
    # rather than trusting CHAR's argument as a universal model selector.
    visible=[]
    for i in range(nentities):
        start=struct.unpack_from('<H',script,table+64*i)[0]
        if script[start]==0xa1:visible.append(i)
    if visible[index]!=entity or len(visible)!=nmodels:raise ValueError('Unexpected entity/model ordering')
    section7=pointers[6]-pointers[0]+28
    size,models=struct.unpack_from('<HH',dat,section7)
    if models!=nmodels or size!=4+models*8:raise ValueError('Invalid model metadata')
    metadata=dat[section7+4+index*8:section7+12+index*8]
    file_size,models_offset=struct.unpack_from('<II',bsx)
    if file_size!=len(bsx):raise ValueError('Invalid BSX size')
    _,count,texture_offset,buffer_size=struct.unpack_from('<4I',bsx,models_offset)
    if count!=nmodels:raise ValueError('BSX/DAT model mismatch')
    header=models_offset+16+48*index
    bones,parts,animations=(bsx[header+i]for i in(23,35,47))
    if (bones,parts,animations)!=tuple(metadata[1:4]):raise ValueError('Candidate needs a global BCX base')
    skeleton=header+struct.unpack_from('<I',bsx,header+4)[0]
    if skeleton+4*bones+32*parts+16*animations>len(bsx):raise ValueError('Truncated skeleton')
    parents=[]
    for i in range(bones):
        parent=struct.unpack_from('<b',bsx,skeleton+4*i+2)[0]
        if not -1<=parent<i:raise ValueError('Invalid bone hierarchy')
        parents.append(parent)
    vertices=[]
    for i in range(parts):
        p=skeleton+4*bones+32*i;vertex=struct.unpack_from('<I',bsx,p+24)[0]&0x7fffffff
        if vertex+4+bsx[p+2]*8>models_offset:raise ValueError('Vertex data outside geometry section')
        vertices.append(bsx[p+2])
    motions=[]
    for i in range(animations):
        p=skeleton+4*bones+32*parts+16*i
        frames=struct.unpack_from('<H',bsx,p)[0];n=bsx[p+2]
        data=struct.unpack_from('<I',bsx,p+12)[0]&0x7fffffff
        if not frames or n!=bones or data+4+8*n>models_offset:raise ValueError('Invalid motion channels')
        offsets=struct.unpack_from('<3H',bsx,p+6)
        for offset,length in zip(offsets,(bsx[p+3]*frames,bsx[p+4]*2,bsx[p+5]*frames)):
            if data+offset+length>models_offset:raise ValueError('Motion stream outside data section')
        motions.append({'frames':frames,'bones':n,'channels_offset':data})
    return {'entity_name':entity_name,'entity_index':entity,'model_index':index,
      'script_entry':entry,'dat_model_metadata_offset':section7+4+index*8,
      'bsx_descriptor_offset':header,'skeleton_offset':skeleton,
      'bones':bones,'parts':parts,'vertices':vertices,'motions':motions,
      'texture_section_offset':models_offset+texture_offset,'all_models_buffer_size':buffer_size,
      'dat_sha256':hashlib.sha256(dat).hexdigest(),'bsx_sha256':hashlib.sha256(bsx).hexdigest()}

def inspect(cue):
    d=Disc(cue)
    try:
        r={'schema':1,'basis':'Owner-disc bytes; reviewed primary format notes; original loader offset arithmetic',
           'references':REFERENCES,'native_bcx':sorted(n for n in d.files if n.endswith('.BCX')),'candidates':[]}
        for field,name,index in CANDIDATES:
            dat=decompress_lzs(d.read('FIELD/'+field+'.DAT'));bsx=decompress_lzs(d.read('FIELD/'+field+'.BSX'))
            candidate=inventory(dat,bsx,name,index);candidate['field']=field;r['candidates'].append(candidate)
        r['pending']=['No standalone Sephiroth BCX exists on these discs',
          'Model descriptor must become a new mod-owned model/entity; never reuse the existing scripted NPC',
          'Portable asset needs texture ownership/VRAM allocation, relative-pointer relocation, animation role mapping and per-field buffer growth',
          'Native script entities have a64-entry mapping; added script rows/initialization and follower/leader controls require separate integration',
          'Static hierarchy/stream bounds are validated; poses, motion roles and rendered appearance are not yet validated']
        return r
    finally:d.reader.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--write',action='store_true');a=p.parse_args();r=inspect(a.disc)
    path=ROOT/'mods/preloaded/packages/ff7.expanded-party/field-assets.evidence.json'
    if a.write:path.write_text(json.dumps(r,indent=2)+'\n')
    else:assert r==json.loads(path.read_text()),'Disc assets differ'
    print(json.dumps({'candidates':[{k:c[k]for k in('field','entity_name','model_index','bones','parts','motions')}for c in r['candidates']]}))
if __name__=='__main__':main()
