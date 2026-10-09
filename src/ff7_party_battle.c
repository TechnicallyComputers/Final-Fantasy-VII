#include "ff7_party_battle.h"
#include "ff7_party_game.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include <stddef.h>
#include <stdint.h>

enum Action {INITIAL_RECORD,REFRESH_RECORD,AI_ALIAS,AI_HEADER,MODEL,EXTENT,ALIAS,OFFSET,MOTIONS,ARENA_RECORD};
typedef struct {uint32_t pc;enum Action action;unsigned reg;uint32_t words[13];} BattleSite;
static const BattleSite s_sites[]={
#include "ff7_party_battle_sites.inc"
};
/* 27 empty AI offsets cover original identities plus all16 allocated proxies.
 * This is personal character AI only; shared enemy/formation AI is untouched.
 * Extent records are scratch, recomputed against the mounted disc on each load.
 */
enum {STORAGE_SIZE=192,EMPTY_AI=0,EXTENTS=64};
static uint32_t s_storage;
static int extra(uint32_t g){return g<=255 && ff7_party_game_is_extra((uint8_t)g);}
static uint16_t half(uint32_t p){return (uint16_t)(psx_mod_read_byte(p)|((unsigned)psx_mod_read_byte(p+1)<<8));}
static int matches(const BattleSite* s){
    for(unsigned i=0;i<13;++i)if(psx_mod_read_word(s->pc-24+4*i)!=s->words[i])return 0;
    return 1;
}
static uint32_t guest_crc32(uint32_t start,uint32_t length){
    uint32_t crc=~0u;
    for(uint32_t i=0;i<length;++i){
        crc^=psx_mod_read_byte(start+i);
        for(unsigned b=0;b<8;++b)crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u);
    }
    return ~crc;
}
static void prepare_motions(unsigned slot){
    if(slot>=3)return;
    uint8_t guest=psx_mod_read_byte(0x801636b8u+slot*16u);
    const FF7PartyProfile* profile=ff7_party_game_profile(guest);
    if(!extra(guest) || !profile || profile->motion_policy!=FF7_PARTY_MOTION_SEPHIROTH)return;
    uint32_t model=0x80103200u+slot*0xf000u;
    /* Original copy completed. Guard the whole51,420-byte original body.
     * Skeleton, motion bitstreams, textures and allocation size stay intact.
     * Original interpreter consumes relative motion pointers directly.
     * Cover/damage reuse own evade5; items reuse own casting12, with paired
     * weapon pointers. Death/defend/limits still require separate work. */
    if(guest_crc32(model,51420u)!=0xb30ba230u){
        psx_mod_counter_add("ff7.party_battle.motion_reject",1);return;
    }
    static const struct{uint16_t offset;uint32_t replacement;} pointers[]={
        {44,42140},{48,44468},{52,44468},{252,50636},{256,50868},{260,50868}
    };
    for(unsigned i=0;i<sizeof pointers/sizeof pointers[0];++i)
        psx_mod_write_word(model+pointers[i].offset,pointers[i].replacement);
    static const uint16_t damage[]={35428,35432,35433,35440};
    for(unsigned i=0;i<sizeof damage/sizeof damage[0];++i)psx_mod_write_byte(model+damage[i],5);
    psx_mod_counter_add("ff7.party_battle.motion_prepare",1);
}
static uint32_t extent(unsigned pair){
    unsigned slot=half(0x800fa9c6u+pair*4u);
    if(slot>=3)return 0;
    uint8_t guest=psx_mod_read_byte(0x801636b8u+slot*16u);
    if(!extra(guest))return 0;
    const FF7PartyProfile* p=ff7_party_game_profile(guest);
    uint32_t lba,size;
    if(!p || !p->battle_model || !psx_mod_disc_file_extent(p->battle_model,&lba,&size)
       || size<4 || size>0x50000u){
        psx_mod_counter_add("ff7.party_battle.asset_reject",1);return 0;
    }
    uint32_t out=s_storage+EXTENTS+pair*8u;
    psx_mod_write_word(out,lba);psx_mod_write_word(out+4,(size+2047u)&~2047u);
    return out;
}
static void apply_site(CPUState* cpu,const BattleSite* s){
    uint32_t* r=cpu->gpr;
    switch(s->action){
    case INITIAL_RECORD:
        if(extra(r[30]))r[3]=ff7_party_game_record((uint8_t)r[30])-r[9];
        break;
    case REFRESH_RECORD:
        if(extra(r[7]))r[17]=ff7_party_game_record((uint8_t)r[7]);
        break;
    case ARENA_RECORD:
        if(extra(r[7]))r[3]=ff7_party_game_record_offset((uint8_t)r[7]);
        break;
    case AI_ALIAS:
        if(extra(r[19]))r[1]=s_storage+EMPTY_AI-0x7a58u;
        break;
    case AI_HEADER:
        if(extra(r[19]))r[4]=s_storage+EMPTY_AI;
        break;
    case MODEL:
        /* v0 may already be native Barret/Vincent variant11..15. Resolve the
         * actor identity through s2, not the overlapping model-number domain. */
        if(r[18]>=0x801636b8u && r[18]<=0x801636d8u && ((r[18]-0x801636b8u)%16u)==0){
            uint8_t g=psx_mod_read_byte(r[18]);
            if(extra(g))r[2]=ff7_party_game_presentation(g);
        }
        break;
    case EXTENT:{
        uint32_t p=extent(s->reg);
        if(p){r[3]=p;r[s->reg?2:4]=p;}
        break;}
    case ALIAS:{
        uint32_t p=r[s->reg],delta=p-0x800491d0u;
        if(delta<27u*4u && !(delta&3u) && extra(delta/4u))
            r[s->reg]=ff7_party_game_alias_word((uint8_t)(delta/4u));
        break;}
    case OFFSET:{
        uint32_t v=r[s->reg];
        if(v<=33u*26u && !(v%33u) && extra(v/33u))
            r[s->reg]=ff7_party_game_record_offset((uint8_t)(v/33u))>>2;
        break;}
    case MOTIONS:prepare_motions(r[16]);break;
    }
}
static void battle_instruction(CPUState* cpu,uint32_t pc){
    if(!cpu || !s_storage)return;
    pc=(pc&0x1fffffffu)|0x80000000u;
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i){
        if(s_sites[i].pc==pc && matches(&s_sites[i])){
            apply_site(cpu,&s_sites[i]);psx_mod_counter_add("ff7.party_battle.hook",1);return;
        }
    }
    psx_mod_counter_add("ff7.party_battle.context_reject",1);
}
int ff7_party_battle_init(void){
    s_storage=psx_mod_alloc_guest_memory(STORAGE_SIZE,4);
    if(!s_storage)return 0;
    for(unsigned i=0;i<64;++i)psx_mod_write_byte(s_storage+i,255);
    return 1;
}
void ff7_party_battle_restore(void){/* All mutable adapter data rewinds in guest memory. */}
PSX_MOD_CONSTRUCTOR(register_ff7_party_battle){
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
        (void)psx_mod_register_instruction_plugin("ff7.party-gameplay",s_sites[i].pc,
                                                 s_sites[i].words[6],battle_instruction);
}
