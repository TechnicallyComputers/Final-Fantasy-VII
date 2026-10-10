#include "ff7_party_rewards.h"
#include "ff7_party_game.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include <stddef.h>

enum Action {ACTIVE_RECORD,WRITEBACK_RECORD,RESTORE_RECORD,GROWTH_ROW,
             RESERVE_RECORD,RESERVE_ID,RESERVE_LOOP};
typedef struct {uint32_t pc;enum Action action;uint32_t words[13];} RewardSite;
static const RewardSite s_sites[]={
#include "ff7_party_rewards_sites.inc"
};
static int extra(uint32_t guest){return guest<=255 && ff7_party_game_is_extra((uint8_t)guest);}
static unsigned count(void){unsigned n=ff7_party_game_extra_count();return n<=16?n:0;}
static int active(uint8_t guest){
    for(unsigned i=0;i<3;++i)if(psx_mod_read_byte(0x8009cbdcu+i)==guest)return 1;
    return 0;
}
static void apply_site(CPUState* cpu,const RewardSite* site){
    uint32_t* r=cpu->gpr;
    switch(site->action){
    case ACTIVE_RECORD:
        /* Original search keeps scanning after a match. Starting at its final
         * iteration gives exactly one award without touching native records. */
        if(extra(r[3])){r[20]=ff7_party_game_record_offset((uint8_t)r[3]);r[16]=8;}
        break;
    case WRITEBACK_RECORD:
        if(extra(r[18]))r[17]=ff7_party_game_record((uint8_t)r[18]);
        break;
    case RESTORE_RECORD:
        if(extra(r[7])){r[5]=ff7_party_game_record((uint8_t)r[7]);r[1]=r[5]+0x38c8u;}
        break;
    case GROWTH_ROW:{
        const FF7PartyProfile* p=extra(r[2])?ff7_party_game_profile((uint8_t)r[2]):NULL;
        /* Changes only the immutable curve selector. The original temporary
         * record and persistent record keep their independent identity. */
        if(p && p->growth_identity<9)r[3]=7u*p->growth_identity;
        break;}
    case RESERVE_RECORD:
        if(r[20]>=9 && r[20]<9+count()){
            uint8_t guest=ff7_party_game_extra_guest(r[20]-9);
            if(extra(guest)){
                r[19]=ff7_party_game_record_offset(guest);
                uint32_t bit=1u<<guest;
                r[21]=active(guest)?r[21]&~bit:r[21]|bit;
            }
        }
        break;
    case RESERVE_ID:
        if(extra(r[3]))r[2]=1; /* Preserve original per-character mask test. */
        break;
    case RESERVE_LOOP:r[2]=r[20]<9+count();break;
    }
}
static void rewards_instruction(CPUState* cpu,uint32_t pc){
    if(!cpu || !ff7_party_game_ready())return;
    pc=(pc&0x1fffffffu)|0x80000000u;
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i){
        const RewardSite* s=&s_sites[i];
        if(s->pc!=pc)continue;
        for(unsigned j=0;j<13;++j)if(psx_mod_read_word(pc-24+4*j)!=s->words[j]){
            psx_mod_counter_add("ff7.party_rewards.context_reject",1);return;
        }
        apply_site(cpu,s);psx_mod_counter_add("ff7.party_rewards.hook",1);return;
    }
}
PSX_MOD_CONSTRUCTOR(register_ff7_party_rewards){
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
        (void)psx_mod_register_instruction_plugin("ff7.party-gameplay",s_sites[i].pc,
                                                s_sites[i].words[6],rewards_instruction);
}
