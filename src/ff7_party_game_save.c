#include "ff7_party_game_save.h"
#include "ff7_party_game.h"
#include "ff7_party_projection.h"
#include "cpu_state.h"
#include "memcard.h"
#include "mod_plugins.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* A BIOS card write flushes each128-byte sector and reports failures to the
 * game. We therefore accept partial native writes, refresh bindings of other
 * slots, and omit the target's old metadata while a new packet is incomplete.
 * Added-character metadata attaches only when the complete8192-byte packet
 * matches. The framework publishes that base+tail atomically for each flush.
 * Pending packets live in Expansion1 and rewind with RAM/cards. Host caches
 * below are rebuilt from the framework's restored extension, never from a
 * later gameplay state. No filesystem calls occur in this adapter. */
enum { CARDS=2, P_VALID=0, P_SIZE=4, P_NAME=8, P_PACKET=32,
       P_PAYLOAD=P_PACKET+FF7_NATIVE_FILE_BYTES,
       P_BYTES=P_PAYLOAD+FF7_PARTY_PAYLOAD_MAX };
enum Action { PREVIEW_OFFSET, PREPARE, LOADED, FINISHED, NEW_GAME, PREVIEW_READ };
enum { PREVIEW_CACHE=0x801e3864u, PREVIEW_BYTES=84, PREVIEW_PARTY=5 };
typedef struct {uint32_t pc;enum Action action;uint32_t words[13];} SaveSite;
static const SaveSite s_sites[]={
#include "ff7_party_game_save_sites.inc"
};
static uint32_t s_pending;
static FF7PartyCard s_cards[CARDS];
static uint8_t s_ready[CARDS],s_directories[CARDS][15][32];
static const uint8_t ZERO_DIGEST[32]={0};

static uint32_t pending(unsigned card){return s_pending+card*P_BYTES;}
static void read_guest(uint32_t addr,uint8_t* out,unsigned size){
    for(unsigned i=0;i<size;++i)out[i]=psx_mod_read_byte(addr+i);
}
static void write_guest(uint32_t addr,const uint8_t* data,unsigned size){
    for(unsigned i=0;i<size;++i)psx_mod_write_byte(addr+i,data[i]);
}
static uint32_t word(const uint8_t* p){return p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
static int xor_valid(const uint8_t* p){
    unsigned sum=0;for(unsigned i=0;i<128;++i)sum^=p[i];return sum==0;
}
static int allocated(const uint8_t* base,unsigned slot){
    const uint8_t* p=base+slot*128;
    return slot>=1 && slot<=15 && word(p)==0x51 && word(p+4)==8192 &&
        p[8]==255 && p[9]==255 && xor_valid(p);
}
static int filename(uint32_t addr,uint8_t name[20]){
    uint8_t prefix[5];read_guest(addr,prefix,5);
    if(prefix[0]!='b'||prefix[1]!='u'||prefix[3]!='0'||prefix[4]!=':'||
       (prefix[2]!='0'&&prefix[2]!='1'))return -1;
    memset(name,0,20);
    unsigned i;
    for(i=0;i<20;++i){
        uint8_t c=psx_mod_read_byte(addr+5+i);
        if(!c)break;
        if(c<32 || c>=127 || c=='/' || c=='\\')return -1;
        name[i]=c;
    }
    if(!i || (i==20 && psx_mod_read_byte(addr+25)))return -1;
    return prefix[2]-'0';
}
static unsigned find_slot(const uint8_t* base,const uint8_t name[20]){
    unsigned found=0;
    for(unsigned slot=1;slot<=15;++slot)
        if(allocated(base,slot) && !memcmp(base+slot*128+10,name,20)){
            if(found)return 0; /* Ambiguous directory: no guessing. */
            found=slot;
        }
    return found;
}
static int codec_load(int card,const uint8_t* base,const uint8_t* tail,uint32_t bytes){
    if(card<0||card>=CARDS)return -1;
    s_ready[card]=0;memset(&s_cards[card],0,sizeof s_cards[card]);
    memset(s_directories[card],0,sizeof s_directories[card]);
    if(ff7_party_card_decode(&s_cards[card],base,FF7_PARTY_CARD_BYTES,tail,bytes)!=FF7_PARTY_OK){
        psx_mod_counter_add("ff7.party_game_save.load_reject",1);return -1;
    }
    for(unsigned i=0;i<s_cards[card].count;++i){
        unsigned slot=s_cards[card].slots[i].directory_slot;
        memcpy(s_directories[card][slot-1],base+slot*128,32);
    }
    s_ready[card]=1;
    psx_mod_counter_add("ff7.party_game_save.card_loaded",1);return 0;
}
static void remove_slot(FF7PartyCard* card,unsigned slot){
    for(unsigned i=0;i<card->count;++i)if(card->slots[i].directory_slot==slot){
        memmove(card->slots+i,card->slots+i+1,(card->count-i-1)*sizeof card->slots[0]);
        --card->count;return;
    }
}
static int codec_store(int card,const uint8_t* base,uint8_t* tail,uint32_t capacity){
    if(card<0||card>=CARDS||!s_ready[card]||!base)return -1;
    if(base[0]!='M'||base[1]!='C'||!xor_valid(base))return -1;
    FF7PartyCard next=s_cards[card];
    for(unsigned i=0;i<next.count;){
        unsigned slot=next.slots[i].directory_slot;
        if(!allocated(base,slot) || memcmp(s_directories[card][slot-1],base+slot*128,32))
            remove_slot(&next,slot);
        else ++i;
    }
    uint32_t p=pending((unsigned)card);
    if(s_pending && psx_mod_read_word(p+P_VALID)==1){
        uint8_t name[20];read_guest(p+P_NAME,name,20);
        unsigned slot=find_slot(base,name);
        if(slot){
            uint8_t packet[FF7_NATIVE_FILE_BYTES];read_guest(p+P_PACKET,packet,sizeof packet);
            remove_slot(&next,slot);
            if(!memcmp(base+slot*8192,packet,sizeof packet)){
                uint32_t size=psx_mod_read_word(p+P_SIZE);
                uint8_t payload[FF7_PARTY_PAYLOAD_MAX];
                FF7PartyState party;
                if(size>sizeof payload)return -1;
                read_guest(p+P_PAYLOAD,payload,size);
                if(ff7_party_decode(&party,ZERO_DIGEST,payload,size)!=FF7_PARTY_OK)return -1;
                if(next.count>=15)return -1;
                unsigned at=0;
                while(at<next.count && next.slots[at].directory_slot<slot)++at;
                memmove(next.slots+at+1,next.slots+at,(next.count-at)*sizeof next.slots[0]);
                next.slots[at].directory_slot=(uint8_t)slot;next.slots[at].party=party;++next.count;
                psx_mod_counter_add("ff7.party_game_save.packet_complete",1);
            }
        }
    }
    size_t bytes=0;
    if(next.count && ff7_party_card_encode(&next,base,FF7_PARTY_CARD_BYTES,tail,capacity,&bytes)!=FF7_PARTY_OK)
        return -1;
    /* Callback publication may fail after this cache update. The pending
     * packet remains retryable; rewind restores both tail and guest packet. */
    s_cards[card]=next;memset(s_directories[card],0,sizeof s_directories[card]);
    for(unsigned i=0;i<next.count;++i){
        unsigned slot=next.slots[i].directory_slot;
        memcpy(s_directories[card][slot-1],base+slot*128,32);
    }
    return (int)bytes;
}
static int prepare(uint32_t path){
    FF7PartyState party;
    uint8_t name[20],fallback[3],packet[FF7_NATIVE_FILE_BYTES],payload[FF7_PARTY_PAYLOAD_MAX];
    size_t size=0;
    int card=filename(path,name);
    if(card<0||!s_pending||!ff7_party_game_fallback(fallback)||
       ff7_party_game_snapshot(&party)!=FF7_PARTY_OK)return 0;
    read_guest(0x801e6f38u,packet,sizeof packet);
    if(packet[0]!='S'||packet[1]!='C'||packet[3]!=1 ||
       !ff7_native_save_valid(packet+512,FF7_NATIVE_SAVE_BYTES) ||
       !ff7_native_save_project(packet+512,FF7_NATIVE_SAVE_BYTES,fallback) ||
       ff7_party_encode(&party,ZERO_DIGEST,payload,sizeof payload,&size)!=FF7_PARTY_OK)return 0;
    uint32_t p=pending((unsigned)card);
    psx_mod_write_word(p+P_VALID,0);
    write_guest(p+P_NAME,name,20);write_guest(p+P_PACKET,packet,sizeof packet);
    write_guest(p+P_PAYLOAD,payload,(unsigned)size);psx_mod_write_word(p+P_SIZE,(uint32_t)size);
    write_guest(0x801e6f38u,packet,sizeof packet);
    psx_mod_write_word(p+P_VALID,1);
    psx_mod_counter_add("ff7.party_game_save.prepare",1);return 1;
}
static void loaded(uint32_t path){
    uint8_t name[20],fallback[3];
    int card=filename(path,name);
    if(card<0)return;
    for(unsigned i=0;i<3;++i)fallback[i]=psx_mod_read_byte(0x8009cbdcu+i);
    /* Lookup against current card RAM, not a remembered menu row or filename.
     * The original read must have returned success and the entire native file
     * must still match the bytes just loaded by SAVEMENU. */
    uint8_t base[FF7_PARTY_CARD_BYTES];
    if(memcard_export_raw(card,base)!=0)return;
    unsigned slot=find_slot(base,name);
    if(!slot)return;
    uint8_t packet[FF7_NATIVE_FILE_BYTES];read_guest(0x801e6f38u,packet,sizeof packet);
    if(memcmp(base+slot*8192,packet,sizeof packet) ||
       !ff7_native_save_valid(packet+512,FF7_NATIVE_SAVE_BYTES))return;
    if(s_ready[card])for(unsigned i=0;i<s_cards[card].count;++i)
        if(s_cards[card].slots[i].directory_slot==slot){
            if(ff7_party_game_load(&s_cards[card].slots[i].party,fallback)==FF7_PARTY_OK){
                psx_mod_counter_add("ff7.party_game_save.restore_party",1);return;
            }
            psx_mod_counter_add("ff7.party_game_save.profile_unavailable",1);break;
        }
    /* Loading an ordinary slot must discard progress from a previous game.
     * Unknown installed profiles also retain the safe native fallback. */
    if(ff7_party_game_initialize(fallback))psx_mod_counter_add("ff7.party_game_save.native_load",1);
}
/* The file list caches each save's native header, whose party bytes hold the
 * standard-card fallback for an extended slot. Restore only the positions the
 * bound metadata assigns to registered extras; the original portrait seams
 * draw their guest handles. Native positions and the card stay untouched. */
static void preview_read(uint32_t path,unsigned selector){
    uint8_t name[20];
    int card=filename(path,name);
    if(card<0||(unsigned)card!=((selector>>4)&1u)||!s_ready[card])return;
    uint8_t base[FF7_PARTY_CARD_BYTES];
    if(memcard_export_raw(card,base)!=0)return;
    unsigned slot=find_slot(base,name);
    if(!slot||memcmp(s_directories[card][slot-1],base+slot*128,32))return;
    for(unsigned i=0;i<s_cards[card].count;++i){
        if(s_cards[card].slots[i].directory_slot!=slot)continue;
        const FF7PartyState* party=&s_cards[card].slots[i].party;
        uint8_t guest[3];
        int extra=0;
        for(unsigned j=0;j<3;++j){
            uint16_t id=party->active[j];
            guest[j]=255;
            if(id<FF7_PARTY_EXTRA_FIRST||id==FF7_PARTY_EMPTY)continue;
            guest[j]=ff7_party_game_guest_id(id);
            if(guest[j]==FF7_PARTY_GUEST_EMPTY)return; /* Profile unavailable: keep native. */
            extra=1;
        }
        if(!extra)return;
        uint32_t entry=PREVIEW_CACHE+(selector&15u)*PREVIEW_BYTES+PREVIEW_PARTY;
        for(unsigned j=0;j<3;++j)if(guest[j]!=255)psx_mod_write_byte(entry+j,guest[j]);
        psx_mod_counter_add("ff7.party_game_save.preview_party",1);
        return;
    }
}
static void instruction(CPUState* cpu,uint32_t pc){
    if(!cpu||!s_pending||!ff7_party_game_ready())return;
    pc=(pc&0x1fffffffu)|0x80000000u;
    for(unsigned i=0;i<sizeof s_sites/sizeof s_sites[0];++i){
        const SaveSite* site=s_sites+i;
        if(site->pc!=pc)continue;
        int match=1;
        for(unsigned j=0;j<13;++j)if(psx_mod_read_word(pc-24+4*j)!=site->words[j]){match=0;break;}
        if(!match)return;
        switch(site->action){
        case PREVIEW_OFFSET:{
            uint32_t value=cpu->gpr[16];
            if(value%33==0 && value/33<=255 && ff7_party_game_is_extra((uint8_t)(value/33)))
                cpu->gpr[16]=ff7_party_game_record_offset((uint8_t)(value/33))>>2;
            break;}
        case PREPARE:
            if(!prepare(cpu->gpr[19])){
                /* Original BIOS open of an empty filename fails. Its normal
                 * error path unwinds this function; no private IDs reach disk.
                 * Instruction callbacks never redirect PC or run guest code. */
                cpu->gpr[19]=s_pending+CARDS*P_BYTES;
                psx_mod_counter_add("ff7.party_game_save.prepare_reject",1);
            }
            break;
        case LOADED:
            /* Success-only caller branch, after the original native CRC check.
             * 1F40's filename was at callee SP+38, caller SP-30. The only
             * intervening call is the stackless checksum leaf1950. Restore
             * extras here before the success sound call can reuse that stack.
             * Restoring at2134 changes CBDC/CAD before CRC and rejects saves. */
            loaded(cpu->gpr[29]-0x30);break;
        case FINISHED:{
            uint8_t name[20];int card=filename(cpu->gpr[19],name);
            if(card>=0)psx_mod_write_word(pending((unsigned)card)+P_VALID,0);
            break;}
        case PREVIEW_READ:
            /* 1D40 frame: filename at SP+0x38, selector in s2. */
            preview_read(cpu->gpr[29]+0x38,cpu->gpr[18]);break;
        case NEW_GAME:{
            uint8_t native[3];read_guest(0x8009cbdcu,native,3);
            if(ff7_party_game_initialize(native))
                psx_mod_counter_add("ff7.party_game_save.new_game",1);
            break;}
        }
        return;
    }
}
int ff7_party_game_save_init(void){
    s_pending=psx_mod_alloc_guest_memory(CARDS*P_BYTES+4,4);
    if(!s_pending)return 0;
    memset(s_cards,0,sizeof s_cards);memset(s_ready,0,sizeof s_ready);
    memset(s_directories,0,sizeof s_directories);
    for(unsigned i=0;i<CARDS;++i)psx_mod_write_word(pending(i)+P_VALID,0);
    psx_mod_write_word(s_pending+CARDS*P_BYTES,0);
    memcard_set_extension_codec(codec_load,codec_store);
    return 1;
}
void ff7_party_game_save_restore(void){
    /* Framework reload callback reconstructs host card caches from snapshot;
     * pending bytes are already part of restored guest enhancement memory. */
}
PSX_MOD_CONSTRUCTOR(register_ff7_party_game_save){
    for(unsigned i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
        (void)psx_mod_register_instruction_plugin("ff7.party-gameplay",s_sites[i].pc,
            s_sites[i].words[6],instruction);
}
