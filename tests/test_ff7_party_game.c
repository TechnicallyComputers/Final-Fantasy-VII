/* Lifecycle/storage tests: two independent additions, native preservation,
 * atomic selection, save reload/proxy rebinding and whole-state rewind. No
 * original assets are embedded; a synthetic gzip kernel exercises the loader.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/ff7_party_game.c"
#include "../src/ff7_party_resident.c"
#include "cpu_state.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x); exit(1); } } while(0)
static uint8_t ram[0x200000], expansion[4096], kernel[4096];
static uint32_t kernel_size;
static void (*activate_callback)(void), (*vblank_callback)(void), (*restore_callback)(void);
static unsigned hook_count, restores;
static int disc_available=1;

static uint8_t* address(uint32_t p) {
    p &= 0x1fffffffu;
    if (p < sizeof ram) return ram+p;
    CHECK(p>=0x1f000000u && p-0x1f000000u<sizeof expansion);
    return expansion+p-0x1f000000u;
}
uint8_t psx_mod_read_byte(uint32_t p) { return *address(p); }
uint16_t psx_mod_read_half(uint32_t p) { return psx_mod_read_byte(p)|(uint16_t)psx_mod_read_byte(p+1)<<8; }
uint32_t psx_mod_read_word(uint32_t p) { return psx_mod_read_half(p)|(uint32_t)psx_mod_read_half(p+2)<<16; }
void psx_mod_write_byte(uint32_t p,uint8_t v) { *address(p)=v; }
void psx_mod_write_half(uint32_t p,uint16_t v) { psx_mod_write_byte(p,(uint8_t)v); psx_mod_write_byte(p+1,(uint8_t)(v>>8)); }
void psx_mod_write_word(uint32_t p,uint32_t v) { psx_mod_write_half(p,(uint16_t)v); psx_mod_write_half(p+2,(uint16_t)(v>>16)); }
uint32_t psx_mod_alloc_guest_memory(uint32_t bytes,uint32_t align) {
    CHECK(bytes==GAME_BYTES && align==4); memset(expansion,0,sizeof expansion); return 0x9f000000u;
}
void psx_mod_counter_add(const char* name,uint32_t delta) { CHECK(name && delta==1); }
int psx_mod_register_activation_plugin(const char* id,void (*fn)(void)) { CHECK(!strcmp(id,"ff7.party-gameplay")); activate_callback=fn; return 1; }
int psx_mod_register_vblank_plugin(const char* id,void (*fn)(void)) { CHECK(!strcmp(id,"ff7.party-gameplay")); vblank_callback=fn; return 1; }
int psx_mod_register_savestate_plugin(const char* id,void (*fn)(void)) { CHECK(!strcmp(id,"ff7.party-gameplay")); restore_callback=fn; return 1; }
int psx_mod_register_instruction_plugin(const char* id,uint32_t pc,uint32_t word,void (*fn)(struct CPUState*,uint32_t)) {
    CHECK(!strcmp(id,"ff7.party-gameplay") && pc && word && fn); ++hook_count; return 1;
}
int psx_mod_game_started(void) { return 1; }
int ff7_party_menu_init(void) { return 1; }
void ff7_party_menu_restore(void) { ++restores; }
int ff7_party_battle_init(void) { return 1; }
int ff7_party_limit_init(void) { return 1; }
void ff7_party_limit_restore(void) { }
void ff7_party_battle_restore(void) { }
int ff7_party_game_save_init(void) { return 1; }
void ff7_party_game_save_restore(void) { }
int ff7_party_field_init(void) { return 1; }
void ff7_party_field_restore(void) { }
int ff7_party_field_loader_init(void) { return 1; }
void ff7_party_field_loader_restore(void) { }
int psx_mod_read_disc_file(const char* path,void* out,uint32_t cap,uint32_t* bytes) {
    CHECK(!strcmp(path,"INIT/KERNEL.BIN")); *bytes=0;
    if (!disc_available) return 0;
    if (out && cap<kernel_size) return 0;
    if (out) memcpy(out,kernel,kernel_size);
    *bytes=kernel_size; return 1;
}

static void synthetic_kernel(void) {
    static const uint8_t ids[9]={0,1,2,3,4,5,9,10,8};
    uint8_t records[9*FF7_PARTY_RECORD_SIZE];
    memset(records,0,sizeof records);
    for (unsigned i=0;i<9;++i) {
        uint8_t* r=records+i*FF7_PARTY_RECORD_SIZE;
        r[0]=ids[i]; r[1]=(uint8_t)(10+i); r[0x2e]=100;
        r[0x10]=(uint8_t)('A'+i); r[0x11]=255;
    }
    kernel_size=0;
    for (unsigned i=0;i<4;++i) {
        uint8_t zipped[2048], empty=0;
        z_stream s; memset(&s,0,sizeof s);
        CHECK(deflateInit2(&s,9,Z_DEFLATED,31,8,Z_DEFAULT_STRATEGY)==Z_OK);
        s.next_in=i==3 ? records : &empty;
        s.avail_in=i==3 ? sizeof records : 1;
        s.next_out=zipped; s.avail_out=sizeof zipped;
        CHECK(deflate(&s,Z_FINISH)==Z_STREAM_END);
        unsigned bytes=(unsigned)s.total_out;
        deflateEnd(&s);
        unsigned unpacked=i==3 ? sizeof records : 1;
        CHECK(kernel_size+6+bytes<sizeof kernel);
        kernel[kernel_size++]=(uint8_t)bytes; kernel[kernel_size++]=(uint8_t)(bytes>>8);
        kernel[kernel_size++]=(uint8_t)unpacked; kernel[kernel_size++]=(uint8_t)(unpacked>>8);
        kernel[kernel_size++]=(uint8_t)i; kernel[kernel_size++]=0;
        memcpy(kernel+kernel_size,zipped,bytes); kernel_size+=bytes;
    }
    psx_mod_write_byte(NATIVE_RECORDS+1,10);
    psx_mod_write_half(NATIVE_RECORDS+0x2e,100);
    psx_mod_write_byte(ACTIVE,0); psx_mod_write_byte(ACTIVE+1,7); psx_mod_write_byte(ACTIVE+2,255);
    for(unsigned i=0;i<3;++i)psx_mod_write_byte(0x8009d391u+i,255);
}

static void lifecycle(void) {
    static const FF7PartyProfile second={0x101,10,7,10,0,0,0,"test/model","test/portrait",0,NULL,0,0};
    register_ff7_party_game();
    CHECK(ff7_party_game_register_profile(&second));
    CHECK(!ff7_party_game_register_profile(&second));
    register_ff7_party_resident();
    CHECK(hook_count==sizeof s_sites/sizeof s_sites[0]);
    activate_callback();
    CHECK(!ff7_party_game_register_profile(&second));
    CHECK(!ff7_party_game_ready());
    synthetic_kernel();
    uint8_t original[9*FF7_PARTY_RECORD_SIZE];
    memcpy(original,address(NATIVE_RECORDS),sizeof original);
    disc_available=0; vblank_callback(); CHECK(!ff7_party_game_ready());
    disc_available=1; vblank_callback(); CHECK(ff7_party_game_ready());
    CHECK(ff7_party_game_extra_count()==2);
    CHECK(ff7_party_game_guest_id(0x100)==11 && ff7_party_game_guest_id(0x101)==12);
    CHECK(ff7_party_game_extra_guest(2)==255);
    CHECK(ff7_party_game_record(9)==NATIVE_RECORDS+6*132);
    CHECK(ff7_party_game_record(10)==NATIVE_RECORDS+7*132);
    CHECK(ff7_party_game_record(11)!=ff7_party_game_record(12));
    CHECK(ff7_party_game_record(11)!=ff7_party_game_record(10));
    CHECK(ff7_party_game_presentation(11)==10 && ff7_party_game_presentation(12)==10);
    CHECK(ff7_party_game_select(2,0x100));
    CHECK(!ff7_party_game_select(1,0x100));
    CHECK(psx_mod_read_byte(ACTIVE+1)==7);
    CHECK(ff7_party_game_select(1,0x101));
    uint8_t fallback[3]; CHECK(ff7_party_game_fallback(fallback));
    CHECK(fallback[0]==0 && fallback[1]==7 && fallback[2]==255);
    uint32_t a=ff7_party_game_record(11),b=ff7_party_game_record(12);
    CHECK(psx_mod_read_half(a+0x22)==1 && psx_mod_read_byte(a+14)==1);
    CHECK(psx_mod_read_half(b+0x22)==0); /* Profile without a limit policy. */
    psx_mod_write_byte(a+14,3); psx_mod_write_byte(a+15,179);
    psx_mod_write_half(a+0x22,0xda); /* Legacy record missing first-technique bit. */
    psx_mod_write_half(a+0x24,319); psx_mod_write_half(a+0x26,8);
    psx_mod_write_half(a+0x28,7); psx_mod_write_half(a+0x2a,6);
    psx_mod_write_word(a+0x40,0x12345678); /* Distinct materia/AP. */
    psx_mod_write_word(b+0x40,0xabcdef01);
    psx_mod_write_byte(a+0x1c,127); psx_mod_write_byte(b+0x1c,1);
    FF7PartyState state;
    psx_mod_write_byte(0x8009d391u,11);
    psx_mod_write_byte(0x8009d392u,10);
    CHECK(ff7_party_game_snapshot(&state)==FF7_PARTY_OK);
    CHECK(state.stored_known && state.stored[0]==0x100 && state.stored[1]==7 && state.stored_hint[1]==10);
    CHECK(state.active[1]==0x101 && state.active[2]==0x100);
    CHECK(memcmp(original,address(NATIVE_RECORDS),sizeof original)==0);
    uint8_t payload[4096],digest[32]={0}; size_t payload_bytes=0; FF7PartyState decoded;
    CHECK(ff7_party_encode(&state,digest,payload,sizeof payload,&payload_bytes)==FF7_PARTY_OK);
    CHECK(ff7_party_decode(&decoded,digest,payload,payload_bytes)==FF7_PARTY_OK);
    CHECK(!memcmp(decoded.extra[0].record,state.extra[0].record,132));
    CHECK(ff7_party_game_load(&decoded,fallback)==FF7_PARTY_OK);
    CHECK(psx_mod_read_half(a+0x22)==0xdb);
    for(unsigned j=1;j<132;++j)CHECK(psx_mod_read_byte(a+j)==
        (j==0x22 ? (uint8_t)(state.extra[0].record[j]|1) : state.extra[0].record[j]));
    CHECK(!memcmp(address(b)+1,state.extra[1].record+1,131));
    CHECK(memcmp(original,address(NATIVE_RECORDS),sizeof original)==0);
    /* Two physical stores make one active-active PHS swap transaction. */
    psx_mod_write_byte(ACTIVE+1,11); psx_mod_write_byte(ACTIVE+2,12);
    ff7_party_game_observe_active();
    CHECK(ff7_party_game_snapshot(&state)==FF7_PARTY_OK);
    CHECK(state.active[1]==0x100 && state.active[2]==0x101);
    uint8_t exp_before[sizeof expansion],party_before[3];
    memcpy(exp_before,expansion,sizeof expansion); memcpy(party_before,address(ACTIVE),3);
    FF7PartyState bad=state; bad.extra[0].id=0x999; bad.active[1]=0x999;
    CHECK(ff7_party_game_load(&bad,fallback)==FF7_PARTY_INVALID);
    CHECK(!memcmp(exp_before,expansion,sizeof expansion) && !memcmp(party_before,address(ACTIVE),3));
    FF7PartyMember swap=state.extra[0]; state.extra[0]=state.extra[1]; state.extra[1]=swap;
    CHECK(ff7_party_game_load(&state,fallback)==FF7_PARTY_OK);
    CHECK(ff7_party_game_guest_id(0x100)==12 && psx_mod_read_byte(ACTIVE+1)==12);
    CHECK(psx_mod_read_word(ff7_party_game_record(12)+0x40)==0x12345678);
    CHECK(psx_mod_read_byte(ff7_party_game_record(12))==12);
    CHECK(psx_mod_read_byte(0x8009d391u)==12 && psx_mod_read_byte(0x8009d392u)==10);
    /* Framework rewind restores these exact guest regions together. */
    memcpy(expansion,exp_before,sizeof expansion); memcpy(address(ACTIVE),party_before,3);
    psx_mod_write_byte(0x8009d391u,11);
    restore_callback(); CHECK(restores==1);
    CHECK(ff7_party_game_guest_id(0x100)==11 && psx_mod_read_byte(ACTIVE+1)==11);
    CHECK(psx_mod_read_word(ff7_party_game_record(11)+0x40)==0x12345678);
    FF7PartyState sentinel; memset(&sentinel,0x55,sizeof sentinel); state=sentinel;
    psx_mod_write_byte(ACTIVE+1,27);
    CHECK(ff7_party_game_snapshot(&state)==FF7_PARTY_INVALID);
    CHECK(!memcmp(&state,&sentinel,sizeof state));
    memcpy(address(ACTIVE),party_before,3);
    psx_mod_write_byte(ACTIVE+1,255); psx_mod_write_byte(ACTIVE+2,255);
    vblank_callback(); CHECK(ff7_party_game_fallback(fallback));
    CHECK(fallback[0]==0 && fallback[1]==255 && fallback[2]==255);
    memcpy(address(ACTIVE),party_before,3);
    psx_mod_write_word(s_game+H_VERSION,999); vblank_callback();
    CHECK(!ff7_party_game_ready() && psx_mod_read_word(s_game+H_VERSION)==999);
    memcpy(expansion,exp_before,sizeof expansion);
}

static void resident_adapters(void) {
    struct CPUState cpu;
    for (size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i) {
        const ResidentSite* site=&s_sites[i];
        for(unsigned j=0;j<13;++j) psx_mod_write_word(site->pc-24+4*j,site->words[j]);
        for(unsigned guest=0;guest<=12;++guest) {
            memset(&cpu,0,sizeof cpu); cpu.pc=site->pc;
            cpu.gpr[site->reg]=site->action==ALIAS ? 0x800491d0u+4*guest : 33*guest;
            struct CPUState before=cpu;
            party_resident_instruction(&cpu,site->pc);
            if(guest<11) CHECK(!memcmp(&before,&cpu,sizeof cpu));
            else CHECK(cpu.gpr[site->reg]==(site->action==ALIAS ?
                ff7_party_game_alias_word((uint8_t)guest) : ff7_party_game_record_offset((uint8_t)guest)/4));
            CHECK(cpu.pc==before.pc);
        }
        memset(&cpu,0,sizeof cpu); cpu.pc=site->pc;
        cpu.gpr[site->reg]=site->action==ALIAS ? 0x800491d0u+4*11 : 33*11;
        struct CPUState before=cpu;
        psx_mod_write_word(site->pc-24,site->words[0]^1);
        party_resident_instruction(&cpu,site->pc);
        CHECK(!memcmp(&before,&cpu,sizeof cpu));
    }
}

/* Original-disc oracle bridge, using exactly the production callbacks. */
void ff7_test_game_reset(void) {
    memset(ram,0,sizeof ram); memset(expansion,0,sizeof expansion);
    s_profile_count=0; s_activated=0; s_game=0; hook_count=restores=0;
    lifecycle();
}
uint8_t* ff7_test_game_ram(void) { return ram; }
uint8_t* ff7_test_game_expansion(void) { return expansion; }
uint32_t ff7_test_game_record(uint8_t guest) { return ff7_party_game_record(guest); }
void ff7_test_game_hook(uint32_t pc,uint32_t* registers) {
    struct CPUState cpu; memset(&cpu,0,sizeof cpu);
    cpu.pc=pc; memcpy(cpu.gpr,registers,sizeof cpu.gpr);
    party_resident_instruction(&cpu,pc);
    memcpy(registers,cpu.gpr,sizeof cpu.gpr);
}

int main(void) {
    lifecycle(); resident_adapters();
    puts("expanded-party guest lifecycle and resident adapter checks passed");
    return 0;
}
