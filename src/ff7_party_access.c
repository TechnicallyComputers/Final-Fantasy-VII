#include "ff7_party_access.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include "../psx_symbols.h"

#include <string.h>

/* Independently extracted from the owner's NTSC-U SCUS_941.63. The full leaf
 * bodies, including branch/return delay slots, are guarded on every query. */
static const uint32_t s_name_words[] = {
    0x00042080,0x3c018005,0x242191d0,0x00240821,0x8c230000,0x00000000,
    0x00031140,0x00431021,0x00021080,0x3c03800a,0x2463c748,0x03e00008,0x00431021
};
static const uint32_t s_armor_words[] = {
    0x3c01800a,0x2421cbdc,0x00240821,0x90230000,0x340200ff,0x10620015,
    0x00000000,0x00031080,0x3c018005,0x242191d0,0x00220821,0x8c230000,
    0x00000000,0x00031140,0x00431021,0x00021080,0x3c01800a,0x2421c755,
    0x00220821,0x90230000,0x00000000,0x000310c0,0x00431021,0x00021080,
    0x3c038007,0x24631e4d,0x00431021,0x03e00008,0x00000000
};
static const uint32_t s_weapon_words[] = {
    0x3c01800a,0x2421cbdc,0x00240821,0x90230000,0x340200ff,0x10620017,
    0x00000000,0x00031080,0x3c018005,0x242191d0,0x00220821,0x8c230000,
    0x00000000,0x00031140,0x00431021,0x00021080,0x3c01800a,0x2421c754,
    0x00220821,0x90230000,0x00000000,0x00031040,0x00431021,0x00021080,
    0x00431023,0x00021080,0x3c038007,0x246338bc,0x00431021,0x03e00008,0x00000000
};

static const uint32_t NATIVE_RECORDS = 0x8009c738u, NAME_BASE = 0x8009c748u;
static const uint32_t ALIASES = 0x800491d0u, ARMOR_SLOTS = 0x80071e4du, WEAPON_SLOTS = 0x800738bcu;
static uint32_t s_records;
static int s_published;
static FF7PartyState s_state;

static int matches(uint32_t address, const uint32_t* words, size_t count) {
    for (size_t i = 0; i < count; ++i)
        if (psx_mod_read_word(address + (uint32_t)i * 4) != words[i]) return 0;
    return 1;
}

static int guards(void) {
    return matches(PSX_FN_GetCharacterName, s_name_words, sizeof(s_name_words)/4) &&
        matches(PSX_FN_GetPartySlotArmorMateriaSlots, s_armor_words, sizeof(s_armor_words)/4) &&
        matches(PSX_FN_GetPartySlotWeaponMateriaSlots, s_weapon_words, sizeof(s_weapon_words)/4);
}

void ff7_party_access_unpublish(void) {
    s_published = 0;
    memset(&s_state, 0, sizeof(s_state));
}

FF7PartyResult ff7_party_access_publish(const FF7PartyState* state) {
    static const uint8_t zero_digest[32] = {0};
    size_t required = 0;
    /* Reuse the core's complete identity/active-roster validation. */
    if (!s_records || !guards() ||
        ff7_party_encode(state, zero_digest, NULL, 0, &required) != FF7_PARTY_BUFFER_SMALL) {
        psx_mod_counter_add("ff7.party_access.publish_reject", 1);
        return FF7_PARTY_INVALID;
    }
    for (size_t i = 0; i < state->count; ++i)
        for (size_t j = 0; j < FF7_PARTY_RECORD_SIZE; ++j)
            psx_mod_write_byte(s_records + (uint32_t)(i * FF7_PARTY_RECORD_SIZE + j), state->extra[i].record[j]);
    s_state = *state;
    s_published = 1;
    psx_mod_counter_add("ff7.party_access.publish", 1);
    return FF7_PARTY_OK;
}

uint32_t ff7_party_access_record(uint16_t identity) {
    if (!s_records || !s_published || !guards()) return 0;
    if (identity < FF7_PARTY_NATIVE_COUNT)
        return NATIVE_RECORDS + (uint32_t)identity * FF7_PARTY_RECORD_SIZE;
    for (size_t i = 0; i < s_state.count; ++i)
        if (s_state.extra[i].id == identity)
            return s_records + (uint32_t)i * FF7_PARTY_RECORD_SIZE;
    return 0;
}

FF7PartyResult ff7_party_access_snapshot(FF7PartyState* state) {
    FF7PartyState next;
    if (!state || !s_records || !s_published || !guards()) return FF7_PARTY_INVALID;
    next = s_state;
    for (size_t i = 0; i < next.count; ++i)
        for (size_t j = 0; j < FF7_PARTY_RECORD_SIZE; ++j)
            next.extra[i].record[j] = psx_mod_read_byte(s_records + (uint32_t)(i * FF7_PARTY_RECORD_SIZE + j));
    *state = next;
    return FF7_PARTY_OK;
}

static int query_error(struct CPUState* cpu) {
    cpu->gpr[2] = 0;
    psx_mod_counter_add("ff7.party_access.query_reject", 1);
    return 1; /* Never run original array indexing on an invalid extended ID. */
}

static int party_access_query(struct CPUState* cpu, uint32_t address) {
    if (!cpu || cpu->gpr[4] < FF7_PARTY_EXTRA_FIRST) return 0;
    uint32_t identity = cpu->gpr[4];
    uint32_t record = identity < FF7_PARTY_EMPTY ? ff7_party_access_record((uint16_t)identity) : 0;
    if (!record) return query_error(cpu);
    address &= 0x1fffffffu;
    if (address == (PSX_FN_GetCharacterName & 0x1fffffffu)) {
        int terminated = 0;
        for (uint32_t i = 0; i < 12; ++i)
            if (psx_mod_read_byte(record+0x10+i) == 0xff) terminated = 1;
        if (!terminated) return query_error(cpu);
        cpu->gpr[4] = identity * 4;
        cpu->gpr[1] = ALIASES + identity * 4; /* Scratch value only; never dereferenced. */
        cpu->gpr[3] = NAME_BASE;
        cpu->gpr[2] = record + 0x10;
    } else if (address == (PSX_FN_GetPartySlotArmorMateriaSlots & 0x1fffffffu)) {
        uint32_t armor = psx_mod_read_byte(record+0x1d);
        /* Original kernel section7 = 1152 bytes = 32 records * 36. */
        if (armor >= 32) return query_error(cpu);
        cpu->gpr[1] = record + 0x1d;
        cpu->gpr[3] = ARMOR_SLOTS;
        cpu->gpr[2] = ARMOR_SLOTS + armor * 36;
    } else if (address == (PSX_FN_GetPartySlotWeaponMateriaSlots & 0x1fffffffu)) {
        uint32_t weapon = psx_mod_read_byte(record+0x1c);
        /* Original kernel section6 = 5632 bytes = 128 records * 44. */
        if (weapon >= 128) return query_error(cpu);
        cpu->gpr[1] = record + 0x1c;
        cpu->gpr[3] = WEAPON_SLOTS;
        cpu->gpr[2] = WEAPON_SLOTS + weapon * 44;
    } else {
        return 0;
    }
    psx_mod_counter_add("ff7.party_access.query", 1);
    return 1; /* Runtime filter dispatch publishes PC <- ra. */
}

static void party_access_activate(void) {
    ff7_party_access_unpublish();
    s_records = psx_mod_alloc_guest_memory(FF7_PARTY_EXTRA_CAPACITY * FF7_PARTY_RECORD_SIZE, 4);
    psx_mod_counter_add(s_records ? "ff7.party_access.activate" : "ff7.party_access.alloc_reject", 1);
}

static void party_access_restore(void) {
    /* Expansion bytes may rewind, but host roster ownership is not yet part
     * of the game state. Require explicit republish rather than mix eras. */
    ff7_party_access_unpublish();
    psx_mod_counter_add("ff7.party_access.restore_unpublish", 1);
}

PSX_MOD_CONSTRUCTOR(register_ff7_party_access) {
    (void)psx_mod_register_activation_plugin("ff7.party-access", party_access_activate);
    (void)psx_mod_register_savestate_plugin("ff7.party-access", party_access_restore);
    (void)psx_mod_register_function_filter_plugin("ff7.party-access", PSX_FN_GetCharacterName, party_access_query);
    (void)psx_mod_register_function_filter_plugin("ff7.party-access", PSX_FN_GetPartySlotArmorMateriaSlots, party_access_query);
    (void)psx_mod_register_function_filter_plugin("ff7.party-access", PSX_FN_GetPartySlotWeaponMateriaSlots, party_access_query);
}
