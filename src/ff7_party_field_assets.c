#include "ff7_party_field_assets.h"
#include <string.h>

static uint16_t u16(const uint8_t* p){return (uint16_t)(p[0]|((unsigned)p[1]<<8));}
static uint32_t u32(const uint8_t* p){return (uint32_t)u16(p)|((uint32_t)u16(p+2)<<16);}
static void w16(uint8_t* p,unsigned v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void w32(uint8_t* p,uint32_t v){w16(p,v);w16(p+2,v>>16);}
static int span(size_t at,size_t n,size_t bytes){return at<=bytes && n<=bytes-at;}
static size_t aligned(size_t n){return (n+3u)&~(size_t)3u;}

size_t ff7_field_decode_lzs(const uint8_t* in,size_t n,uint8_t* out,size_t capacity){
    if(!in || !out || n<4 || u32(in)!=n-4)return 0;
    uint8_t ring[4096]={0};unsigned pos=0xfee;size_t at=4,used=0;
    while(at<n){
        unsigned flags=in[at++];
        for(unsigned bit=0;bit<8 && at<n;++bit){
            if(flags&(1u<<bit)){
                if(used>=capacity)return 0;
                uint8_t value=in[at++];out[used++]=value;ring[pos]=value;pos=(pos+1)&4095;
            }else{
                if(n-at<2)return 0;
                unsigned offset=in[at]|((in[at+1]&0xf0u)<<4),count=(in[at+1]&15u)+3;at+=2;
                if(count>capacity-used)return 0;
                for(unsigned i=0;i<count;++i){uint8_t value=ring[(offset+i)&4095];
                    out[used++]=value;ring[pos]=value;pos=(pos+1)&4095;}
            }
        }
    }
    return used;
}

size_t ff7_field_append_script(const uint8_t* in,size_t n,const uint8_t* guests,
                              unsigned count,uint8_t* out,size_t capacity){
    if(!in || !guests || !out || n<32 || n>65535 || !count || count>16 || u16(in)!=0x502)return 0;
    unsigned entities=in[2],models=in[3],akao=u16(in+6);
    if(entities+count>64 || models+count>32)return 0;
    size_t names=32+entities*8u,table=names+akao*4u,end=table+entities*64u;
    size_t delta=count*72u,total=n+delta+count*40u;
    if(end>n || total>65535 || total>capacity || u16(in+4)<end || u16(in+4)>n)return 0;
    for(unsigned i=0;i<count;++i){
        if(guests[i]<11 || guests[i]>26)return 0;
        for(unsigned j=0;j<i;++j)if(guests[j]==guests[i])return 0;
    }
    for(unsigned i=0;i<akao;++i)if(u32(in+names+4*i)<end || u32(in+names+4*i)>=n)return 0;
    for(unsigned i=0;i<entities*32u;++i)if(u16(in+table+2*i)<end || u16(in+table+2*i)>=n)return 0;
    /* The runtime's guarded CHAR adapter gives appended entities independent
     * state indices. It preserves the native counter even when a field creates
     * an original actor later (SEMKIN_3); script order alone is insufficient. */
    memset(out,0,total);memcpy(out,in,names);
    out[2]=(uint8_t)(entities+count);out[3]=(uint8_t)(models+count);w16(out+4,u16(in+4)+(unsigned)delta);
    for(unsigned i=0;i<count;++i){
        uint8_t* name=out+names+8*i;memcpy(name,"extra",5);name[5]=(uint8_t)('A'+i);
    }
    for(unsigned i=0;i<akao;++i)w32(out+names+count*8u+4*i,u32(in+names+4*i)+(uint32_t)delta);
    size_t new_table=table+count*8u;
    for(unsigned i=0;i<entities*32u;++i)w16(out+new_table+2*i,u16(in+table+2*i)+(unsigned)delta);
    memcpy(out+end+delta,in+end,n-end);
    for(unsigned i=0;i<count;++i){
        size_t start=n+delta+40*i;uint8_t* code=out+start;
        /* Original engine creates the independently assigned model, binds party
         * identity, selects animation0/speed1, then returns from init. All
         * remaining script entries have distinct RET bytes, preserving the
         * retail script-row convention. No story-NPC scripts are copied. */
        code[0]=0xa1;code[1]=(uint8_t)(models+i);code[2]=0xa0;code[3]=guests[i];
        code[4]=0xa2;code[5]=0;code[6]=1;code[7]=0;
        size_t row=new_table+64u*(entities+i);w16(out+row,(unsigned)start);
        for(unsigned j=1;j<32;++j)w16(out+row+2*j,(unsigned)(start+8+j));
    }
    return total;
}

typedef struct ModelView{size_t header,skeleton;unsigned bones,parts,animations;uint32_t packets;}ModelView;
static int view(const FF7FieldAssetSource* source,ModelView* v){
    if(!source || !source->bsx || source->size<24 || source->size>0x100000 || u32(source->bsx)!=source->size)return 0;
    const uint8_t* p=source->bsx;size_t models=u32(p+4);
    if(!span(models,16,source->size))return 0;
    unsigned count=u32(p+models+4);
    if(count>32 || source->model>=count || !span(models+16,count*48u,source->size))return 0;
    v->header=models+16+48u*source->model;
    v->bones=p[v->header+23];v->parts=p[v->header+35];v->animations=p[v->header+47];
    if(!v->bones || !v->parts || !v->animations || p[v->header+18]!=0 || p[v->header+30]!=0 || p[v->header+42]!=0)return 0;
    v->skeleton=v->header+u32(p+v->header+4);
    if(!span(v->skeleton,4u*v->bones+32u*v->parts+16u*v->animations,source->size))return 0;
    v->packets=16u*v->bones;
    for(unsigned i=0;i<v->bones;++i){int parent=(int8_t)p[v->skeleton+4*i+2];if(parent<-1 || parent>=(int)i)return 0;}
    for(unsigned i=0;i<v->parts;++i){
        const uint8_t* part=p+v->skeleton+4u*v->bones+32u*i;uint32_t pointer=u32(part+24);
        if((pointer&0xfff00000u)!=0x80000000u || !span(pointer&0xfffffu,4u+part[2]*8u,models))return 0;
        v->packets+=u16(part+22);
    }
    v->packets*=2;
    for(unsigned i=0;i<v->animations;++i){
        const uint8_t* motion=p+v->skeleton+4u*v->bones+32u*v->parts+16u*i;
        uint32_t pointer=u32(motion+12);unsigned frames=u16(motion);
        if(!frames || motion[2]!=v->bones || (pointer&0xfff00000u)!=0x80000000u ||
           !span(pointer&0xfffffu,4u+8u*v->bones,models))return 0;
        unsigned lengths[3]={motion[3]*frames,motion[4]*2u,motion[5]*frames};
        for(unsigned j=0;j<3;++j)if(!span((pointer&0xfffffu)+u16(motion+6+2*j),lengths[j],models))return 0;
    }
    return 1;
}
int ff7_field_asset_metadata(const FF7FieldAssetSource* source,uint8_t output[8]){
    ModelView v;if(!output || !view(source,&v))return 0;
    memset(output,0,8);output[0]=source->bsx[v.header];output[1]=(uint8_t)v.bones;
    output[2]=(uint8_t)v.parts;output[3]=(uint8_t)v.animations;output[5]=1;
    return 1;
}
size_t ff7_field_append_models(const uint8_t* in,size_t n,const FF7FieldAssetSource* sources,
                              unsigned count,uint8_t* out,size_t capacity,size_t* reserve){
    if(!in || !sources || !out || !reserve || n<24 || n>0x100000 || u32(in)!=n || !count || count>16)return 0;
    size_t original=u32(in+4);if(!span(original,16,n))return 0;
    unsigned old_count=u32(in+original+4),new_count=old_count+count;
    if(new_count>32 || !span(original+16,old_count*48u,n))return 0;
    size_t texture=original+u32(in+original+8);if(!span(texture,8,n))return 0;
    ModelView views[16];size_t starts[16],cursor=aligned(n);uint32_t packets=u32(in+original+12);
    if(packets>0x400000)return 0;
    for(unsigned i=0;i<count;++i){
        if(!view(&sources[i],&views[i]))return 0;
        /* Current portable sources must use the shared FIELD.TDB only. Local
         * texture pages need a future allocation/relocation policy. */
        size_t m=u32(sources[i].bsx+4),t=m+u32(sources[i].bsx+m+8);
        if(!span(t,8,sources[i].size) || sources[i].bsx[t+4])return 0;
        starts[i]=cursor;cursor+=aligned(sources[i].size);packets+=views[i].packets;
    }
    size_t models=cursor,total=models+16+new_count*48u,required=models+packets+new_count*48u;
    if(required<total)required=total;
    if(required>capacity || total>0x1000000u)return 0;
    for(unsigned i=0;i<old_count;++i){
        size_t h=original+16+48*i,s=h+u32(in+h+4);
        size_t size=4u*in[h+23]+32u*in[h+35]+16u*in[h+47];
        if(!span(s,size,n))return 0;
    }
    memset(out,0,required);memcpy(out,in,n);
    for(unsigned i=0;i<count;++i)memcpy(out+starts[i],sources[i].bsx,sources[i].size);
    w32(out,(uint32_t)total);w32(out+4,(uint32_t)models);
    w32(out+models,0x80000000u+(uint32_t)models);w32(out+models+4,new_count);
    w32(out+models+8,(uint32_t)(texture-models));w32(out+models+12,packets);
    for(unsigned i=0;i<old_count;++i){
        size_t before=original+16+48*i,after=models+16+48*i;
        memcpy(out+after,in+before,48);w32(out+after+4,(uint32_t)(before+u32(in+before+4)-after));
    }
    for(unsigned i=0;i<count;++i){
        const ModelView* v=&views[i];size_t after=models+16+48u*(old_count+i),skeleton=starts[i]+v->skeleton;
        memcpy(out+after,sources[i].bsx+v->header,48);w32(out+after+4,(uint32_t)(skeleton-after));
        for(unsigned j=0;j<v->parts;++j){uint8_t* p=out+skeleton+4u*v->bones+32u*j;
            w32(p+24,u32(p+24)+(uint32_t)starts[i]);}
        for(unsigned j=0;j<v->animations;++j){uint8_t* p=out+skeleton+4u*v->bones+32u*v->parts+16u*j;
            w32(p+12,u32(p+12)+(uint32_t)starts[i]);}
    }
    *reserve=required;return total;
}
