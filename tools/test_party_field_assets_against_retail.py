"""Verify owned-disc field relocation using original MIPS model initialization.

No art is emitted. Device texture uploads are stubbed; rendering is not tested.
"""
import argparse,ctypes,gzip,json,struct
from pathlib import Path
from unicorn import Uc,UC_ARCH_MIPS,UC_MODE_MIPS32,UC_MODE_LITTLE_ENDIAN
from unicorn.mips_const import UC_MIPS_REG_0,UC_MIPS_REG_PC
from inspect_ff7_party import Disc
from inspect_ff7_animations import decompress_lzs

class Source(ctypes.Structure):
    _fields_=[('bsx',ctypes.c_void_p),('size',ctypes.c_size_t),('model',ctypes.c_uint)]
def u32(b,p=0):return struct.unpack_from('<I',b,p)[0]
def metadata(dat):return dat[u32(dat,24)-u32(dat)+28:]
def load_model(field,bsx,meta,index):
    uc=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN)
    uc.mem_map(0,0x200000);uc.mem_map(0x800000,0x600000)
    def wr(p,b):uc.mem_write(p&0x1fffffff,bytes(b))
    def rd(p,n):return bytes(uc.mem_read(p&0x1fffffff,n))
    def reg(n,v):uc.reg_write(UC_MIPS_REG_0+n,v&0xffffffff)
    def run(pc,end):
        uc.emu_start(pc,end,count=2000000)
        assert uc.reg_read(UC_MIPS_REG_PC)==end
    wr(0x800a0000,field);wr(0x80800000,bsx)
    m=bytearray(meta)
    for i in range(struct.unpack_from('<H',m,2)[0]):m[4+8*i+5]=int(i==index);m[4+8*i+7]=0
    wr(0x80110000,m)
    reg(29,0x801ff000);reg(31,0x80001000);reg(4,0x80110000);reg(5,0x80d00000)
    run(0x800adaa4,0x80001000)
    for pc in(0x800ad858,0x800ad7b8,0x80043dd8):wr(pc,struct.pack('<II',0x03e00008,0x00001021))
    wr(0x801ff038,struct.pack('<I',0x80110004));reg(17,0x80800000);reg(21,0x80d00000)
    run(0x800ac484,0x800ac744)
    instance=rd(0x80d0000c,36);bones,parts,motions=instance[2:5];skeleton=u32(instance,28)
    data=bytearray(rd(skeleton,4*bones+32*parts+16*motions))
    geometry=[];animation=[]
    for i in range(parts):
        at=4*bones+32*i;p=u32(data,at+24)
        geometry.append(rd(p,4+data[at+2]*8));struct.pack_into('<I',data,at+24,0)
    for i in range(motions):
        at=4*bones+32*parts+16*i;p=u32(data,at+12);frames=struct.unpack_from('<H',data,at)[0]
        offsets=struct.unpack_from('<3H',data,at+6)
        size=max([4+8*bones]+[o+n for o,n in zip(offsets,(data[at+3]*frames,data[at+4]*2,data[at+5]*frames))])
        animation.append(rd(p,size));struct.pack_into('<I',data,at+12,0)
    # Build both original DMA buffers for every part. Native scale uses GTE;
    # isolate that separately from packet layout/texture coordinate generation.
    wr(0x800af6ec,struct.pack('<II',0x03e00008,0x00001021))
    packet_base=0x80800000+u32(bsx,4)
    expected_size=32*bones+sum(2*struct.unpack_from('<H',data,4*bones+32*i+22)[0]for i in range(parts))
    # Coordinate/matrix words belong to later GTE steps, so initialize both
    # scratch regions equally before comparing bytes written by this builder.
    wr(packet_base,b'\0'*expected_size)
    reg(4,0x80d0000c);reg(5,packet_base);reg(6,0);reg(31,0x80001000)
    run(0x800acba0,0x80001000)
    packet_end=uc.reg_read(UC_MIPS_REG_0+2)
    assert packet_end-packet_base==expected_size
    packets=rd(packet_base,expected_size)
    return (bytes(data),geometry,animation,packets)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disc',required=True,type=Path)
    p.add_argument('--library',required=True,type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    lib=ctypes.CDLL(str(a.library.resolve()))
    lib.ff7_field_append_models.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(Source),ctypes.c_uint,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
    lib.ff7_field_append_models.restype=ctypes.c_size_t
    lib.ff7_field_append_script.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_uint,ctypes.c_void_p,ctypes.c_size_t]
    lib.ff7_field_append_script.restype=ctypes.c_size_t
    d=Disc(a.disc)
    try:
        field=gzip.decompress(d.read('FIELD/FIELD.BIN')[8:])
        raw={n:decompress_lzs(d.read('FIELD/'+n))for n in('NIVL.DAT','NIVL.BSX','MD1STIN.DAT','MD1STIN.BSX')}
    finally:d.reader.close()
    source=ctypes.create_string_buffer(raw['NIVL.BSX']);sources=(Source*1)(Source(ctypes.addressof(source),len(source)-1,3))
    out=ctypes.create_string_buffer(0x400000);reserve=ctypes.c_size_t()
    original=raw['MD1STIN.BSX'];n=lib.ff7_field_append_models(original,len(original),sources,1,out,len(out),ctypes.byref(reserve))
    assert n and n<=reserve.value<=len(out)
    merged=out.raw[:reserve.value];meta=bytearray(metadata(raw['MD1STIN.DAT']));count=struct.unpack_from('<H',meta,2)[0]
    meta=meta[:4+count*8];extra=(ctypes.c_ubyte*8)();assert lib.ff7_field_asset_metadata(ctypes.byref(sources[0]),extra)
    meta.extend(extra);struct.pack_into('<HH',meta,0,len(meta),count+1)
    expected=load_model(field,raw['NIVL.BSX'],metadata(raw['NIVL.DAT']),3)
    actual=load_model(field,merged,meta,count);assert actual==expected
    many=(Source*16)(*(sources[0]for _ in range(16)))
    many_bytes=lib.ff7_field_append_models(original,len(original),many,16,out,len(out),ctypes.byref(reserve))
    assert many_bytes
    many_meta=bytearray(meta[:-8]);many_meta.extend(bytes(extra)*16)
    struct.pack_into('<HH',many_meta,0,len(many_meta),count+16)
    assert load_model(field,out.raw[:reserve.value],many_meta,count+15)==expected
    dat=raw['MD1STIN.DAT'];script=dat[28:28+u32(dat,4)-u32(dat)]
    transformed=ctypes.create_string_buffer(65536);length=lib.ff7_field_append_script(script,len(script),b'\x0b',1,transformed,len(transformed))
    assert length==len(script)+112
    result=transformed.raw[:length];entities=script[2];akao=struct.unpack_from('<H',script,6)[0]
    table=32+8*entities+4*akao;newtable=table+8;end=table+64*entities
    assert result[end+72:len(script)+72]==script[end:]
    for i in range(entities*32):assert struct.unpack_from('<H',result,newtable+2*i)[0]==struct.unpack_from('<H',script,table+2*i)[0]+72
    assert result[len(script)+72:len(script)+80]==bytes([0xa1,script[3],0xa0,11,0xa2,0,1,0])
    assert not lib.ff7_field_append_models(original,len(original),sources,1,out,64,ctypes.byref(reserve))
    assert not lib.ff7_field_append_script(script,len(script),b'\x0a',1,transformed,len(transformed))
    report={'disc':a.disc.name,'status':'passed','cases':['Original ADAA4 model allocation plus AC484..AC744 relocation: appended NIVL model3 in MD1STIN equals original24 bones,16 parts,7 motions and referenced vertex/motion bytes','Original ACBA0/ACC5C builds identical double-buffered GPU packets and consumes exactly reserved packet bytes','16 appended independent copies: last model still matches original geometry/motions/packets','Original script entity numbers/code bytes and all32 offsets per existing entity preserved; independent proxy11 init appended','Small capacity and native-identity insertion rejected'],'merged_bytes_one_extra':n,'packet_reserve_16_extras':reserve.value,'limitations':'Texture uploads and GTE scaling stubbed; full script initialization and visual field gameplay not covered'}
    if a.output:a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
