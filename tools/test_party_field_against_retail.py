"""Original MIPS full-heal and field entity/model routing with production adapters.

Entity/model test fixtures represent an already-created mod-owned actor. They
are not a Sephiroth field asset loader or a visual/story acceptance test.
"""
import argparse
import ctypes
import gzip
import json
import struct
from pathlib import Path
from inspect_ff7_party import Disc, ROOT, kernel_sections
from inspect_ff7_field_hooks import inspect
from test_party_rewards_against_retail import VM,rec

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--library',required=True,type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    lib=ctypes.CDLL(str(a.library.resolve()))
    for suffix in ('ram','expansion','reset','hook'):
        setattr(lib,'ff7_test_rewards_'+suffix,getattr(lib,'ff7_test_field_'+suffix))
    for n in ('ff7_test_rewards_ram','ff7_test_rewards_expansion'):getattr(lib,n).restype=ctypes.c_void_p
    lib.ff7_test_rewards_hook.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
    lib.ff7_party_field_bind.argtypes=[ctypes.c_uint16,ctypes.c_uint8]
    report=inspect(a.disc)
    assert report==json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/field-hooks.evidence.json').read_text())
    resident=json.loads((ROOT/'mods/preloaded/packages/ff7.expanded-party/resident.evidence.json').read_text())
    merged={'sites':report['sites']+resident['sites']}
    d=Disc(a.disc)
    try:
        exe=d.read(next(n for n in d.files if n.startswith('SCUS_')and '/'not in n))
        field=gzip.decompress(d.read('FIELD/FIELD.BIN')[8:]);kernel=kernel_sections(d.read('INIT/KERNEL.BIN'))
    finally:d.reader.close()
    def vm():
        v=VM(lib,merged,exe,b'',kernel);v.write(0x800a0000,field)
        v.write(0x800491d0,struct.pack('<11I',0,1,2,3,4,5,6,7,8,6,7))
        for address,index in ((0x800738a0,5),(0x80071e44,6),(0x80071c24,7),(0x800730d0,8)):
            v.write(address,kernel[index])
        return v
    cases=[]
    for g in (11,26):
        v=vm();v.write(0x8009cbdc,bytes([0,7,g]))
        template=bytearray(kernel[3][7*132:8*132]);template[0]=g
        v.write(rec(g),template)
        for identity in (0,7,g):
            v.write(rec(identity),bytes([identity]))
            v.half(rec(identity)+0x2c,1);v.half(rec(identity)+0x30,0);v.write(rec(identity)+0x1f,b'\x30')
        before=[v.read(rec(i),132)for i in range(9)]
        v.run(0x800d348c)
        for identity in(0,7,g):
            data=v.read(rec(identity),132)
            assert data[0]==identity and data[0x1f]==0
            assert data[0x2c:0x2e]==data[0x38:0x3a],(identity,data[0x2c:0x3c].hex())
            assert data[0x30:0x32]==data[0x3a:0x3c],(identity,data[0x2c:0x3c].hex())
        for i in range(9):
            if i not in(0,7):assert v.read(rec(i),132)==before[i]
        assert v.read(0x8009cbdc,3)==bytes([0,7,g])
    cases.append('Whole original D348C full-heal, including original resident derived stats and HP/MP routines: Cloud/Vincent/proxy11 or26 retain records, recover to maximum, clear status')
    def entities(v):
        v.word(0x8009c6dc,0x80110000);v.write(0x80110002,b'\x03')
        v.word(0x8007e770,0x80120000);v.half(0x80120002,3)
        v.word(0x8008357c,0x80121000);v.word(0x8009c6e0,0x80122000)
        v.write(0x8009ad30,b'\xff'*9);v.write(0x8009ad30,b'\0');v.write(0x8009ad37,b'\x01')
        v.write(0x8007eb98,b'\x00\x01\x02'+b'\xff'*61)
        for i in range(3):v.write(0x80121005+i*8,b'\x01')
    for g in(11,26):
        v=vm();entities(v);v.write(0x8009d391,bytes([g,0,7]));v.write(0x8009cbdc,bytes([g,0,7]))
        native=v.read(0x8009ad30,9);records=v.read(0x8009c738,9*132)
        assert lib.ff7_party_field_bind(0x100+g-11,2)
        v.write(0x80121015,b'\0');v.run(0x800bb1b4)
        assert v.read(0x80121015,1)==b'\x01'
        v.run(0x800ceb20);assert v.read(0x8012202a,2)==b'\x02\0'
        assert v.read(0x8009ad30,9)==native and v.read(0x8009c738,9*132)==records
        assert v.read(0x8009d391,3)==v.read(0x8009cbdc,3)==bytes([g,0,7])
        # The actual guarded original A0 PC stores route into the extra map;
        # rejected native collision writes go to scratch and keep prior binding.
        for pc,source in((0x800cec0c,4),(0x800ced54,3)):
            v.reg(1,0x8009ad30+g);v.reg(source,2);v.run(pc,pc+4)
            assert lib.ff7_party_field_entity(g)==2
            v.reg(1,0x8009ad30+g);v.reg(source,0);v.run(pc,pc+4)
            assert lib.ff7_party_field_entity(g)==2 and v.read(0x8009ad30,9)==native
        v.run(0x800baf00,0x800baf20);assert lib.ff7_party_field_entity(g)==255
        assert v.read(0x8009ad30,9)==b'\xff'*9
    cases.append('Whole original party-model enable and leader entity selection for an independent bound actor, plus PC opcode stores/collision rejection and native per-field reset; logical proxies preserved')
    # Unbound leader/model-enable paths explicitly test255 before model lookup.
    v=vm();entities(v);v.write(0x8009d391,b'\x0b\x00\x07');v.half(0x8012202a,77)
    v.run(0x800ceb20);assert v.read(0x8012202a,2)==b'M\0'
    cases.append('Unbound extra leader leaves existing leader selection intact; no AD30 out-of-range access')
    result={'disc':a.disc.name,'status':'passed','cases':cases,
      'limits':'Bound model/entity is a test fixture; automatic Sephiroth BSX actor injection, follower/script safety and visual gameplay remain pending'}
    if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
