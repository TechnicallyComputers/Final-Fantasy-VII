#include "ff7_party_menu.h"
#include "ff7_party_game.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include "gpu.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Original NTSC-U menus, independently inspected on all three owner discs.
 * Instruction hooks do not call guest functions: branch/load delay state is
 * still live. Every hook has a thirteen-word original-code context guard.
 */
enum Menu { MENU_FORMMENU, MENU_EQIPMENU, MENU_STATMENU, MENU_ITEMMENU, MENU_MGICMENU };
enum Action { OFFSET, ALIAS, PORTRAIT, PORTRAIT_ALIAS, PHS_READY, PHS_CLOSE,
              PHS_SWAP, ELIGIBILITY, LIST_BASE, LIST_CLEAR, LIST_FILL, LIST_APPEND,
              ITEM_LIMIT_MESSAGE, STORY_SCAN_RECORD, STORY_REMOVE_RECORD,
              STORY_MASK, STORY_MORE, STORY_RETURN_RECORD, STORY_RETURN_MASK,
              STORY_RETURN_NEXT };
typedef struct { uint32_t pc; enum Menu menu; enum Action action; unsigned reg;
                 uint32_t words[13]; } MenuSite;
static const MenuSite s_sites[] = {
#include "ff7_party_menu_sites.inc"
};

enum { EXTRA_CAPACITY = 16, PORTRAIT_CELL = 9, STORAGE_SIZE = 4096,
       FLAG = 0, ALIAS_WORD = 4, PORTRAIT_WORD = 68, EXCHANGE = 144,
       PORTRAIT_EXTENTS = 176,
       ITEM_NOTICE = 200,
       PALETTE_BACKUP = 256, IMAGE_BACKUP = 768 };
static const uint32_t NATIVE = 0x8009c738u, ACTIVE = 0x8009cbdcu;
static const uint32_t ALIAS_TABLE = 0x800491d0u, RESERVE = 0x801d3424u;
static const uint32_t BACKUP_MAGIC = 0x50485339u;
static uint32_t s_storage;
static uint8_t s_portrait[2848];
static int s_portrait_valid;
static unsigned extra_count(void) {
    unsigned count=ff7_party_game_extra_count();
    return count<EXTRA_CAPACITY ? count : EXTRA_CAPACITY;
}
static int portrait_cell(uint8_t guest) {
    unsigned presentation=ff7_party_game_presentation(guest);
    if (presentation<9) return (int)presentation;
    const FF7PartyProfile* p=ff7_party_game_profile(guest);
    /* One spare atlas cell. Other new portrait assets require paging/banking;
     * do not draw an unrelated portrait when a future profile lacks a cell. */
    return p && p->portrait && strcmp(p->portrait,"MENU/PCEFI.TIM")==0 ? PORTRAIT_CELL : -1;
}

static uint32_t crc32(const uint8_t* bytes, size_t length) {
    uint32_t crc = ~0u;
    for (size_t i=0; i<length; ++i) {
        crc ^= bytes[i];
        for (unsigned b=0; b<8; ++b) crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u);
    }
    return ~crc;
}
static int matches(const MenuSite* site) {
    for (unsigned i=0; i<13; ++i)
        if (psx_mod_read_word(site->pc-24+4*i)!=site->words[i]) return 0;
    return 1;
}

/* Same synchronous GP0 image transfer used by the runtime's PsyQ service, but
 * sourced from host TIM bytes or enhancement memory (that service only accepts
 * main RAM). Stock LoadNinePortraits has finished its transfers at PHS_READY.
 * All writes retain GPU command ordering; no guest CPU reentry occurs here.
 */
static void upload(unsigned x, unsigned y, unsigned w, unsigned h,
                   const uint8_t* bytes, uint32_t guest) {
    gpu_write_gp1(0x04000000u);
    gpu_write_gp0(0x01000000u);
    gpu_write_gp0(0xa0000000u);
    gpu_write_gp0(x|(y<<16));
    gpu_write_gp0(w|(h<<16));
    for (unsigned i=0; i<w*h/2; ++i) {
        uint32_t word;
        if (bytes) {
            const uint8_t* p=bytes+4*i;
            word=(uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
        } else word=psx_mod_read_word(guest+4*i);
        gpu_write_gp0(word);
    }
    gpu_write_gp1(0x04000002u);
}
static void backup(unsigned x, unsigned y, unsigned w, unsigned h, uint32_t guest) {
    for (unsigned row=0; row<h; ++row)
        for (unsigned col=0; col<w; ++col)
            psx_mod_write_half(guest+2*(row*w+col), gpu_vram_peek((int)(x+col),(int)(y+row)));
}
static int load_portrait(const FF7PartyProfile* p) {
    uint32_t bytes=0;
    if (!s_portrait_valid) {
        if (!psx_mod_read_disc_file(p->portrait,s_portrait,sizeof s_portrait,&bytes) ||
            bytes!=sizeof s_portrait || crc32(s_portrait,bytes)!=0x6800bc48u) {
            psx_mod_counter_add("ff7.party_menu.portrait_reject",1);
            return 0;
        }
        /* Exact original TIM: 8bpp, 256x1 CLUT at file20, 24x48 image at544. */
        s_portrait_valid=1;
    }
    return 1;
}
static int prepare_portrait(const FF7PartyProfile* p) {
    if(!load_portrait(p))return 0;
    if (psx_mod_read_word(s_storage+FLAG)!=BACKUP_MAGIC) {
        backup(384,9,256,1,s_storage+PALETTE_BACKUP);
        backup(856,448,24,48,s_storage+IMAGE_BACKUP);
        psx_mod_write_word(s_storage+FLAG,BACKUP_MAGIC);
    }
    upload(384,9,256,1,s_portrait+20,0);
    upload(856,448,24,48,s_portrait+544,0);
    return 1;
}
static void close_portrait(void) {
    if (psx_mod_read_word(s_storage+FLAG)!=BACKUP_MAGIC) return;
    upload(384,9,256,1,NULL,s_storage+PALETTE_BACKUP);
    upload(856,448,24,48,NULL,s_storage+IMAGE_BACKUP);
    psx_mod_write_word(s_storage+FLAG,0);
}
int ff7_party_menu_prepare_portrait(uint8_t guest) {
    if(!s_storage || !ff7_party_game_is_extra(guest))return -1;
    int cell=portrait_cell(guest);
    const FF7PartyProfile* p=ff7_party_game_profile(guest);
    if(cell==PORTRAIT_CELL && (!p || !prepare_portrait(p)))return -1;
    return cell;
}
uint32_t ff7_party_menu_portrait_extent(uint8_t guest,unsigned slot) {
    if(!s_storage || slot>=3 || !ff7_party_game_is_extra(guest) ||
       portrait_cell(guest)!=PORTRAIT_CELL)return 0;
    const FF7PartyProfile* p=ff7_party_game_profile(guest);
    uint32_t lba,size;
    if(!p || !load_portrait(p) ||
       !psx_mod_disc_file_extent(p->portrait,&lba,&size) || size!=sizeof s_portrait){
        psx_mod_counter_add("ff7.party_menu.portrait_extent_reject",1);return 0;
    }
    uint32_t extent=s_storage+PORTRAIT_EXTENTS+slot*8;
    psx_mod_write_word(extent,lba);psx_mod_write_word(extent+4,(size+2047u)&~2047u);
    return extent;
}
static void append_reserve(void) {
    for (unsigned e=0;e<extra_count();++e) {
        uint8_t guest=ff7_party_game_extra_guest(e);
        int present=0, cell=portrait_cell(guest);
        const FF7PartyProfile* p=ff7_party_game_profile(guest);
        if (!ff7_party_game_record(guest) || cell<0 || (cell==PORTRAIT_CELL && !prepare_portrait(p))) continue;
        for (unsigned i=0;i<3;++i) present|=psx_mod_read_byte(ACTIVE+i)==guest;
        for (unsigned i=0;i<9;++i) present|=psx_mod_read_byte(RESERVE+i)==guest;
        if (present) continue;
        for (unsigned i=0;i<9;++i) if (psx_mod_read_byte(RESERVE+i)==255) {
            psx_mod_write_byte(RESERVE+i,guest);
            psx_mod_counter_add("ff7.party_menu.phs_append",1);
            present=1;
            break;
        }
        if (!present) psx_mod_counter_add("ff7.party_menu.phs_capacity_reject",1);
    }
}

static uint32_t story_record(unsigned extra) {
    if(extra>=extra_count())return 0;
    uint32_t p=ff7_party_game_record(ff7_party_game_extra_guest(extra));
    return (p&3u)?0:p;
}
static void apply_site(struct CPUState* cpu, const MenuSite* site) {
    if(site->action>=STORY_SCAN_RECORD){
        /* Bounds and pointer routing are one transaction: never extend a
         * native loop if a neighboring required adapter cannot match. */
        for(size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i)
            if(s_sites[i].action>=STORY_SCAN_RECORD && !matches(&s_sites[i]))return;
    }
    switch (site->action) {
    case OFFSET:
        /* Before SLL r,r,2, r==33*guest identifies this record arithmetic.
         * The replacement is an unsigned modulo-2^32 base-relative offset;
         * the unchanged following ADDU produces the expansion record address.
         * Keeping the original base is essential: materia exchange uses it
         * for native characters and Sephiroth within the same frame.
         */
        for (unsigned e=0;e<extra_count();++e) {
            uint8_t guest=ff7_party_game_extra_guest(e);
            uint32_t record=ff7_party_game_record(guest);
            if (record && !(record&3u) && cpu->gpr[site->reg]==33u*guest) {
                cpu->gpr[site->reg]=(record-NATIVE)>>2;
                break;
            }
        }
        break;
    case ALIAS:
    case PORTRAIT_ALIAS:
        for (unsigned e=0;e<extra_count();++e) {
            uint8_t guest=ff7_party_game_extra_guest(e);
            int cell=portrait_cell(guest);
            if (ff7_party_game_record(guest) && cpu->gpr[site->reg]==ALIAS_TABLE+4u*guest) {
                if (site->action==PORTRAIT_ALIAS && cell<0) break;
                uint32_t word=s_storage+(site->action==ALIAS ? ALIAS_WORD : PORTRAIT_WORD)+4*e;
                psx_mod_write_word(word,site->action==ALIAS ? guest : (uint32_t)cell);
                cpu->gpr[site->reg]=word;
                break;
            }
        }
        break;
    case PORTRAIT:
        if (cpu->gpr[site->reg]<=255 && ff7_party_game_is_extra((uint8_t)cpu->gpr[site->reg])) {
            int cell=portrait_cell((uint8_t)cpu->gpr[site->reg]);
            if (cell>=0) cpu->gpr[site->reg]=(uint32_t)cell;
        }
        break;
    case ELIGIBILITY:
        /* Original equipment inventory and count transactions stay intact.
         * Masamune uses Sephiroth bit10; armor/accessory use Cloud's bit0.
         * This is a compatibility policy, never an identity/record alias.
         */
        if (cpu->gpr[3]<=255 && ff7_party_game_is_extra((uint8_t)cpu->gpr[3])) {
            uint8_t guest=(uint8_t)cpu->gpr[3];
            const FF7PartyProfile* p=ff7_party_game_profile(guest);
            if (p) cpu->gpr[3]=site->reg==10 ? p->weapon_compatibility :
                (site->pc==0x801d046cu ? p->armor_compatibility : p->accessory_compatibility);
            else if (ff7_party_game_presentation(guest)<9)
                cpu->gpr[3]=ff7_party_game_presentation(guest);
        }
        break;
    case PHS_READY: append_reserve(); break;
    case PHS_CLOSE: close_portrait(); break;
    case PHS_SWAP:
        /* This instruction is also the three-slot recalculation loop head. */
        if (cpu->gpr[16]==0) ff7_party_game_observe_active();
        break;
    case LIST_CLEAR:
        for (unsigned i=0;i<32;++i) psx_mod_write_byte(s_storage+EXCHANGE+i,255);
        cpu->gpr[2]=s_storage+EXCHANGE+8;
        break;
    case LIST_FILL:
        if (cpu->gpr[4]==0x801df6ecu) cpu->gpr[4]=s_storage+EXCHANGE;
        break;
    case LIST_BASE: cpu->gpr[site->reg]=s_storage+EXCHANGE; break;
    case LIST_APPEND:
        if (cpu->gpr[8]<=9) {
            for (unsigned e=0;e<extra_count();++e) {
                uint8_t guest=ff7_party_game_extra_guest(e);
                if (!ff7_party_game_record(guest)) continue;
                psx_mod_write_byte(s_storage+EXCHANGE+cpu->gpr[8],guest);
                ++cpu->gpr[8];
            }
        }
        break;
    case ITEM_LIMIT_MESSAGE:
        /* Retail refusal text is indexed by raw native identity. An added
         * identity cannot index that fixed message table. Keep item rejection
         * and inventory unchanged, but supply bounded mod-authored text. */
        if(cpu->gpr[4]<=255 && ff7_party_game_is_extra((uint8_t)cpu->gpr[4]))
            cpu->gpr[3]=s_storage+ITEM_NOTICE-cpu->gpr[2];
        break;
    case STORY_SCAN_RECORD:
    case STORY_REMOVE_RECORD:{
        /* Wutai mode15: native0..8 retain availability/order; registered
         * independent records follow, then the original200-entry inventory.
         * Rank selection,48-entry storage and exact AP-word removal stay MIPS. */
        uint32_t p=story_record(cpu->gpr[site->reg]-9u);
        if(p){
            unsigned weapon=site->action==STORY_SCAN_RECORD?19:7;
            unsigned armor=site->action==STORY_SCAN_RECORD?20:8;
            cpu->gpr[weapon]=p+0x40;cpu->gpr[armor]=p+0x60;
        }
        break;}
    case STORY_MASK:
        if(cpu->gpr[site->reg]>=9)
            cpu->gpr[2]=story_record(cpu->gpr[site->reg]-9u)?1:0;
        break;
    case STORY_MORE:
        if(cpu->gpr[site->reg]>=9)
            cpu->gpr[2]=cpu->gpr[site->reg]<9+extra_count();
        break;
    case STORY_RETURN_RECORD:{
        /* Mode16 still tries native8..0 first. Negative t1 values -2,-3,...
         * enumerate extras afterward without expanding the native bitmask.
         * t0 remains the record-relative gear offset, t3/t4 materia pointers. */
        uint32_t p=story_record(~cpu->gpr[9]-1u);
        if(p){cpu->gpr[8]=p-NATIVE;cpu->gpr[11]=p+0x40;cpu->gpr[12]=p+0x60;}
        break;}
    case STORY_RETURN_MASK:
        if(cpu->gpr[9]&0x80000000u)cpu->gpr[2]=story_record(~cpu->gpr[9]-1u)?1:0;
        break;
    case STORY_RETURN_NEXT:
        /* Before native t1--/BNE t1,-1. All progress remains in snapshot-owned
         * guest registers; success can return early without host iterator state. */
        if(cpu->gpr[9]==0 && extra_count())cpu->gpr[9]=~0u;
        else if((cpu->gpr[9]&0x80000000u) && ~cpu->gpr[9]==extra_count())cpu->gpr[9]=0;
        break;
    }
}
static void menu_instruction(struct CPUState* cpu,uint32_t address) {
    if (!cpu || !s_storage) return;
    address=(address&0x1fffffffu)|0x80000000u;
    for (size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i) {
        const MenuSite* site=&s_sites[i];
        if (site->pc==address && matches(site)) {
            apply_site(cpu,site);
            psx_mod_counter_add("ff7.party_menu.hook",1);
            return;
        }
    }
    psx_mod_counter_add("ff7.party_menu.context_reject",1);
}
int ff7_party_menu_init(void) {
    s_portrait_valid=0;
    s_storage=psx_mod_alloc_guest_memory(STORAGE_SIZE,4);
    if (!s_storage) return 0;
    psx_mod_write_word(s_storage+FLAG,0);
    for (unsigned i=0;i<32;++i) psx_mod_write_byte(s_storage+EXCHANGE+i,255);
    static const char notice[]="Cannot use this item.";
    for(unsigned i=0;i<sizeof notice;++i)
        psx_mod_write_byte(s_storage+ITEM_NOTICE+i,notice[i]?(uint8_t)(notice[i]-32):255);
    return 1;
}
void ff7_party_menu_restore(void) {
    /* Guest allocation and GPU state rewind together. Backups and presence
     * marker are guest bytes, so a restored active PHS retains its real prior
     * palette/image. This does not provide the bridge's full save lifecycle. */
    s_portrait_valid=0;
}
PSX_MOD_CONSTRUCTOR(register_ff7_party_menu) {
    for (size_t i=0;i<sizeof s_sites/sizeof s_sites[0];++i) {
        /* Several overlays can share the address and opcode. One dispatcher
         * registration checks every context; never register it twice. */
        int registered=0;
        for(size_t j=0;j<i;++j)
            if(s_sites[j].pc==s_sites[i].pc && s_sites[j].words[6]==s_sites[i].words[6])registered=1;
        if(registered)continue;
        (void)psx_mod_register_instruction_plugin("ff7.party-gameplay",s_sites[i].pc,
                                                s_sites[i].words[6],menu_instruction);
    }
}
