#include "ff7_party_field_loader.h"
#include "ff7_party_field_assets.h"
#include "ff7_party_field.h"
#include "ff7_party_game.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

enum {SCRIPT_BYTES=65536,META_BYTES=260,WORK_BYTES=0x100000,MODEL_BYTES=0x400000,NATIVE_STATE_CAPACITY=16};
enum LoaderAction {PREPARE,MODELS};
typedef struct {uint32_t pc;enum LoaderAction action;uint32_t words[13];} LoaderSite;
static const LoaderSite s_sites[]={
#include "ff7_party_field_loader_sites.inc"
};
/* Arena addresses are immutable for one activation; active field and previous
 * native workspace live in rewindable guest memory. No external file writes. */
static uint32_t s_script,s_metadata,s_control,s_workspace,s_models;
static uint16_t u16(const uint8_t* p){return (uint16_t)(p[0]|((unsigned)p[1]<<8));}
static uint32_t u32(const uint8_t* p){return u16(p)|((uint32_t)u16(p+2)<<16);}
static void put16(uint8_t* p,unsigned n){p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);}
static int ram(uint32_t p,size_t n){p&=0x1fffffffu;return n<=0x200000 && p>=0x10000 && p<=0x200000-n;}
static void read_bytes(uint32_t p,uint8_t* b,size_t n){for(size_t i=0;i<n;++i)b[i]=psx_mod_read_byte(p+(uint32_t)i);}
static void write_bytes(uint32_t p,const uint8_t* b,size_t n){for(size_t i=0;i<n;++i)psx_mod_write_byte(p+(uint32_t)i,b[i]);}
static uint8_t* file(const char* path,size_t* n){
    uint32_t size=0;if(!psx_mod_read_disc_file(path,NULL,0,&size) || size<4 || size>0x100000)return NULL;
    uint8_t* compressed=malloc(size);uint8_t* decoded=malloc(0x100000);
    if(!compressed || !decoded){free(compressed);free(decoded);return NULL;}
    if(!psx_mod_read_disc_file(path,compressed,size,&size))*n=0;
    else *n=ff7_field_decode_lzs(compressed,size,decoded,0x100000);
    free(compressed);if(!*n){free(decoded);return NULL;}return decoded;
}
static int guards(void){
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
        for(unsigned j=0;j<13;++j)if(psx_mod_read_word(s_sites[i].pc-24+4*j)!=s_sites[i].words[j])return 0;
    return 1;
}
static int prepare(CPUState* cpu){
    uint32_t script=cpu->gpr[6],header=script-28,next,metadata;
    uint8_t* input=NULL;uint8_t* bsx=NULL;uint8_t* output=NULL;uint8_t* model_output=NULL;
    FF7FieldAssetSource sources[16]={{0}};uint8_t guests[16],meta[META_BYTES];unsigned count=0;
    size_t n=0,bsx_bytes=0,reserve=0;int ok=0;
    if(!ram(header,32) || psx_mod_read_word(header)!=script)return 0;
    next=psx_mod_read_word(header+4);metadata=psx_mod_read_word(header+24);
    if(next<script || next-script>65535 || next-script<32 || !ram(script,next-script) || !ram(metadata,4))return 0;
    n=next-script;input=malloc(n);output=malloc(SCRIPT_BYTES);model_output=malloc(MODEL_BYTES);
    if(!input || !output || !model_output)goto done;
    read_bytes(script,input,n);
    unsigned original_models=input[3];size_t original_meta=4+8u*original_models;
    if(original_models>32 || !ram(metadata,original_meta))goto done;
    read_bytes(metadata,meta,original_meta);
    if(u16(meta)!=original_meta || u16(meta+2)!=original_models)goto done;
    char name[9]={0},path[80];
    for(unsigned i=0;i<8 && input[24+i];++i){
        unsigned c=input[24+i];if(c>='a' && c<='z')c-=32;
        if(!((c>='A'&&c<='Z') || (c>='0'&&c<='9') || c=='_'))goto done;
        name[i]=(char)c;
    }
    if(!name[0])goto done;
    (void)snprintf(path,sizeof path,"FIELD/%s.BSX",name);
    uint32_t lba=0,size=0,field=(uint32_t)(psx_mod_read_byte(0x8009a05c)|((unsigned)psx_mod_read_byte(0x8009a05d)<<8));
    if(field>=800 || !psx_mod_disc_file_extent(path,&lba,&size) ||
       lba!=psx_mod_read_word(0x800da5c8+24*field) || size!=psx_mod_read_word(0x800da5cc+24*field))goto done;
    bsx=file(path,&bsx_bytes);if(!bsx || bsx_bytes<24 || u32(bsx+4)>bsx_bytes-16 || u32(bsx+u32(bsx+4)+4)!=original_models)goto done;
    for(unsigned i=0;i<ff7_party_game_extra_count();++i){
        uint8_t g=ff7_party_game_extra_guest(i);const FF7PartyProfile* profile=ff7_party_game_profile(g);
        if(!profile || !profile->field_source)continue;
        /* The renderer has32 auxiliaries, but native script model-state data
         * has many direct80074EA4 accesses. Only16 total states are established
         * by original fields. A saturated field needs a separate state-array
         * relocation before adding actors; never overwrite a native actor. */
        if(count>=16 || original_models+count>=NATIVE_STATE_CAPACITY || input[2]+count>=64)goto done;
        if(snprintf(path,sizeof path,"%s.BSX",profile->field_source)>=(int)sizeof path)goto done;
        sources[count].model=profile->field_model_index;sources[count].bsx=file(path,&sources[count].size);
        if(!sources[count].bsx)goto done;
        if(!ff7_field_asset_metadata(&sources[count],meta+original_meta+8*count)){free((void*)sources[count].bsx);sources[count].bsx=NULL;goto done;}
        guests[count++]=g;
    }
    if(!count)goto done;
    put16(meta,original_meta+8*count);put16(meta+2,original_models+count);
    size_t script_bytes=ff7_field_append_script(input,n,guests,count,output,SCRIPT_BYTES);
    size_t model_bytes=ff7_field_append_models(bsx,bsx_bytes,sources,count,model_output,MODEL_BYTES,&reserve);
    if(!script_bytes || !model_bytes)goto done;
    /* Worst case all model entries enabled. Original BCX loading also appends
     * complete decoded files; budget every referenced entry, including repeats. */
    static const char* const bcx[]={"","CLOUD","BALLET","TIFA","EARITH","RED","YUFI","KETCY","VINCENT","CID"};
    size_t working=12+36u*(original_models+count)+bsx_bytes;
    for(unsigned i=0;i<original_models+count;++i){
        uint8_t* m=meta+4+8*i;
        working+=4u*m[1]+32u*m[2]+16u*(m[7] && m[3]<3?3:m[3]);
        if(m[7]){
            if(m[7]>9)goto done;
            (void)snprintf(path,sizeof path,"FIELD/%s.BCX",bcx[m[7]]);
            size_t bytes=0;uint8_t* data=file(path,&bytes);if(!data)goto done;
            working+=bytes;free(data);
        }
    }
    if(working>WORK_BYTES)goto done;
    /* Publish only after every input and capacity is validated. The original
     * DAT header remains untouched: the entry register and two model globals
     * are the verified consumers. Current field/context owns these pointers. */
    write_bytes(s_script,output,script_bytes);write_bytes(s_metadata,meta,original_meta+8*count);
    write_bytes(s_models,model_output,reserve);
    psx_mod_write_word(s_control+4,psx_mod_read_word(0x8004a62c));
    psx_mod_write_word(s_control+8,field);psx_mod_write_word(s_control+12,(uint32_t)model_bytes);
    psx_mod_write_word(0x8007e770,s_metadata);psx_mod_write_word(0x8008357c,s_metadata+4);
    psx_mod_write_word(0x8004a62c,s_workspace);psx_mod_write_word(s_control,1);
    cpu->gpr[6]=s_script;ok=1;
done:
    for(unsigned i=0;i<count;++i)free((void*)sources[i].bsx);
    free(input);free(bsx);free(output);free(model_output);return ok;
}
static void instruction(CPUState* cpu,uint32_t pc){
    if(!cpu || !s_control || !ff7_party_game_ready())return;
    pc=(pc&0x1fffffffu)|0x80000000u;
    if(pc!=s_sites[0].pc && pc!=s_sites[1].pc)return;
    if(!guards()){psx_mod_counter_add("ff7.party_field_loader.context_reject",1);return;}
    if(pc==s_sites[0].pc){
        if(psx_mod_read_word(s_control) && psx_mod_read_word(0x8004a62c)==s_workspace)
            psx_mod_write_word(0x8004a62c,psx_mod_read_word(s_control+4));
        psx_mod_write_word(s_control,0);
        psx_mod_counter_add(prepare(cpu)?"ff7.party_field_loader.prepared":"ff7.party_field_loader.prepare_reject",1);
    }else if(psx_mod_read_word(s_control)){
        uint32_t field=psx_mod_read_byte(0x8009a05c)|((unsigned)psx_mod_read_byte(0x8009a05d)<<8);
        if(field!=psx_mod_read_word(s_control+8) || psx_mod_read_word(0x8007e770)!=s_metadata){
            psx_mod_counter_add("ff7.party_field_loader.model_reject",1);return;
        }
        cpu->gpr[17]=s_models;psx_mod_counter_add("ff7.party_field_loader.models",1);
    }
}
int ff7_party_field_loader_init(void){
    s_script=psx_mod_alloc_guest_memory(SCRIPT_BYTES+META_BYTES+32,16);
    s_workspace=psx_mod_alloc_gpu_dma_memory(WORK_BYTES,16);
    s_models=psx_mod_alloc_gpu_dma_memory(MODEL_BYTES,16);
    s_metadata=s_control=0;
    if(!s_script || !s_workspace || !s_models)return 0;
    s_metadata=s_script+SCRIPT_BYTES;s_control=s_metadata+META_BYTES;
    psx_mod_write_word(s_control,0);ff7_party_field_owned_storage(s_script,s_metadata);return 1;
}
void ff7_party_field_loader_restore(void){/* Arenas and control restore with guest state. */}
PSX_MOD_CONSTRUCTOR(register_ff7_party_field_loader){
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
        (void)psx_mod_register_instruction_plugin("ff7.party-gameplay",s_sites[i].pc,s_sites[i].words[6],instruction);
}
