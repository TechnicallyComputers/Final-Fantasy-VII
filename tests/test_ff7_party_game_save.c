/* Full-packet binding, interrupted sector writes, slot replacement, card
 * isolation, reload and pending-packet rewind. Synthetic saves only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/ff7_party_game_save.c"
#define CHECK(x) do{if(!(x)){fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x);exit(1);}}while(0)
static uint8_t ram[0x200000],expansion[0x10000],cards[2][FF7_PARTY_CARD_BYTES];
static FF7PartyState live;
static uint8_t fallback[3]={0,7,255};
static unsigned load_count,init_count,registered;
static int allow_snapshot=1;
static MemcardExtensionLoad loader;
static MemcardExtensionSave writer;
static uint8_t* ptr(uint32_t p){p&=0x1fffffffu;
    if(p<sizeof ram)return ram+p;
    CHECK(p>=0x1f000000u && p-0x1f000000u<sizeof expansion);return expansion+p-0x1f000000u;
}
uint8_t psx_mod_read_byte(uint32_t p){return *ptr(p);}
uint32_t psx_mod_read_word(uint32_t p){uint32_t v=0;for(unsigned i=0;i<4;++i)v|=(uint32_t)*ptr(p+i)<<(i*8);return v;}
void psx_mod_write_byte(uint32_t p,uint8_t v){*ptr(p)=v;}
void psx_mod_write_word(uint32_t p,uint32_t v){for(unsigned i=0;i<4;++i)*ptr(p+i)=(uint8_t)(v>>(i*8));}
uint32_t psx_mod_alloc_guest_memory(uint32_t size,uint32_t alignment){CHECK(size<sizeof expansion && alignment==4);return 0x9f000000u;}
void psx_mod_counter_add(const char* name,uint32_t value){CHECK(name && value==1);}
int psx_mod_register_instruction_plugin(const char* id,uint32_t pc,uint32_t expected,void(*fn)(CPUState*,uint32_t)){
    CHECK(!strcmp(id,"ff7.party-gameplay") && pc && expected && fn);++registered;return 1;
}
void memcard_set_extension_codec(MemcardExtensionLoad load,MemcardExtensionSave save){loader=load;writer=save;}
int memcard_export_raw(int card,uint8_t* out){if(card<0||card>=2)return -1;memcpy(out,cards[card],sizeof cards[card]);return 0;}
int ff7_party_game_ready(void){return 1;}
int ff7_party_game_is_extra(uint8_t guest){return guest==11;}
uint32_t ff7_party_game_record_offset(uint8_t guest){return guest==11?0x80140000u-0x8009c738u:0;}
int ff7_party_game_fallback(uint8_t out[3]){memcpy(out,fallback,3);return 1;}
FF7PartyResult ff7_party_game_snapshot(FF7PartyState* out){if(!allow_snapshot)return FF7_PARTY_INVALID;*out=live;return FF7_PARTY_OK;}
FF7PartyResult ff7_party_game_load(const FF7PartyState* state,const uint8_t native[3]){
    CHECK(native[0]==0 && native[1]==7 && native[2]==255);live=*state;++load_count;return FF7_PARTY_OK;
}
int ff7_party_game_initialize(const uint8_t native[3]){CHECK(native[0]==0);++init_count;return 1;}
static void frame(uint8_t* p){uint8_t x=0;for(unsigned i=0;i<127;++i)x^=p[i];p[127]=x;}
static void blank(uint8_t* base){memset(base,0,FF7_PARTY_CARD_BYTES);base[0]='M';base[1]='C';frame(base);}
static void directory(uint8_t* base,unsigned slot,const char* name){
    uint8_t* p=base+slot*128;memset(p,0,128);p[0]=0x51;p[5]=0x20;p[8]=p[9]=255;
    memcpy(p+10,name,strlen(name));frame(p);
}
static void fixture(void){
    memset(ram,0,sizeof ram);memset(expansion,0,sizeof expansion);blank(cards[0]);blank(cards[1]);
    ff7_party_init(&live);uint8_t record[132];memset(record,0x5a,sizeof record);
    CHECK(ff7_party_add_sephiroth(&live,record)==FF7_PARTY_OK);
    const uint16_t active[3]={0,7,0x100};CHECK(ff7_party_select(&live,active)==FF7_PARTY_OK);
    live.stored_known=1;live.stored[0]=0x100;live.stored[1]=7;live.stored_hint[1]=10;
    CHECK(ff7_party_game_save_init());CHECK(loader(0,cards[0],NULL,0)==0);CHECK(loader(1,cards[1],NULL,0)==0);
    memcpy(ptr(0x80100000),"bu00:BASCUS-94163FF7-S01",24);
    uint8_t* packet=ptr(0x801e6f38);packet[0]='S';packet[1]='C';packet[2]=0x11;packet[3]=1;
    packet[8191]=0x77; /* Force the complete-packet match to require final sector. */
    uint8_t* map=packet+512;memset(map,0,FF7_NATIVE_SAVE_BYTES);
    memcpy(map+FF7_NATIVE_ACTIVE_OFFSET,(uint8_t[]){0,7,11},3);
    memcpy(map+FF7_NATIVE_STORED_OFFSET,(uint8_t[]){11,10,255},3);
    map[0x54+1]=8;memcpy(map+0x54+16,"CLOUD",6);
    uint16_t crc=ff7_native_save_checksum(map);map[0]=(uint8_t)crc;map[1]=(uint8_t)(crc>>8);
    memcpy(ptr(0x8009cbdc),(uint8_t[]){0,7,255},3);
}
static void seed(uint32_t pc){for(unsigned i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
    if(s_sites[i].pc==pc)for(unsigned j=0;j<13;++j)psx_mod_write_word(pc-24+j*4,s_sites[i].words[j]);}
static void hook(uint32_t pc,CPUState* cpu){seed(pc);cpu->pc=0x80045678u;instruction(cpu,pc);CHECK(cpu->pc==0x80045678u);}
uint8_t* ff7_test_game_save_ram(void){return ram;}
uint8_t* ff7_test_game_save_expansion(void){return expansion;}
void ff7_test_game_save_reset(void){fixture();}
void ff7_test_game_save_hook(uint32_t pc,uint32_t* regs){CPUState cpu;memset(&cpu,0,sizeof cpu);
    cpu.pc=pc;memcpy(cpu.gpr,regs,sizeof cpu.gpr);instruction(&cpu,pc);memcpy(regs,cpu.gpr,sizeof cpu.gpr);}
int main(void){
    /* Story aliases 9/10 and their native rows share storage; projection must
     * not insert the same underlying member twice when replacing an extra. */
    uint8_t projected[FF7_NATIVE_SAVE_BYTES]={0};
    memcpy(projected+FF7_NATIVE_ACTIVE_OFFSET,(uint8_t[]){9,11,255},3);
    memcpy(projected+FF7_NATIVE_STORED_OFFSET,(uint8_t[]){10,11,255},3);
    CHECK(ff7_native_save_project(projected,sizeof projected,(uint8_t[]){7,6,255}));
    CHECK(!memcmp(projected+FF7_NATIVE_ACTIVE_OFFSET,(uint8_t[]){9,7,255},3));
    CHECK(!memcmp(projected+FF7_NATIVE_STORED_OFFSET,(uint8_t[]){10,6,255},3));
    CHECK(ff7_native_save_valid(projected,sizeof projected));
    CHECK(!ff7_native_save_project(projected,sizeof projected,(uint8_t[]){7,10,255}));
    register_ff7_party_game_save();CHECK(registered==5);fixture();
    uint8_t original_map[FF7_NATIVE_SAVE_BYTES];memcpy(original_map,ptr(0x801e7138),sizeof original_map);
    CPUState cpu;memset(&cpu,0,sizeof cpu);cpu.gpr[19]=0x80100000;
    hook(0x801d2900,&cpu);CHECK(cpu.gpr[19]==0x80100000 && psx_mod_read_word(s_pending)==1);
    const uint8_t* packet=ptr(0x801e6f38);const uint8_t* map=packet+512;
    CHECK(ff7_native_save_valid(map,FF7_NATIVE_SAVE_BYTES));
    CHECK(!memcmp(map+0x4f8,(uint8_t[]){0,7,255},3));
    CHECK(!memcmp(map+0xcad,(uint8_t[]){0,10,255},3));
    CHECK(!memcmp(original_map+0x54,map+0x54,9*132));
    static uint8_t tail[FF7_PARTY_CARD_EXTENSION_MAX];FF7PartyCard decoded;
    directory(cards[0],2,"BASCUS-94163FF7-S01");
    CHECK(writer(0,cards[0],tail,sizeof tail)==0); /* Directory alone is insufficient. */
    for(unsigned sector=0;sector<64;++sector){
        memcpy(cards[0]+2*8192+sector*128,packet+sector*128,128);
        int bytes=writer(0,cards[0],tail,sizeof tail);
        if(sector<63)CHECK(bytes==0);
        else{
            CHECK(bytes>0);CHECK(ff7_party_card_decode(&decoded,cards[0],sizeof cards[0],tail,(unsigned)bytes)==FF7_PARTY_OK);
            CHECK(decoded.count==1 && decoded.slots[0].directory_slot==2);
            CHECK(decoded.slots[0].party.active[2]==0x100 && decoded.slots[0].party.stored[0]==0x100);
            CHECK(loader(0,cards[0],tail,(unsigned)bytes)==0);
        }
    }
    CHECK(writer(1,cards[1],tail,sizeof tail)==0);
    /* Exact name is bound; moving/changing a directory must remove old extras. */
    cards[0][2*128+10]^=1;frame(cards[0]+2*128);CHECK(writer(0,cards[0],tail,sizeof tail)==0);
    directory(cards[0],2,"BASCUS-94163FF7-S01");int bytes=writer(0,cards[0],tail,sizeof tail);CHECK(bytes>0);
    CHECK(loader(0,cards[0],tail,(unsigned)bytes)==0);
    memcpy(ptr(0x80190038),ptr(0x80100000),26);cpu.gpr[29]=0x80190000;cpu.gpr[2]=0;
    hook(0x801d2134,&cpu);CHECK(load_count==1);
    CHECK(loader(0,cards[0],NULL,0)==0);hook(0x801d2134,&cpu);CHECK(init_count==1);
    /* Rewind an in-flight packet, then reapply it against matching card bytes. */
    static uint8_t backup[sizeof expansion];memcpy(backup,expansion,sizeof backup);
    hook(0x801d2a14,&cpu);CHECK(psx_mod_read_word(s_pending)==0);
    memcpy(expansion,backup,sizeof backup);ff7_party_game_save_restore();CHECK(writer(0,cards[0],tail,sizeof tail)>0);
    allow_snapshot=0;hook(0x801d2900,&cpu);CHECK(cpu.gpr[19]==s_pending+CARDS*P_BYTES && *ptr(cpu.gpr[19])==0);
    /* Corrupt native checksums and malformed paths cannot attach metadata. */
    allow_snapshot=1;cpu.gpr[19]=0x80100000;psx_mod_write_byte(0x801e7138,0);psx_mod_write_byte(0x801e7139,0);
    hook(0x801d2900,&cpu);CHECK(cpu.gpr[19]!=0x80100000);
    hook(0x80011dbc,&cpu);CHECK(init_count==2);
    puts("native fallback projection and full-packet card metadata lifecycle passed");return 0;
}
