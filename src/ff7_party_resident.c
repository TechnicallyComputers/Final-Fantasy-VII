#include "ff7_party_game.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include <stddef.h>

enum ResidentAction { OFFSET, ALIAS };
typedef struct {
    uint32_t pc;
    enum ResidentAction action;
    unsigned reg;
    uint32_t words[13];
} ResidentSite;
static const ResidentSite s_sites[] = {
#include "ff7_party_resident_sites.inc"
};

static void party_resident_instruction(struct CPUState* cpu, uint32_t address) {
    if (!cpu || !ff7_party_game_ready()) return;
    address = (address & 0x1fffffffu) | 0x80000000u;
    const ResidentSite* site = NULL;
    for (size_t i = 0; i < sizeof(s_sites)/sizeof(s_sites[0]); ++i)
        if (s_sites[i].pc == address) { site = &s_sites[i]; break; }
    if (!site) return;
    for (unsigned i = 0; i < 13; ++i)
        if (psx_mod_read_word(address-24+4*i) != site->words[i]) {
            psx_mod_counter_add("ff7.party_resident.guard_reject",1); return;
        }
    if (site->action == ALIAS) {
        uint32_t pointer = cpu->gpr[site->reg];
        uint32_t offset = pointer - 0x800491d0u;
        if (offset & 3u || offset/4 > 255 || !ff7_party_game_is_extra((uint8_t)(offset/4))) return;
        uint32_t scratch = ff7_party_game_alias_word((uint8_t)(offset/4));
        if (!scratch) return;
        cpu->gpr[site->reg] = scratch;
        psx_mod_counter_add("ff7.party_resident.alias",1);
    } else {
        uint32_t input = cpu->gpr[site->reg];
        for (unsigned i = 0; i < ff7_party_game_extra_count(); ++i) {
            uint8_t guest = ff7_party_game_extra_guest(i);
            if (input != (uint32_t)guest*33) continue;
            cpu->gpr[site->reg] = ff7_party_game_record_offset(guest)/4;
            psx_mod_counter_add("ff7.party_resident.record",1);
            break;
        }
    }
}

PSX_MOD_CONSTRUCTOR(register_ff7_party_resident) {
    for (size_t i = 0; i < sizeof(s_sites)/sizeof(s_sites[0]); ++i)
        (void)psx_mod_register_instruction_plugin("ff7.party-gameplay",s_sites[i].pc,
            s_sites[i].words[6],party_resident_instruction);
}
