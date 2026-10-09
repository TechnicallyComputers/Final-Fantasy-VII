#include "ff7_party_projection.h"
#include <string.h>

static uint16_t half(const uint8_t* p) { return p[0] | (uint16_t)p[1]<<8; }
static void put_half(uint8_t* p,uint16_t n) { p[0]=(uint8_t)n; p[1]=(uint8_t)(n>>8); }

uint16_t ff7_native_save_checksum(const uint8_t* save) {
    uint16_t crc=0xffff;
    if(!save)return 0;
    for(unsigned i=4;i<FF7_NATIVE_SAVE_BYTES;++i){
        crc^=(uint16_t)save[i]<<8;
        for(unsigned bit=0;bit<8;++bit)
            crc=(uint16_t)((crc<<1)^((crc&0x8000u)?0x1021u:0));
    }
    return (uint16_t)~crc;
}
int ff7_native_save_valid(const uint8_t* save,size_t size) {
    return save && size==FF7_NATIVE_SAVE_BYTES && save[2]==0 && save[3]==0 &&
        half(save)==ff7_native_save_checksum(save);
}
static int native(uint8_t id) { return id<=10 || id==255; }
static uint8_t native_row(uint8_t id) { return id==9?6:id==10?7:id; }
static int used(const uint8_t party[3],uint8_t id) {
    for(unsigned i=0;i<3;++i)if(native_row(party[i])==native_row(id))return 1;
    return 0;
}
int ff7_native_save_project(uint8_t* save,size_t size,const uint8_t fallback[3]) {
    uint8_t party[3];
    int changed=0;
    if(!save || size!=FF7_NATIVE_SAVE_BYTES || !fallback)return 0;
    for(unsigned i=0;i<3;++i){
        if(!native(fallback[i]))return 0;
        for(unsigned j=0;j<i;++j)
            if(fallback[i]!=255 && native_row(fallback[i])==native_row(fallback[j]))return 0;
        uint8_t id=save[FF7_NATIVE_ACTIVE_OFFSET+i];
        party[i]=native(id)?id:255;
        if(!native(id))changed=1;
        if(!native(save[FF7_NATIVE_STORED_OFFSET+i]))changed=1;
    }
    if(!changed)return ff7_native_save_valid(save,size);
    for(unsigned i=0;i<3;++i){
        if(native(save[FF7_NATIVE_ACTIVE_OFFSET+i]))continue;
        uint8_t candidate=fallback[i];
        if(candidate==255 || used(party,candidate)){
            candidate=255;
            for(unsigned j=0;j<3;++j)
                if(fallback[j]!=255 && !used(party,fallback[j])){
                    candidate=fallback[j];break;
                }
        }
        party[i]=candidate;
    }
    memcpy(save+FF7_NATIVE_ACTIVE_OFFSET,party,3);
    memcpy(save+5,party,3);
    /* Verified FIELD CF60C/CF5A0 store/restore this three-byte bank. */
    uint8_t stored[3];
    for(unsigned i=0;i<3;++i){
        uint8_t id=save[FF7_NATIVE_STORED_OFFSET+i];stored[i]=native(id)?id:255;
    }
    for(unsigned i=0;i<3;++i)
        if(!native(save[FF7_NATIVE_STORED_OFFSET+i])){
            uint8_t candidate=fallback[i];
            stored[i]=(candidate!=255 && !used(stored,candidate))?candidate:255;
        }
    memcpy(save+FF7_NATIVE_STORED_OFFSET,stored,3);
    /* Stock9/10 retain their alias semantics in story saves. */
    unsigned leader=0;
    while(leader<3 && party[leader]==255)++leader;
    if(leader<3){
        unsigned row=party[leader];
        if(row==9)row=6; else if(row==10)row=7;
        const uint8_t* record=save+0x54+row*132;
        save[4]=record[1];
        memcpy(save+8,record+0x10,16);
        put_half(save+0x18,half(record+0x2c));
        put_half(save+0x1a,half(record+0x38));
        put_half(save+0x1c,half(record+0x30));
        put_half(save+0x1e,half(record+0x3a));
    }
    put_half(save,ff7_native_save_checksum(save));save[2]=save[3]=0;
    return 1;
}
