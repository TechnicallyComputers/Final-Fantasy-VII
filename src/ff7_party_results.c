#include "ff7_party_game.h"
#include "ff7_party_menu.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include <stddef.h>

enum ResultAction {RECORD_SCAN,RESULT_ALIAS,PORTRAIT_COPY,PORTRAIT_EXTENT,SAVE_PORTRAIT};
typedef struct {uint32_t pc;enum ResultAction action;unsigned reg;uint32_t words[13];} ResultSite;
static const ResultSite s_sites[]={
#include "ff7_party_results_sites.inc"
};
static int extra(uint32_t g){return g<=255 && ff7_party_game_is_extra((uint8_t)g);}
static void result_instruction(CPUState* cpu,uint32_t pc){
    if(!cpu || !ff7_party_game_ready())return;
    pc=(pc&0x1fffffffu)|0x80000000u;
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i){
        const ResultSite* s=&s_sites[i];if(s->pc!=pc)continue;
        for(unsigned j=0;j<13;++j)if(psx_mod_read_word(pc-24+j*4)!=s->words[j]){
            psx_mod_counter_add("ff7.party_results.context_reject",1);return;
        }
        uint32_t* r=cpu->gpr;
        switch(s->action){
        case RECORD_SCAN:
            /* The stock EXP animation searches nine records by ID. Preserve
             * its curve/tween/party-slot state and redirect only this search
             * iteration plus the subsequent record-relative reads. */
            if(extra(r[6])){
                r[9]=ff7_party_game_record_offset((uint8_t)r[6]);
                r[1]=0x800a0000u+r[9];r[5]=8;
            }
            break;
        case RESULT_ALIAS:{
            uint32_t off=r[s->reg]-0x800491d0u;
            if(!(off&3u) && extra(off/4u))
                r[s->reg]=ff7_party_game_alias_word((uint8_t)(off/4u));
            break;}
        case PORTRAIT_COPY:
        case SAVE_PORTRAIT:
            if(extra(r[s->reg])){
                int cell=ff7_party_menu_prepare_portrait((uint8_t)r[s->reg]);
                if(cell>=0)r[s->reg]=(uint32_t)cell;
            }
            break;
        case PORTRAIT_EXTENT:
            if(extra(r[17])){
                uint32_t extent=ff7_party_menu_portrait_extent((uint8_t)r[17],r[16]);
                /* A missing profile asset cannot index past the native table.
                 * Use the first valid native portrait as a visible fallback. */
                r[2]=extent?extent:0x80048fe8u;r[3]=r[2]+4;
                psx_mod_counter_add(extent?"ff7.party_results.portrait_asset":
                                           "ff7.party_results.portrait_fallback",1);
            }
            break;
        }
        psx_mod_counter_add("ff7.party_results.hook",1);return;
    }
}
PSX_MOD_CONSTRUCTOR(register_ff7_party_results){
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
        (void)psx_mod_register_instruction_plugin("ff7.party-gameplay",s_sites[i].pc,
                                                s_sites[i].words[6],result_instruction);
}
