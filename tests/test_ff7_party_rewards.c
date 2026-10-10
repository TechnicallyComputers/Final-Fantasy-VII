#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/ff7_party_rewards.c"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x);exit(1);}}while(0)
static uint8_t s_ram[0x200000],s_expansion[0x20000];
static unsigned s_count=16,s_rejected,s_registered,s_ready=1;
static FF7PartyProfile s_profile={0x100,10,7,10,0,0,0,"ENEMY6/SEFIROS.LZS","MENU/PCEFI.TIM",1,NULL,0,0};
static uint8_t* ptr(uint32_t p){p&=0x1fffffffu;if(p<sizeof s_ram)return s_ram+p;
    CHECK(p>=0x1f000000u && p-0x1f000000u<sizeof s_expansion);return s_expansion+p-0x1f000000u;}
uint8_t psx_mod_read_byte(uint32_t p){return *ptr(p);}
uint32_t psx_mod_read_word(uint32_t p){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=(uint32_t)*ptr(p+i)<<(i*8);return v;}
void psx_mod_write_word(uint32_t p,uint32_t v){for(unsigned i=0;i<4;++i)*ptr(p+i)=(uint8_t)(v>>(8*i));}
void psx_mod_counter_add(const char* n,uint32_t v){CHECK(v==1);if(strstr(n,"reject"))++s_rejected;}
int psx_mod_register_instruction_plugin(const char* n,uint32_t p,uint32_t w,void(*f)(CPUState*,uint32_t)){
    CHECK(!strcmp(n,"ff7.party-gameplay") && p && w && f);++s_registered;return 1;}
int ff7_party_game_ready(void){return (int)s_ready;}
unsigned ff7_party_game_extra_count(void){return s_count;}
uint8_t ff7_party_game_extra_guest(unsigned i){return i<s_count?(uint8_t)(11+i):255;}
int ff7_party_game_is_extra(uint8_t g){return g>=11 && g<11+s_count;}
uint32_t ff7_party_game_record(uint8_t g){return ff7_party_game_is_extra(g)?0x9f010000u+132u*(g-11):0;}
uint32_t ff7_party_game_record_offset(uint8_t g){return ff7_party_game_record(g)-0x8009c738u;}
const FF7PartyProfile* ff7_party_game_profile(uint8_t g){return ff7_party_game_is_extra(g)?&s_profile:NULL;}
uint8_t* ff7_test_rewards_ram(void){return s_ram;}
uint8_t* ff7_test_rewards_expansion(void){return s_expansion;}
void ff7_test_rewards_reset(unsigned count,unsigned growth){
    CHECK(count<=16 && growth<9);memset(s_ram,0,sizeof s_ram);memset(s_expansion,0,sizeof s_expansion);
    s_count=count;s_profile.growth_identity=(uint8_t)growth;s_ready=1;s_rejected=0;
    for(unsigned i=0;i<count;++i)*ptr(ff7_party_game_record((uint8_t)(11+i)))=(uint8_t)(11+i);
}
void ff7_test_rewards_hook(uint32_t pc,uint32_t* regs){CPUState cpu;memset(&cpu,0,sizeof cpu);
    memcpy(cpu.gpr,regs,sizeof cpu.gpr);rewards_instruction(&cpu,pc);memcpy(regs,cpu.gpr,sizeof cpu.gpr);}
static void seed(const RewardSite* s){for(unsigned i=0;i<13;++i)psx_mod_write_word(s->pc-24+4*i,s->words[i]);}
int main(void){
    register_ff7_party_rewards();CHECK(s_registered==7);ff7_test_rewards_reset(16,7);
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i){const RewardSite* s=&s_sites[i];seed(s);
        for(unsigned g=0;g<27;++g){uint32_t r[32]={0};
            switch(s->action){
            case ACTIVE_RECORD:r[3]=g;ff7_test_rewards_hook(s->pc,r);
                CHECK(r[20]==(g<11?0:ff7_party_game_record_offset((uint8_t)g)));CHECK(r[16]==(g<11?0:8));break;
            case WRITEBACK_RECORD:r[18]=g;ff7_test_rewards_hook(s->pc,r);
                CHECK(r[17]==(g<11?0:ff7_party_game_record((uint8_t)g)));break;
            case RESTORE_RECORD:r[7]=g;ff7_test_rewards_hook(s->pc,r);
                CHECK(r[5]==(g<11?0:ff7_party_game_record((uint8_t)g)));CHECK(r[1]==(g<11?0:r[5]+0x38c8u));break;
            case GROWTH_ROW:r[2]=g;r[3]=7*g;ff7_test_rewards_hook(s->pc,r);CHECK(r[3]==(g<11?7*g:49));break;
            case RESERVE_ID:r[3]=g;ff7_test_rewards_hook(s->pc,r);CHECK(r[2]==(g>=11));break;
            case RESERVE_LOOP:r[20]=g;ff7_test_rewards_hook(s->pc,r);CHECK(r[2]==(g<25));break;
            case RESERVE_RECORD:if(g>=11){r[20]=g-2;ff7_test_rewards_hook(s->pc,r);
                CHECK(r[19]==ff7_party_game_record_offset((uint8_t)g));CHECK(r[21]==1u<<g);
                *ptr(0x8009cbdc)=(uint8_t)g;ff7_test_rewards_hook(s->pc,r);CHECK(r[21]==0);*ptr(0x8009cbdc)=0;}break;
            }
        }
        uint32_t r[32]={0};psx_mod_write_word(s->pc-4,0xdeadbeefu);ff7_test_rewards_hook(s->pc,r);CHECK(s_rejected==i+1);
    }
    puts("reward guards,16 proxies,native passthrough,curve selection,reserve exclusion passed");return 0;
}
