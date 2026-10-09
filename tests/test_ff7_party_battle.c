#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/ff7_party_battle.c"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x);exit(1);}}while(0)
static uint8_t s_ram[0x200000],s_expansion[0x20000];
static unsigned s_count=1,s_registered,s_rejected,s_alloc_fail,s_asset_fail;
static uint32_t s_lba=30363,s_bytes=43264;
static FF7PartyProfile s_profile={0x100,10,7,10,0,0,0,"ENEMY6/SEFIROS.LZS","MENU/PCEFI.TIM",FF7_PARTY_MOTION_SEPHIROTH,NULL,0};
static uint8_t* ptr(uint32_t p){p&=0x1fffffffu;if(p<sizeof s_ram)return s_ram+p;
    CHECK(p>=0x1f000000u && p-0x1f000000u<sizeof s_expansion);return s_expansion+p-0x1f000000u;}
uint8_t psx_mod_read_byte(uint32_t p){return *ptr(p);}
uint32_t psx_mod_read_word(uint32_t p){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=(uint32_t)*ptr(p+i)<<(i*8);return v;}
void psx_mod_write_byte(uint32_t p,uint8_t v){*ptr(p)=v;}
void psx_mod_write_word(uint32_t p,uint32_t v){for(unsigned i=0;i<4;++i)*ptr(p+i)=(uint8_t)(v>>(i*8));}
uint32_t psx_mod_alloc_guest_memory(uint32_t n,uint32_t align){CHECK(n==192&&align==4);return s_alloc_fail?0:0x9f000000u;}
int psx_mod_disc_file_extent(const char* p,uint32_t* l,uint32_t* n){CHECK(!strcmp(p,s_profile.battle_model));*l=s_lba;*n=s_bytes;return !s_asset_fail;}
void psx_mod_counter_add(const char* p,uint32_t n){CHECK(n==1);if(strstr(p,"reject"))++s_rejected;}
int psx_mod_register_instruction_plugin(const char* p,uint32_t a,uint32_t w,void(*f)(CPUState*,uint32_t)){
    CHECK(!strcmp(p,"ff7.party-gameplay")&&a&&w&&f);++s_registered;return 1;}
int ff7_party_game_is_extra(uint8_t g){return g>=11&&g<11+s_count;}
uint32_t ff7_party_game_record(uint8_t g){return ff7_party_game_is_extra(g)?0x9f010000u+132u*(g-11):0;}
uint32_t ff7_party_game_record_offset(uint8_t g){return ff7_party_game_record(g)-0x8009c738u;}
uint32_t ff7_party_game_alias_word(uint8_t g){uint32_t p=0x9f001000u+4u*(g-11);psx_mod_write_word(p,g);return p;}
uint8_t ff7_party_game_presentation(uint8_t g){CHECK(ff7_party_game_is_extra(g));return 10;}
const FF7PartyProfile* ff7_party_game_profile(uint8_t g){return ff7_party_game_is_extra(g)?&s_profile:NULL;}
uint8_t* ff7_test_battle_ram(void){return s_ram;}
uint8_t* ff7_test_battle_expansion(void){return s_expansion;}
void ff7_test_battle_extent(uint32_t lba,uint32_t bytes){s_lba=lba;s_bytes=bytes;}
void ff7_test_battle_reset(unsigned count){memset(s_ram,0,sizeof s_ram);memset(s_expansion,0,sizeof s_expansion);
    s_count=count;s_rejected=s_alloc_fail=s_asset_fail=0;CHECK(ff7_party_battle_init());
    for(unsigned i=0;i<count;++i)psx_mod_write_byte(ff7_party_game_record((uint8_t)(11+i)),(uint8_t)(11+i));}
void ff7_test_battle_hook(uint32_t pc,uint32_t* regs){CPUState cpu;memset(&cpu,0,sizeof cpu);
    memcpy(cpu.gpr,regs,sizeof cpu.gpr);battle_instruction(&cpu,pc);memcpy(regs,cpu.gpr,sizeof cpu.gpr);}
static void seed(const BattleSite* s){for(unsigned i=0;i<13;++i)psx_mod_write_word(s->pc-24+4*i,s->words[i]);}
int main(void){
    register_ff7_party_battle();CHECK(s_registered==sizeof s_sites/sizeof s_sites[0]);ff7_test_battle_reset(16);
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i){const BattleSite* s=&s_sites[i];seed(s);
        for(unsigned g=0;g<27;++g){uint32_t r[32]={0};
            switch(s->action){
            case OFFSET:r[s->reg]=33*g;ff7_test_battle_hook(s->pc,r);
                CHECK((r[s->reg]<<2)==(g<11?132*g:ff7_party_game_record_offset((uint8_t)g)));break;
            case ALIAS:r[s->reg]=0x800491d0u+4*g;ff7_test_battle_hook(s->pc,r);
                CHECK(r[s->reg]==(g<11?0x800491d0u+4*g:ff7_party_game_alias_word((uint8_t)g)));break;
            case INITIAL_RECORD:r[30]=g;r[9]=132*5;r[3]=0x8009c738u;ff7_test_battle_hook(s->pc,r);
                CHECK(r[3]+r[9]==(g<11?0x8009c738u+660:ff7_party_game_record((uint8_t)g)));break;
            case REFRESH_RECORD:r[7]=g;r[17]=0x8009c738u;ff7_test_battle_hook(s->pc,r);
                CHECK(r[17]==(g<11?0x8009c738u:ff7_party_game_record((uint8_t)g)));break;
            case ARENA_RECORD:r[7]=g;r[3]=0;ff7_test_battle_hook(s->pc,r);
                CHECK(r[3]==(g<11?0:ff7_party_game_record_offset((uint8_t)g)));break;
            case AI_ALIAS:r[19]=g;r[1]=0x800e0000u+g;ff7_test_battle_hook(s->pc,r);
                CHECK(r[19]==g);CHECK(r[1]==(g<11?0x800e0000u+g:s_storage-0x7a58u));break;
            case AI_HEADER:r[19]=g;r[4]=0x80082884u;ff7_test_battle_hook(s->pc,r);
                CHECK(r[19]==g);CHECK(r[4]==(g<11?0x80082884u:s_storage));break;
            case MODEL:r[18]=0x801636b8u;r[2]=14;psx_mod_write_byte(r[18],(uint8_t)g);
                ff7_test_battle_hook(s->pc,r);CHECK(r[2]==(g<11?14:10));break;
            case MOTIONS:r[16]=3;ff7_test_battle_hook(s->pc,r);break;
            case EXTENT:psx_mod_write_word(0x800fa9c6u+s->reg*4,2);psx_mod_write_byte(0x801636d8u,(uint8_t)g);
                ff7_test_battle_hook(s->pc,r);CHECK(r[3]==(g<11?0:s_storage+EXTENTS+s->reg*8));
                if(g>=11){CHECK(psx_mod_read_word(r[3])==s_lba);CHECK(psx_mod_read_word(r[3]+4)==45056);}break;
            }
        }
        uint32_t regs[32]={0};psx_mod_write_word(s->pc-4,0xdeadbeefu);
        ff7_test_battle_hook(s->pc,regs);CHECK(s_rejected==i+1);
    }
    s_alloc_fail=1;CHECK(!ff7_party_battle_init());puts("battle adapter guards,16 extra proxies,native variants,empty AI,extent resolution passed");return 0;
}
