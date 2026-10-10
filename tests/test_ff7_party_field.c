#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/ff7_party_field.c"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x);exit(1);}}while(0)
static uint8_t s_ram[0x200000],s_expansion[0x20000];
static unsigned s_count=16,s_rejected,s_registered;
static struct{uint32_t pc;void(*fn)(CPUState*,uint32_t);}s_callbacks[256];
static FF7PartyProfile s_profile={0x100,10,7,10,0,0,0,"ENEMY6/SEFIROS.LZS","MENU/PCEFI.TIM",1,"FIELD/NIVL",3,0};
void register_ff7_party_resident(void);
static uint8_t* ptr(uint32_t p){p&=0x1fffffffu;if(p<sizeof s_ram)return s_ram+p;
    CHECK(p>=0x1f000000u && p-0x1f000000u<sizeof s_expansion);return s_expansion+p-0x1f000000u;}
uint8_t psx_mod_read_byte(uint32_t p){return *ptr(p);}
uint32_t psx_mod_read_word(uint32_t p){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=(uint32_t)*ptr(p+i)<<(i*8);return v;}
void psx_mod_write_byte(uint32_t p,uint8_t v){*ptr(p)=v;}
void psx_mod_write_word(uint32_t p,uint32_t v){for(unsigned i=0;i<4;++i)*ptr(p+i)=(uint8_t)(v>>(i*8));}
uint32_t psx_mod_alloc_guest_memory(uint32_t n,uint32_t a){CHECK(n==32&&a==4);return 0x9f000000u;}
void psx_mod_counter_add(const char* n,uint32_t v){CHECK(v==1);if(strstr(n,"reject"))++s_rejected;}
int psx_mod_register_instruction_plugin(const char* n,uint32_t pc,uint32_t w,void(*f)(CPUState*,uint32_t)){
    CHECK(!strcmp(n,"ff7.party-gameplay") && w && f && s_registered<256);
    s_callbacks[s_registered].pc=pc;s_callbacks[s_registered++].fn=f;return 1;}
int ff7_party_game_ready(void){return 1;}
unsigned ff7_party_game_extra_count(void){return s_count;}
uint8_t ff7_party_game_extra_guest(unsigned i){return i<s_count?(uint8_t)(11+i):255;}
int ff7_party_game_is_extra(uint8_t g){return g>=11 && g<11+s_count;}
uint8_t ff7_party_game_guest_id(uint16_t id){return id>=0x100 && id<0x100+s_count?(uint8_t)(id-0x100+11):255;}
uint32_t ff7_party_game_record(uint8_t g){return ff7_party_game_is_extra(g)?0x9f010000u+132u*(g-11):0;}
uint32_t ff7_party_game_record_offset(uint8_t g){return ff7_party_game_record(g)-0x8009c738u;}
uint32_t ff7_party_game_alias_word(uint8_t g){uint32_t p=0x9f001000u+4u*(g-11);psx_mod_write_word(p,g);return p;}
const FF7PartyProfile* ff7_party_game_profile(uint8_t g){return ff7_party_game_is_extra(g)?&s_profile:NULL;}
uint8_t* ff7_test_field_ram(void){return s_ram;}
uint8_t* ff7_test_field_expansion(void){return s_expansion;}
void ff7_test_field_reset(unsigned count,unsigned ignored){
    (void)ignored;CHECK(count<=16);memset(s_ram,0,sizeof s_ram);memset(s_expansion,0,sizeof s_expansion);
    s_count=count;s_rejected=s_registered=0;register_ff7_party_field();register_ff7_party_resident();CHECK(ff7_party_field_init());
    for(unsigned i=0;i<count;++i)*ptr(ff7_party_game_record((uint8_t)(11+i)))=(uint8_t)(11+i);
}
void ff7_test_field_hook(uint32_t pc,uint32_t* regs){CPUState cpu;memset(&cpu,0,sizeof cpu);memcpy(cpu.gpr,regs,sizeof cpu.gpr);
    for(unsigned i=0;i<s_registered;++i)if(pc==s_callbacks[i].pc)s_callbacks[i].fn(&cpu,pc);
    memcpy(regs,cpu.gpr,sizeof cpu.gpr);
}
static void seed(const FieldSite* s){for(unsigned i=0;i<13;++i)psx_mod_write_word(s->pc-24+4*i,s->words[i]);}
int main(void){
    ff7_test_field_reset(16,0);CHECK(s_registered>=93);
    psx_mod_write_word(0x8009c6dc,0x80110000);psx_mod_write_word(0x8007e770,0x80120000);
    *ptr(0x80110002)=32;*ptr(0x80120002)=32;
    memset(ptr(0x8009ad30),255,9);memset(ptr(0x8007eb98),255,64);
    for(unsigned i=0;i<16;++i){*ptr(0x8007eb98+i)= (uint8_t)i;CHECK(ff7_party_field_bind((uint16_t)(0x100+i),(uint8_t)i));}
    CHECK(!ff7_party_field_bind(0x100,1));CHECK(!ff7_party_field_bind(0x100,32));
    *ptr(0x8009ad30)=0;CHECK(!ff7_party_field_bind(0x100,0));*ptr(0x8009ad30)=255;
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i){const FieldSite* s=&s_sites[i];seed(s);
        for(unsigned g=0;g<27;++g){uint32_t r[32]={0};
            switch(s->action){
            case HEAL_ALIAS:r[2]=0x800491d0+4*g;ff7_test_field_hook(s->pc,r);
                CHECK(r[2]==(g<11?0x800491d0+4*g:ff7_party_game_alias_word((uint8_t)g)));break;
            case HEAL_RANGE:r[3]=g;ff7_test_field_hook(s->pc,r);CHECK(r[2]==(g>=11));break;
            case HEAL_OFFSET:r[2]=33*g;ff7_test_field_hook(s->pc,r);
                CHECK(r[2]==(g<11?33*g:ff7_party_game_record_offset((uint8_t)g)>>2));break;
            case ENTITY_READ:case ENTITY_WRITE:r[1]=0x8009ad30+g;r[(s->words[6]>>16)&31u]=255;
                ff7_test_field_hook(s->pc,r);CHECK(r[1]==(g<11?0x8009ad30+g:s_entities+g-11));break;
            case ENTITY_RESET:ff7_test_field_hook(s->pc,r);CHECK(ff7_party_field_entity(11)==255);break;
            }
        }
        uint32_t r[32]={0};psx_mod_write_word(s->pc-4,0xdeadbeefu);ff7_test_field_hook(s->pc,r);CHECK(s_rejected==i+1);
    }
    CHECK(ff7_party_field_bind(0x100,0));ff7_party_field_restore();CHECK(ff7_party_field_entity(11)==0);
    puts("field guards,16 independent entity bindings,native/collision rejection,heal routing,rewind preservation passed");return 0;
}
