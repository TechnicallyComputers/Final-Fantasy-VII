/* Compile with tests/ff7_party_menu_stubs first, src and runtime/include.
 * Also builds as a shared DLL for original-MIPS menu execution tests. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/ff7_party_menu.c"
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x); exit(1); } } while(0)
static uint8_t s_ram[0x200000],s_expansion[0x20000];
static uint16_t s_vram[1024*512];
static unsigned s_count=1,s_registered,s_observed,s_rejected,s_alloc_fail;
static unsigned s_gpu_phase,s_gpu_x,s_gpu_y,s_gpu_w,s_gpu_h,s_gpu_pixel;
static FF7PartyProfile s_profile={0x100,10,7,10,0,0,0,"ENEMY6/SEFIROS.LZS","MENU/PCEFI.TIM",0,NULL,0};
static uint8_t* ptr(uint32_t address) {
    uint32_t p=address&0x1fffffffu;
    if(p<sizeof s_ram) return s_ram+p;
    CHECK(p>=0x1f000000u && p-0x1f000000u<sizeof s_expansion);
    return s_expansion+(p-0x1f000000u);
}
uint8_t psx_mod_read_byte(uint32_t a){return *ptr(a);}
uint32_t psx_mod_read_word(uint32_t a){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=(uint32_t)*ptr(a+i)<<(8*i);return v;}
void psx_mod_write_byte(uint32_t a,uint8_t v){*ptr(a)=v;}
void psx_mod_write_half(uint32_t a,uint16_t v){for(unsigned i=0;i<2;++i)*ptr(a+i)=(uint8_t)(v>>(8*i));}
void psx_mod_write_word(uint32_t a,uint32_t v){for(unsigned i=0;i<4;++i)*ptr(a+i)=(uint8_t)(v>>(8*i));}
uint32_t psx_mod_alloc_guest_memory(uint32_t n,uint32_t align){CHECK(n==4096&&align==4);return s_alloc_fail?0:0x9f000000u;}
int psx_mod_read_disc_file(const char* p,void* b,uint32_t c,uint32_t* n){(void)p;(void)b;(void)c;*n=0;return 0;}
void psx_mod_counter_add(const char* p,uint32_t n){CHECK(n==1);if(strstr(p,"reject"))++s_rejected;}
int psx_mod_register_instruction_plugin(const char* p,uint32_t a,uint32_t w,void(*f)(CPUState*,uint32_t)){
    CHECK(!strcmp(p,"ff7.party-gameplay")&&a&&w&&f);++s_registered;return 1;
}
unsigned ff7_party_game_extra_count(void){return s_count;}
uint8_t ff7_party_game_extra_guest(unsigned i){return i<s_count?(uint8_t)(11+i):255;}
int ff7_party_game_is_extra(uint8_t g){return g>=11&&g<11+s_count;}
uint32_t ff7_party_game_record(uint8_t g){return ff7_party_game_is_extra(g)?0x9f010000u+(g-11)*132u:0;}
uint8_t ff7_party_game_presentation(uint8_t g){return g==11?10:0;}
const FF7PartyProfile* ff7_party_game_profile(uint8_t g){return g==11?&s_profile:NULL;}
void ff7_party_game_observe_active(void){++s_observed;}
uint16_t gpu_vram_peek(int x,int y){CHECK(x>=0&&x<1024&&y>=0&&y<512);return s_vram[y*1024+x];}
void gpu_write_gp1(uint32_t w){CHECK(w==0x04000000u||w==0x04000002u);}
void gpu_write_gp0(uint32_t w){
    if(!s_gpu_phase){if(w==0xa0000000u)s_gpu_phase=1;else CHECK(w==0x01000000u);return;}
    if(s_gpu_phase==1){s_gpu_x=w&0xffff;s_gpu_y=w>>16;s_gpu_phase=2;return;}
    if(s_gpu_phase==2){s_gpu_w=w&0xffff;s_gpu_h=w>>16;s_gpu_pixel=0;s_gpu_phase=3;return;}
    for(unsigned i=0;i<2;++i){unsigned x=s_gpu_x+s_gpu_pixel%s_gpu_w,y=s_gpu_y+s_gpu_pixel/s_gpu_w;
        CHECK(x<1024&&y<512);s_vram[y*1024+x]=(uint16_t)(w>>(16*i));++s_gpu_pixel;}
    if(s_gpu_pixel==s_gpu_w*s_gpu_h)s_gpu_phase=0;
}
uint8_t* ff7_test_menu_ram(void){return s_ram;}
uint8_t* ff7_test_menu_expansion(void){return s_expansion;}
unsigned ff7_test_menu_observed(void){return s_observed;}
void ff7_test_menu_portrait(const uint8_t* bytes){
    CHECK(crc32(bytes,sizeof s_portrait)==0x6800bc48u);
    memcpy(s_portrait,bytes,sizeof s_portrait);s_portrait_valid=1;
}
void ff7_test_menu_reset(unsigned extras){
    memset(s_ram,0,sizeof s_ram);memset(s_expansion,0,sizeof s_expansion);
    s_count=extras;s_observed=s_rejected=s_gpu_phase=s_alloc_fail=0;
    CHECK(ff7_party_menu_init());
    /* Unit/oracle tests exercise transfer mechanics with a synthetic portrait;
     * production separately requires the original asset CRC and exact size. */
    memset(s_portrait,0xa5,sizeof s_portrait);s_portrait_valid=1;
}
void ff7_test_menu_hook(uint32_t pc,uint32_t* regs){CPUState cpu;memset(&cpu,0,sizeof cpu);
    memcpy(cpu.gpr,regs,sizeof cpu.gpr);menu_instruction(&cpu,pc);memcpy(regs,cpu.gpr,sizeof cpu.gpr);}
static void seed(const MenuSite* s){for(unsigned i=0;i<13;++i)psx_mod_write_word(s->pc-24+4*i,s->words[i]);}
static const MenuSite* find(enum Action a,enum Menu m){
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i) {
        if(s_sites[i].action==a&&s_sites[i].menu==m)return &s_sites[i];
    }
    return NULL;
}
int main(void){
    register_ff7_party_menu();CHECK(s_registered==sizeof s_sites/sizeof s_sites[0]);
    ff7_test_menu_reset(16);
    for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i){
        const MenuSite* s=&s_sites[i];seed(s);
        if(s->action!=OFFSET)continue;
        for(unsigned id=0;id<27;++id){uint32_t r[32]={0};r[s->reg]=33*id;
            ff7_test_menu_hook(s->pc,r);
            CHECK(((r[s->reg]<<2)+NATIVE)==(id<11?NATIVE+132*id:ff7_party_game_record((uint8_t)id)));
        }
        uint32_t r[32]={0};r[s->reg]=363;psx_mod_write_word(s->pc-4,0);
        ff7_test_menu_hook(s->pc,r);CHECK(r[s->reg]==363);
    }
    const MenuSite* s=find(ALIAS,MENU_EQIPMENU);seed(s);
    for(unsigned id=0;id<27;++id){uint32_t r[32]={0};r[s->reg]=ALIAS_TABLE+4*id;ff7_test_menu_hook(s->pc,r);
        if(id<11)CHECK(r[s->reg]==ALIAS_TABLE+4*id);else CHECK(psx_mod_read_word(r[s->reg])==id);}
    s=find(PHS_READY,MENU_FORMMENU);seed(s);memset(s_ram+0x1d3424,255,9);
    s_ram[0x9cbdc]=0;s_ram[0x9cbdd]=7;s_ram[0x9cbde]=11;
    for(unsigned i=0;i<1024*512;++i)s_vram[i]=(uint16_t)(i*7);
    uint16_t before=s_vram[9*1024+384],image_before=s_vram[448*1024+856];
    uint32_t r[32]={0};ff7_test_menu_hook(s->pc,r);
    CHECK(s_ram[0x1d3424]==12&&s_ram[0x1d342c]==20);CHECK(s_ram[0x1d342d]==0);
    CHECK(s_vram[9*1024+384]==0xa5a5&&s_vram[448*1024+856]==0xa5a5);
    ff7_party_menu_restore();s=find(PHS_CLOSE,MENU_FORMMENU);seed(s);ff7_test_menu_hook(s->pc,r);
    CHECK(s_vram[9*1024+384]==before&&s_vram[448*1024+856]==image_before);
    s=find(LIST_APPEND,MENU_EQIPMENU);seed(s);r[8]=9;ff7_test_menu_hook(s->pc,r);
    CHECK(r[8]==25&&psx_mod_read_byte(s_storage+EXCHANGE+24)==26);
    s=find(PHS_SWAP,MENU_FORMMENU);seed(s);ff7_test_menu_hook(s->pc,r);CHECK(s_observed==1);
    s_alloc_fail=1;CHECK(!ff7_party_menu_init());
    puts("ff7_party_menu: registry offsets, guards, aliases, roster bounds, portrait backup/restore passed");
    return 0;
}
