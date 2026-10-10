#include "ff7_party_field_loader.h"
#include "ff7_party_field_assets.h"
#include "ff7_party_field.h"
#include "ff7_party_field_state.h"
#include "ff7_party_game.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

enum {SCRIPT_BYTES=65536,META_BYTES=260,WORK_BYTES=0x100000,MODEL_BYTES=0x400000,STATE_CAPACITY=32};
enum LoaderAction {PREPARE,MODELS,RELOAD};
typedef struct {uint32_t pc;enum LoaderAction action;uint32_t words[13];} LoaderSite;
static const LoaderSite s_sites[]={
#include "ff7_party_field_loader_sites.inc"
};
/* Arena addresses are immutable for one activation; active field and previous
 * native workspace live in rewindable guest memory. No external file writes. */
static uint32_t s_script,s_metadata,s_control,s_workspace,s_models;
static const char* const s_field_paths[]={
#include "ff7_party_field_names.inc"
};
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
    char path[80];
    uint32_t lba=0,size=0,field=(uint32_t)(psx_mod_read_byte(0x8009a05c)|((unsigned)psx_mod_read_byte(0x8009a05d)<<8));
    /* DAT labels are not ISO names (ASTAGE_A stores "astage_", SEMKIN_3
     * stores "semkin_"). Names are generated from each original ISO and
     * checked against the original FIELD table; verify effective extent again. */
    if(field>=sizeof s_field_paths/sizeof s_field_paths[0])goto done;
    (void)snprintf(path,sizeof path,"%s",s_field_paths[field]);
    if(!psx_mod_disc_file_extent(path,&lba,&size) ||
       lba!=psx_mod_read_word(0x800da5c8+24*field) || size!=psx_mod_read_word(0x800da5cc+24*field))goto done;
    bsx=file(path,&bsx_bytes);if(!bsx || bsx_bytes<24 || u32(bsx+4)>bsx_bytes-16 || u32(bsx+u32(bsx+4)+4)!=original_models)goto done;
    for(unsigned i=0;i<ff7_party_game_extra_count();++i){
        uint8_t g=ff7_party_game_extra_guest(i);const FF7PartyProfile* profile=ff7_party_game_profile(g);
        if(!profile || !profile->field_source)continue;
        if(count>=16 || original_models+count>=STATE_CAPACITY || input[2]+count>=64)goto done;
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
    uint32_t states=ff7_party_field_state_begin(cpu->gpr[5],input[2],original_models,count);
    if(!states)goto done;
    /* Publish only after every input and capacity is validated. The original
     * DAT header remains untouched: the entry register and two model globals
     * are the verified consumers. Current field/context owns these pointers. */
    write_bytes(s_script,output,script_bytes);write_bytes(s_metadata,meta,original_meta+8*count);
    write_bytes(s_models,model_output,reserve);
    psx_mod_write_word(s_control+4,psx_mod_read_word(0x8004a62c));
    psx_mod_write_word(s_control+8,field);psx_mod_write_word(s_control+12,(uint32_t)model_bytes);
    psx_mod_write_word(s_control+16,metadata);psx_mod_write_word(s_control+20,count);
    psx_mod_write_word(s_control+24,original_models);psx_mod_write_word(s_control+28,(uint32_t)reserve);
    psx_mod_write_word(0x8007e770,s_metadata);psx_mod_write_word(0x8008357c,s_metadata+4);
    psx_mod_write_word(0x8004a62c,s_workspace);psx_mod_write_word(s_control,3);
    cpu->gpr[5]=states;cpu->gpr[6]=s_script;ok=1;
done:
    for(unsigned i=0;i<count;++i)free((void*)sources[i].bsx);
    free(input);free(bsx);free(output);free(model_output);return ok;
}
static int reload(void){
    /* The original DAT reload restores E770/8357C without restarting scripts.
     * AA930 must see the expanded metadata before ADAA4 allocates descriptors.
     * AC484 is too late. AC35C also relocates/overwrites its BSX in place, so
     * never reuse that mutated buffer across model loads. Rebuild privately,
     * then publish; script cursors, NPC state and party bindings stay intact. */
    unsigned field=psx_mod_read_byte(0x8009a05c)|((unsigned)psx_mod_read_byte(0x8009a05d)<<8);
    unsigned count=psx_mod_read_word(s_control+20),old=psx_mod_read_word(s_control+24);
    uint32_t metadata=psx_mod_read_word(0x8007e770),lba=0,size=0;
    if(field!=psx_mod_read_word(s_control+8) || field>=sizeof s_field_paths/sizeof s_field_paths[0] ||
       psx_mod_read_word(0x8009c6dc)!=s_script || !count || count>16 || old+count>STATE_CAPACITY ||
       (metadata!=s_metadata && metadata!=psx_mod_read_word(s_control+16)) ||
       psx_mod_read_word(0x8008357c)!=metadata+4 ||
       !psx_mod_disc_file_extent(s_field_paths[field],&lba,&size) ||
       lba!=psx_mod_read_word(0x800da5c8+24*field) || size!=psx_mod_read_word(0x800da5cc+24*field))return 0;
    uint8_t meta[META_BYTES];read_bytes(s_metadata,meta,4+8*(old+count));
    if(u16(meta)!=4+8*(old+count) || u16(meta+2)!=old+count ||
       psx_mod_read_byte(s_script+3)!=old+count)return 0;
    if(metadata!=s_metadata){
        uint8_t native[META_BYTES];
        if(!ram(metadata,4+8*old))return 0;
        read_bytes(metadata,native,4+8*old);
        if(u16(native)!=4+8*old || u16(native+2)!=old)return 0;
        memcpy(meta+4,native+4,8*old);
    }
    FF7FieldAssetSource sources[16]={{0}};size_t n=0,reserve=0;unsigned used=0;int ok=0;
    uint8_t* bsx=file(s_field_paths[field],&n);uint8_t* output=malloc(MODEL_BYTES);
    if(!bsx || !output || n<24 || u32(bsx+4)>n-16 || u32(bsx+u32(bsx+4)+4)!=old)goto done;
    for(unsigned i=0;i<ff7_party_game_extra_count();++i){
        const FF7PartyProfile* p=ff7_party_game_profile(ff7_party_game_extra_guest(i));
        if(!p || !p->field_source)continue;
        char path[80];uint8_t expected[8];
        if(used>=count || snprintf(path,sizeof path,"%s.BSX",p->field_source)>=(int)sizeof path)goto done;
        unsigned at=used++;sources[at].model=p->field_model_index;sources[at].bsx=file(path,&sources[at].size);
        if(!sources[at].bsx || !ff7_field_asset_metadata(&sources[at],expected))goto done;
        /* Compact descriptor index4 and visibility5 are runtime values. */
        for(unsigned j=0;j<8;++j)if(j!=4 && j!=5 && expected[j]!=meta[4+8*(old+at)+j])goto done;
    }
    if(used!=count)goto done;
    size_t bytes=ff7_field_append_models(bsx,n,sources,count,output,MODEL_BYTES,&reserve);
    if(!bytes || bytes!=psx_mod_read_word(s_control+12) || reserve!=psx_mod_read_word(s_control+28))goto done;
    write_bytes(s_models,output,reserve);
    /* ADD70 byte6 is a per-load BCX cache marker, invalid after allocation. */
    for(unsigned i=0;i<old+count;++i)meta[4+8*i+6]=0;
    write_bytes(s_metadata,meta,4+8*(old+count));
    psx_mod_write_word(0x8007e770,s_metadata);psx_mod_write_word(0x8008357c,s_metadata+4);
    psx_mod_write_word(0x8004a62c,s_workspace);ok=1;
done:
    for(unsigned i=0;i<used;++i)free((void*)sources[i].bsx);
    free(bsx);free(output);return ok;
}
static void instruction(CPUState* cpu,uint32_t pc){
    if(!cpu || !s_control || !ff7_party_game_ready())return;
    pc=(pc&0x1fffffffu)|0x80000000u;
    if(pc!=s_sites[0].pc && pc!=s_sites[1].pc && pc!=s_sites[2].pc)return;
    if(pc==s_sites[0].pc){
        /* Retire the preceding field even if this entry's context rejects.
         * Otherwise its active state hooks could redirect an unprepared field. */
        ff7_party_field_state_end();
        if(psx_mod_read_word(s_control) && psx_mod_read_word(0x8004a62c)==s_workspace)
            psx_mod_write_word(0x8004a62c,psx_mod_read_word(s_control+4));
        psx_mod_write_word(s_control,0);
    }
    if(!guards()){psx_mod_counter_add("ff7.party_field_loader.context_reject",1);return;}
    if(pc==s_sites[0].pc){
        psx_mod_counter_add(prepare(cpu)?"ff7.party_field_loader.prepared":"ff7.party_field_loader.prepare_reject",1);
    }else if(pc==s_sites[2].pc){
        if(psx_mod_read_word(s_control)){
            /* One-use raw-model readiness is rewindable too. A rejected load
             * must never feed an already relocated buffer to AC35C. */
            psx_mod_write_word(s_control,1);
            int ok=reload();if(ok)psx_mod_write_word(s_control,3);
            psx_mod_counter_add(ok?"ff7.party_field_loader.reloaded":"ff7.party_field_loader.reload_reject",1);
        }
    }else if(psx_mod_read_word(s_control)){
        uint32_t field=psx_mod_read_byte(0x8009a05c)|((unsigned)psx_mod_read_byte(0x8009a05d)<<8);
        if(psx_mod_read_word(s_control)!=3 || field!=psx_mod_read_word(s_control+8) || psx_mod_read_word(0x8007e770)!=s_metadata){
            psx_mod_counter_add("ff7.party_field_loader.model_reject",1);return;
        }
        psx_mod_write_word(s_control,1);
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
    psx_mod_write_word(s_control,0);ff7_party_field_owned_storage(s_script,s_metadata);
    return ff7_party_field_state_init();
}
void ff7_party_field_loader_restore(void){ff7_party_field_state_restore();}
PSX_MOD_CONSTRUCTOR(register_ff7_party_field_loader){
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
        (void)psx_mod_register_instruction_plugin("ff7.party-gameplay",s_sites[i].pc,s_sites[i].words[6],instruction);
}
