#include "ff7_party_field.h"
#include "ff7_party_game.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include <stddef.h>

enum FieldAction {HEAL_ALIAS,HEAL_RANGE,HEAL_OFFSET,ENTITY_READ,ENTITY_WRITE,ENTITY_RESET};
typedef struct {uint32_t pc;enum FieldAction action;uint32_t words[13];} FieldSite;
static const FieldSite s_sites[]={
#include "ff7_party_field_sites.inc"
};
/* A distinct map is essential: native AD30 is nine bytes, and presentation10
 * is a battle model number, never a field entity. Final byte is reject scratch
 * for an invalid PC-opcode binding; the original store still executes. */
static uint32_t s_entities;
static uint32_t s_owned_script,s_owned_metadata;
static int extra(uint32_t g){return g<=255 && ff7_party_game_is_extra((uint8_t)g);}
static int ram(uint32_t p,unsigned bytes){p&=0x1fffffffu;return p>=0x10000 && p<=0x200000u-bytes;}
static void reset_entities(void){
    if(s_entities)for(unsigned i=0;i<32;++i)psx_mod_write_byte(s_entities+i,255);
}
static uint32_t cell(uint8_t guest){
    return s_entities && guest>=11 && guest<=26 && extra(guest)?s_entities+guest-11:0;
}
static int valid_entity(uint8_t guest,uint8_t entity){
    if(entity==255)return 1;
    uint32_t script=psx_mod_read_word(0x8009c6dcu),models=psx_mod_read_word(0x8007e770u);
    if((!ram(script,4) && script!=s_owned_script) || (!ram(models,4) && models!=s_owned_metadata) || entity>=64 || entity>=psx_mod_read_byte(script+2))return 0;
    unsigned model=psx_mod_read_byte(0x8007eb98u+entity);
    unsigned count=psx_mod_read_byte(models+2)|((unsigned)psx_mod_read_byte(models+3)<<8);
    if(model==255 || model>=count)return 0;
    for(unsigned i=0;i<9;++i)if(psx_mod_read_byte(0x8009ad30u+i)==entity)return 0;
    for(unsigned i=0;i<ff7_party_game_extra_count();++i){
        uint8_t other=ff7_party_game_extra_guest(i);
        uint32_t address=cell(other);
        if(other!=guest && address && psx_mod_read_byte(address)==entity)return 0;
    }
    return 1;
}
uint8_t ff7_party_field_entity(uint8_t guest){
    uint32_t address=cell(guest);return address?psx_mod_read_byte(address):255;
}
int ff7_party_field_bind(uint16_t identity,uint8_t entity){
    uint8_t guest=ff7_party_game_guest_id(identity);uint32_t address=cell(guest);
    if(!address || !valid_entity(guest,entity))return 0;
    psx_mod_write_byte(address,entity);return 1;
}
static void field_instruction(CPUState* cpu,uint32_t pc){
    if(!cpu || !ff7_party_game_ready())return;
    pc=(pc&0x1fffffffu)|0x80000000u;
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i){
        const FieldSite* s=&s_sites[i];if(s->pc!=pc)continue;
        for(unsigned j=0;j<13;++j)if(psx_mod_read_word(pc-24+4*j)!=s->words[j]){
            psx_mod_counter_add("ff7.party_field.context_reject",1);return;
        }
        uint32_t* r=cpu->gpr;
        switch(s->action){
        case HEAL_ALIAS:{uint32_t n=r[2]-0x800491d0u;
            if(!(n&3u) && extra(n/4u))r[2]=ff7_party_game_alias_word((uint8_t)(n/4u));
            break;}
        case HEAL_RANGE:if(extra(r[3]))r[2]=1;break;
        case HEAL_OFFSET:
            if(!(r[2]%33u) && extra(r[2]/33u))r[2]=ff7_party_game_record_offset((uint8_t)(r[2]/33u))>>2;
            break;
        case ENTITY_READ:case ENTITY_WRITE:{
            uint32_t guest=r[1]-0x8009ad30u;
            if(s_entities && extra(guest)){
                uint32_t address=cell((uint8_t)guest);
                if(s->action==ENTITY_WRITE){
                    unsigned source=(s->words[6]>>16)&31u;
                    if(!valid_entity((uint8_t)guest,(uint8_t)r[source])){
                        address=s_entities+31;psx_mod_counter_add("ff7.party_field.binding_reject",1);
                    }
                }
                if(address)r[1]=address;
            }
            break;}
        case ENTITY_RESET:reset_entities();break;
        }
        psx_mod_counter_add("ff7.party_field.hook",1);return;
    }
}
void ff7_party_field_owned_storage(uint32_t script,uint32_t metadata){s_owned_script=script;s_owned_metadata=metadata;}
int ff7_party_field_init(void){s_owned_script=s_owned_metadata=0;s_entities=psx_mod_alloc_guest_memory(32,4);reset_entities();return s_entities!=0;}
void ff7_party_field_restore(void){/* Guest map rewinds; never rebind native entities. */}
PSX_MOD_CONSTRUCTOR(register_ff7_party_field){
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
        (void)psx_mod_register_instruction_plugin("ff7.party-gameplay",s_sites[i].pc,
                                                s_sites[i].words[6],field_instruction);
}
