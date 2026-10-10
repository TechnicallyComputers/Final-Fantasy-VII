#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/ff7_party_field_loader.c"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"%s:%d %s\n",__FILE__,__LINE__,#x);abort();}}while(0)
static uint8_t ram_bytes[0x200000],expansion_bytes[0x20000],gpu_bytes[0x600000];
static unsigned guest_used,gpu_used,rejects,registered,file_count;
static uint8_t extra_guest=11;
void ff7_test_loader_guest(unsigned g){if(g<11 || g>26)abort();extra_guest=(uint8_t)g;}
static FF7PartyProfile profile={0x100,10,7,10,0,0,0,"ENEMY6/SEFIROS.LZS","MENU/PCEFI.TIM",1,"FIELD/NIVL",3,0};
static struct{uint32_t pc;void(*fn)(CPUState*,uint32_t);}callbacks[512];
static struct{char path[80];const void* data;uint32_t size,lba;}files[20];
void register_ff7_party_field(void);
void register_ff7_party_field_state(void);
static uint8_t* pointer(uint32_t p){p&=0x1fffffffu;
    if(p<sizeof ram_bytes)return ram_bytes+p;
    if(p>=0x1f000000 && p-0x1f000000<sizeof expansion_bytes)return expansion_bytes+p-0x1f000000;
    CHECK(p>=0x800000 && p-0x800000<sizeof gpu_bytes);return gpu_bytes+p-0x800000;
}
uint8_t psx_mod_read_byte(uint32_t p){return *pointer(p);}
uint32_t psx_mod_read_word(uint32_t p){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=(uint32_t)*pointer(p+i)<<(8*i);return v;}
void psx_mod_write_byte(uint32_t p,uint8_t v){*pointer(p)=v;}
void psx_mod_write_word(uint32_t p,uint32_t v){for(unsigned i=0;i<4;++i)*pointer(p+i)=(uint8_t)(v>>(8*i));}
uint32_t psx_mod_alloc_guest_memory(uint32_t n,uint32_t a){guest_used=(guest_used+a-1)&~(a-1);CHECK(guest_used+n<=sizeof expansion_bytes);uint32_t p=0x9f000000+guest_used;guest_used+=n;return p;}
uint32_t psx_mod_alloc_gpu_dma_memory(uint32_t n,uint32_t a){gpu_used=(gpu_used+a-1)&~(a-1);CHECK(gpu_used+n<=sizeof gpu_bytes);uint32_t p=0x80800000+gpu_used;gpu_used+=n;return p;}
void psx_mod_counter_add(const char* s,uint32_t n){CHECK(n==1);if(strstr(s,"reject"))++rejects;}
int psx_mod_register_instruction_plugin(const char* id,uint32_t pc,uint32_t word,void(*fn)(CPUState*,uint32_t)){
    (void)word;CHECK(!strcmp(id,"ff7.party-gameplay")&&registered<512);callbacks[registered].pc=pc;callbacks[registered++].fn=fn;return 1;
}
int psx_mod_read_disc_file(const char* p,void* out,uint32_t cap,uint32_t* size){
    for(unsigned i=0;i<file_count;++i)if(!strcmp(p,files[i].path)){
        *size=files[i].size;if(!out)return cap==0;if(cap<*size)return 0;memcpy(out,files[i].data,*size);return 1;
    }return 0;
}
int psx_mod_disc_file_extent(const char* p,uint32_t* lba,uint32_t* size){
    for(unsigned i=0;i<file_count;++i)if(!strcmp(p,files[i].path)){*size=files[i].size;*lba=files[i].lba;return 1;}
    return 0;
}
int ff7_party_game_ready(void){return 1;}
unsigned ff7_party_game_extra_count(void){return 1;}
uint8_t ff7_party_game_extra_guest(unsigned i){return i==0?extra_guest:255;}
int ff7_party_game_is_extra(uint8_t g){return g==extra_guest;}
const FF7PartyProfile* ff7_party_game_profile(uint8_t g){return g==extra_guest?&profile:NULL;}
uint8_t ff7_party_game_guest_id(uint16_t id){return id==0x100?extra_guest:255;}
uint32_t ff7_party_game_record_offset(uint8_t g){(void)g;return 0;}
uint32_t ff7_party_game_alias_word(uint8_t g){(void)g;return 0;}
uint8_t* ff7_test_loader_ram(void){return ram_bytes;}
uint8_t* ff7_test_loader_expansion(void){return expansion_bytes;}
uint8_t* ff7_test_loader_gpu(void){return gpu_bytes;}
unsigned ff7_test_loader_rejects(void){return rejects;}
void ff7_test_loader_file(const char* p,const void* data,uint32_t n,uint32_t lba){CHECK(file_count<20&&strlen(p)<80);strcpy(files[file_count].path,p);files[file_count].data=data;files[file_count].size=n;files[file_count++].lba=lba;}
void ff7_test_loader_reset(void){
    memset(ram_bytes,0,sizeof ram_bytes);memset(expansion_bytes,0,sizeof expansion_bytes);memset(gpu_bytes,0,sizeof gpu_bytes);
    guest_used=gpu_used=rejects=registered=file_count=0;register_ff7_party_field();register_ff7_party_field_loader();register_ff7_party_field_state();
    CHECK(ff7_party_field_init());CHECK(ff7_party_field_loader_init());
}
void ff7_test_loader_hook(uint32_t pc,uint32_t* regs){CPUState cpu;memset(&cpu,0,sizeof cpu);cpu.pc=0x81234560;memcpy(cpu.gpr,regs,sizeof cpu.gpr);
    for(unsigned i=0;i<registered;++i)if(callbacks[i].pc==pc)callbacks[i].fn(&cpu,pc);
    CHECK(cpu.pc==0x81234560);if(pc==0x800aa930)CHECK(!memcmp(cpu.gpr,regs,sizeof cpu.gpr));memcpy(regs,cpu.gpr,sizeof cpu.gpr);
}
int main(void){ff7_test_loader_reset();CHECK(registered==433);CHECK(guest_used<0x20000&&gpu_used==0x500000);
    uint32_t r[32]={0};ff7_test_loader_hook(0x800ba534,r);CHECK(rejects==1);
    puts("field loader allocation and guard rejection passed");return 0;
}
