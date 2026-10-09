#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/ff7_party_results.c"
#define s_sites s_resident_sites
#include "../src/ff7_party_resident.c"
#undef s_sites
#define CHECK(x) do{if(!(x)){fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x);exit(1);}}while(0)
static uint8_t ram[0x200000],expansion[0x20000];
static unsigned registered,rejected,prepared;
static uint8_t* ptr(uint32_t p){p&=0x1fffffffu;if(p<sizeof ram)return ram+p;
    CHECK(p>=0x1f000000u && p-0x1f000000u<sizeof expansion);return expansion+p-0x1f000000u;}
uint8_t psx_mod_read_byte(uint32_t p){return *ptr(p);}
uint32_t psx_mod_read_word(uint32_t p){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=(uint32_t)*ptr(p+i)<<(8*i);return v;}
void psx_mod_write_word(uint32_t p,uint32_t v){for(unsigned i=0;i<4;++i)*ptr(p+i)=(uint8_t)(v>>(8*i));}
void psx_mod_counter_add(const char* n,uint32_t v){CHECK(v==1);if(strstr(n,"reject"))++rejected;}
int psx_mod_register_instruction_plugin(const char* n,uint32_t pc,uint32_t w,void(*fn)(CPUState*,uint32_t)){
    CHECK(!strcmp(n,"ff7.party-gameplay") && pc && w && fn);++registered;return 1;}
int ff7_party_game_ready(void){return 1;}
int ff7_party_game_is_extra(uint8_t g){return g>=11 && g<=26;}
unsigned ff7_party_game_extra_count(void){return 16;}
uint8_t ff7_party_game_extra_guest(unsigned i){return i<16?(uint8_t)(11+i):255;}
uint32_t ff7_party_game_record(uint8_t g){return 0x9f010000u+(g-11)*132u;}
uint32_t ff7_party_game_record_offset(uint8_t g){return ff7_party_game_record(g)-0x8009c738u;}
uint32_t ff7_party_game_alias_word(uint8_t g){uint32_t p=0x9f000000u+4u*(g-11);psx_mod_write_word(p,g);return p;}
int ff7_party_menu_prepare_portrait(uint8_t g){CHECK(ff7_party_game_is_extra(g));++prepared;return 9;}
uint8_t* ff7_test_results_ram(void){return ram;}
uint8_t* ff7_test_results_expansion(void){return expansion;}
void ff7_test_results_reset(void){memset(ram,0,sizeof ram);memset(expansion,0,sizeof expansion);rejected=prepared=0;}
void ff7_test_results_hook(uint32_t pc,uint32_t* regs){CPUState cpu;memset(&cpu,0,sizeof cpu);
    cpu.pc=0x80045678u;memcpy(cpu.gpr,regs,sizeof cpu.gpr);result_instruction(&cpu,pc);
    party_resident_instruction(&cpu,pc);
    CHECK(cpu.pc==0x80045678u);memcpy(regs,cpu.gpr,sizeof cpu.gpr);}
int main(void){
    register_ff7_party_results();CHECK(registered==4);ff7_test_results_reset();
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i){const ResultSite* s=&s_sites[i];
        for(unsigned j=0;j<13;++j)psx_mod_write_word(s->pc-24+j*4,s->words[j]);
        for(unsigned g=0;g<=26;++g){uint32_t r[32]={0},before[32];
            unsigned reg=s->reg;
            if(s->action==RECORD_SCAN){r[6]=g;r[9]=132;r[1]=0x800a0084u;r[5]=1;}
            else if(s->action==RESULT_ALIAS)r[reg]=0x800491d0u+4*g;
            else r[reg]=g;
            memcpy(before,r,sizeof r);ff7_test_results_hook(s->pc,r);
            if(g<11){CHECK(!memcmp(before,r,sizeof r));continue;}
            if(s->action==RECORD_SCAN){CHECK(r[9]==ff7_party_game_record_offset((uint8_t)g));CHECK(r[1]==r[9]+0x800a0000u);CHECK(r[5]==8);}
            else if(s->action==RESULT_ALIAS)CHECK(r[reg]==ff7_party_game_alias_word((uint8_t)g));
            else CHECK(r[reg]==9);
        }
        psx_mod_write_word(s->pc-4,0xdeadbeefu);uint32_t r[32]={0};ff7_test_results_hook(s->pc,r);CHECK(rejected==i+1);
    }
    CHECK(prepared==16);puts("result record lookup, aliases, strides, portraits and native passthrough passed");return 0;
}
