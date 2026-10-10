#include "ff7_party_field_state.h"
#include "ff7_party_game.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include <stddef.h>
enum {STATE_STRIDE=132,STATE_CAPACITY=32,STATE_BYTES=STATE_STRIDE*STATE_CAPACITY};
enum StateAction {BASE,ENTITY_LOAD,ENTITY_STORE};
typedef struct {uint32_t pc;unsigned reg;enum StateAction action;uint32_t words[13];} StateSite;
static const StateSite s_sites[]={
#include "ff7_party_field_state_sites.inc"
};
static uint32_t s_arena,s_control;
static int guard(const StateSite* site){
    for(unsigned j=0;j<13;++j)if(psx_mod_read_word(site->pc-24+4*j)!=site->words[j])return 0;
    return 1;
}
void ff7_party_field_state_end(void){if(s_control){
    psx_mod_write_word(s_control+8,psx_mod_read_word(s_control));psx_mod_write_word(s_control,0);
}}
uint32_t ff7_party_field_state_begin(uint32_t native_base,unsigned entities,unsigned native_models,unsigned extras){
    if(!s_control || psx_mod_read_word(s_control) || native_base!=0x80074ea4u || native_models>16 || !extras || extras>16 || entities>64-extras)return 0;
    unsigned models=native_models+extras;
    if(models>STATE_CAPACITY)return 0;
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)if(!guard(&s_sites[i])){
        psx_mod_counter_add("ff7.party_field_state.context_reject",1);return 0;
    }
    /* On first enhanced field (or following a rejected/native field), preserve
     * incoming native initialization bytes. Across enhanced fields, retain the
     * same arena's prior bytes just as the original persistent array does;
     * BA7C4 performs normal per-field initialization. Native array is untouched. */
    if(!psx_mod_read_word(s_control+8))for(unsigned i=0;i<STATE_BYTES;++i)
        psx_mod_write_byte(s_arena+i,i<16*STATE_STRIDE?psx_mod_read_byte(native_base+i):0);
    psx_mod_write_word(s_control+4,models);psx_mod_write_word(s_control+12,entities);
    psx_mod_write_word(s_control+16,native_models);psx_mod_write_word(s_control+20,extras);
    psx_mod_write_word(s_control,1);return s_arena;
}
static void instruction(CPUState* cpu,uint32_t pc){
    if(!cpu || !s_control || !ff7_party_game_ready() || !psx_mod_read_word(s_control))return;
    pc=(pc&0x1fffffffu)|0x80000000u;
    size_t lo=0,hi=sizeof s_sites/sizeof s_sites[0];
    while(lo<hi){size_t mid=lo+(hi-lo)/2;if(s_sites[mid].pc<pc)lo=mid+1;else hi=mid;}
    if(lo==sizeof s_sites/sizeof s_sites[0] || s_sites[lo].pc!=pc)return;
    const StateSite* site=&s_sites[lo];
    if(!guard(site)){psx_mod_counter_add("ff7.party_field_state.context_reject",1);return;}
    if(site->action!=BASE){
        unsigned entity=psx_mod_read_byte(0x800722c4),first=psx_mod_read_word(s_control+12),n=psx_mod_read_word(s_control+20);
        if(entity<first || entity-first>=n)return;
        if(cpu->gpr[site->reg]!=0x800a0000u){psx_mod_counter_add("ff7.party_field_state.base_reject",1);return;}
        uint32_t scratch=s_control+24;
        if(site->action==ENTITY_LOAD)psx_mod_write_byte(scratch,(uint8_t)(psx_mod_read_word(s_control+16)+entity-first));
        cpu->gpr[site->reg]=scratch-(uint32_t)(int32_t)(int16_t)0xc6c4;
        psx_mod_counter_add("ff7.party_field_state.extra_char",1);return;
    }
    if(cpu->gpr[site->reg]!=0x80070000u){psx_mod_counter_add("ff7.party_field_state.base_reject",1);return;}
    cpu->gpr[site->reg]=s_arena-0x4ea4u;
    psx_mod_counter_add("ff7.party_field_state.hook",1);
}
int ff7_party_field_state_init(void){
    s_arena=psx_mod_alloc_guest_memory(STATE_BYTES+32,16);s_control=s_arena?s_arena+STATE_BYTES:0;
    if(s_control){psx_mod_write_word(s_control,0);psx_mod_write_word(s_control+8,0);}
    return s_arena!=0;
}
void ff7_party_field_state_restore(void){/* State records and active flag are guest-owned. */}
PSX_MOD_CONSTRUCTOR(register_ff7_party_field_state){
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
        (void)psx_mod_register_instruction_plugin("ff7.party-gameplay",s_sites[i].pc,s_sites[i].words[6],instruction);
}
