#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/ff7_party_field_state.c"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line%d %s\n",__LINE__,#x);abort();}}while(0)
static uint8_t ram_bytes[0x200000],expansion_bytes[0x10000];
static unsigned registered,rejects;
static uint8_t* pointer(uint32_t p){p&=0x1fffffffu;if(p<sizeof ram_bytes)return ram_bytes+p;
    CHECK(p>=0x1f000000 && p-0x1f000000<sizeof expansion_bytes);return expansion_bytes+p-0x1f000000;}
uint8_t psx_mod_read_byte(uint32_t p){return *pointer(p);}
uint32_t psx_mod_read_word(uint32_t p){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=(uint32_t)*pointer(p+i)<<(8*i);return v;}
void psx_mod_write_byte(uint32_t p,uint8_t v){*pointer(p)=v;}
void psx_mod_write_word(uint32_t p,uint32_t v){for(unsigned i=0;i<4;++i)*pointer(p+i)=(uint8_t)(v>>(8*i));}
uint32_t psx_mod_alloc_guest_memory(uint32_t n,uint32_t a){CHECK(n==STATE_BYTES+32&&a==16);return 0x9f000000;}
int ff7_party_game_ready(void){return 1;}
void psx_mod_counter_add(const char* n,uint32_t v){CHECK(v==1);if(strstr(n,"reject"))++rejects;}
int psx_mod_register_instruction_plugin(const char* id,uint32_t pc,uint32_t word,void(*fn)(CPUState*,uint32_t)){
    CHECK(!strcmp(id,"ff7.party-gameplay")&&pc&&word&&fn);++registered;return 1;
}
uint8_t* ff7_test_state_ram(void){return ram_bytes;}
uint8_t* ff7_test_state_expansion(void){return expansion_bytes;}
void ff7_test_state_reset(void){memset(ram_bytes,0,sizeof ram_bytes);memset(expansion_bytes,0,sizeof expansion_bytes);registered=rejects=0;
    register_ff7_party_field_state();CHECK(ff7_party_field_state_init());}
void ff7_test_state_hook(uint32_t pc,uint32_t* r){CPUState cpu;memset(&cpu,0,sizeof cpu);cpu.pc=0x81234560;
    memcpy(cpu.gpr,r,sizeof cpu.gpr);instruction(&cpu,pc);CHECK(cpu.pc==0x81234560);memcpy(r,cpu.gpr,sizeof cpu.gpr);}
int main(void){
    ff7_test_state_reset();CHECK(registered==400);CHECK(!ff7_party_field_state_begin(0x80074ea4,48,16,16));
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)for(unsigned j=0;j<13;++j)
        psx_mod_write_word(s_sites[i].pc-24+4*j,s_sites[i].words[j]);
    for(unsigned i=0;i<16*STATE_STRIDE;++i)psx_mod_write_byte(0x80074ea4+i,(uint8_t)i);
    CHECK(!ff7_party_field_state_begin(0x80074ea8,48,16,16));CHECK(!ff7_party_field_state_begin(0x80074ea4,49,16,16));
    CHECK(ff7_party_field_state_begin(0x80074ea4,48,16,16)==s_arena);
    CHECK(!memcmp(pointer(0x80074ea4),pointer(s_arena),16*STATE_STRIDE));
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i){
        if(s_sites[i].action!=BASE)continue;
        uint32_t r[32]={0};r[s_sites[i].reg]=0x80070000;ff7_test_state_hook(s_sites[i].pc,r);
        CHECK(r[s_sites[i].reg]==s_arena-0x4ea4);r[s_sites[i].reg]=0x80080000;
        ff7_test_state_hook(s_sites[i].pc,r);CHECK(r[s_sites[i].reg]==0x80080000);
    }
    psx_mod_write_byte(s_arena,123);ff7_party_field_state_end();uint32_t r[32]={0};r[1]=0x80070000;ff7_test_state_hook(0x80011a58,r);CHECK(r[1]==0x80070000);
    CHECK(ff7_party_field_state_begin(0x80074ea4,48,16,16)==s_arena && psx_mod_read_byte(s_arena)==123);
    for(unsigned e=48;e<64;++e){psx_mod_write_byte(0x800722c4,(uint8_t)e);r[3]=0x800a0000;ff7_test_state_hook(0x800c576c,r);
        CHECK(psx_mod_read_byte(r[3]-0x393c)==16+e-48);r[1]=0x800a0000;ff7_test_state_hook(0x800c5780,r);CHECK(r[1]==r[3]);}
    ff7_party_field_state_end();ff7_party_field_state_end(); /* rejected/native field in between */
    CHECK(ff7_party_field_state_begin(0x80074ea4,48,16,16)==s_arena && psx_mod_read_byte(s_arena)==0);
    puts("398 field-state bases,2 independent CHAR counter seams,32-record bounds and native preservation passed");return 0;
}
