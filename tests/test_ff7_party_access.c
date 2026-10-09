/* Tests and optional shared-library oracle bridge; no assets embedded.
 * Compile with -Itests/ff7_party_access_stubs -Isrc -Ipsxrecomp/runtime/include
 * and src/ff7_party.c. The accessor source is included to seed synthetic code
 * signatures; the owner-disc oracle separately verifies every signature byte. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/ff7_party_access.c"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)

static uint8_t s_ram[0x200000], s_expansion[FF7_PARTY_EXTRA_CAPACITY * FF7_PARTY_RECORD_SIZE];
static int s_allocation_fail;
static unsigned s_registrations, s_counter_calls;
static void (*s_activate_callback)(void), (*s_restore_callback)(void);
static PSXModFunctionFilterCallback s_filters[3];
static uint32_t s_addresses[3];

uint8_t psx_mod_read_byte(uint32_t address) {
    uint32_t physical = address & 0x1fffffffu;
    if (physical < sizeof(s_ram)) return s_ram[physical];
    CHECK(physical >= 0x1f000000u && physical-0x1f000000u < sizeof(s_expansion));
    return s_expansion[physical-0x1f000000u];
}
void psx_mod_write_byte(uint32_t address, uint8_t value) {
    uint32_t physical = address & 0x1fffffffu;
    if (physical < sizeof(s_ram)) { s_ram[physical] = value; return; }
    CHECK(physical >= 0x1f000000u && physical-0x1f000000u < sizeof(s_expansion));
    s_expansion[physical-0x1f000000u] = value;
}
uint32_t psx_mod_read_word(uint32_t address) {
    uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) value |= (uint32_t)psx_mod_read_byte(address+i) << (8*i);
    return value;
}
uint32_t psx_mod_alloc_guest_memory(uint32_t size, uint32_t alignment) {
    CHECK(size == sizeof(s_expansion) && alignment == 4);
    memset(s_expansion, 0, sizeof(s_expansion));
    return s_allocation_fail ? 0 : 0x9f000000u;
}
void psx_mod_counter_add(const char* name, uint32_t delta) {
    CHECK(!strncmp(name, "ff7.party_access.", 17) && delta == 1);
    ++s_counter_calls;
}
int psx_mod_register_activation_plugin(const char* id, void (*callback)(void)) {
    CHECK(!strcmp(id, "ff7.party-access")); s_activate_callback = callback; return 0;
}
int psx_mod_register_savestate_plugin(const char* id, void (*callback)(void)) {
    CHECK(!strcmp(id, "ff7.party-access")); s_restore_callback = callback; return 0;
}
int psx_mod_register_function_filter_plugin(const char* id, uint32_t address, PSXModFunctionFilterCallback callback) {
    CHECK(!strcmp(id, "ff7.party-access") && s_registrations < 3);
    s_addresses[s_registrations] = address; s_filters[s_registrations++] = callback; return 0;
}

static void seed(uint32_t address, const uint32_t* words, size_t count) {
    for (size_t i = 0; i < count; ++i)
        for (unsigned byte = 0; byte < 4; ++byte)
            psx_mod_write_byte(address+(uint32_t)i*4+byte, (uint8_t)(words[i] >> (byte*8)));
}

/* These bridge functions are also used by the independent MIPS oracle. */
void ff7_test_access_reset(void) {
    memset(s_ram, 0, sizeof(s_ram));
    s_registrations = 0;
    s_allocation_fail = 0;
    register_ff7_party_access();
    seed(PSX_FN_GetCharacterName, s_name_words, sizeof(s_name_words)/4);
    seed(PSX_FN_GetPartySlotArmorMateriaSlots, s_armor_words, sizeof(s_armor_words)/4);
    seed(PSX_FN_GetPartySlotWeaponMateriaSlots, s_weapon_words, sizeof(s_weapon_words)/4);
    s_activate_callback();
}
int ff7_test_access_publish(const uint8_t* record) {
    FF7PartyState state;
    ff7_party_init(&state);
    if (ff7_party_add_sephiroth(&state, record) != FF7_PARTY_OK) return 0;
    const uint16_t active[] = {0, 7, 0x100};
    if (ff7_party_select(&state, active) != FF7_PARTY_OK) return 0;
    return ff7_party_access_publish(&state) == FF7_PARTY_OK;
}
int ff7_test_access_query(uint32_t address, uint32_t* registers, uint32_t* pc) {
    CPUState cpu;
    memset(&cpu, 0, sizeof(cpu));
    memcpy(cpu.gpr, registers, sizeof(cpu.gpr));
    cpu.pc = *pc;
    int consumed = 0;
    for (unsigned i = 0; i < s_registrations; ++i)
        if ((address & 0x1fffffffu) == (s_addresses[i] & 0x1fffffffu))
            consumed = s_filters[i](&cpu, address);
    if (consumed) cpu.pc = cpu.gpr[31]; /* Runtime filter return contract. */
    memcpy(registers, cpu.gpr, sizeof(cpu.gpr));
    *pc = cpu.pc;
    return consumed;
}

int main(void) {
    uint8_t record[132], native_before[9*132];
    FF7PartyState snapshot, sentinel;
    uint32_t registers[32], before[32], pc;
    memset(record, 0x37, sizeof(record));
    record[0x19] = 0xff; record[0x1c] = 127; record[0x1d] = 6;
    ff7_test_access_reset();
    CHECK(s_registrations == 3 && s_restore_callback);
    CHECK(ff7_party_access_record(0x100) == 0);
    memset(s_ram+0x9c738, 0x6b, sizeof(native_before));
    memcpy(native_before, s_ram+0x9c738, sizeof(native_before));
    CHECK(ff7_test_access_publish(record));
    CHECK(ff7_party_access_record(0) == 0x8009c738u);
    CHECK(ff7_party_access_record(7) == 0x8009c738u+7*132);
    CHECK(ff7_party_access_record(10) == 0);
    CHECK(ff7_party_access_record(0x100) == 0x9f000000u);
    CHECK(!memcmp(native_before, s_ram+0x9c738, sizeof(native_before)));
    for (unsigned i = 0; i < 32; ++i) registers[i] = 0x12340000u+i;
    for (unsigned function = 0; function < 3; ++function) {
        for (unsigned identity = 0; identity < 256; ++identity) {
            registers[4] = identity; memcpy(before, registers, sizeof(before));
            pc = s_addresses[function];
            CHECK(!ff7_test_access_query(pc, registers, &pc));
            CHECK(pc == s_addresses[function] && !memcmp(registers, before, sizeof(before)));
        }
    }
    registers[4] = 0x100; pc = PSX_FN_GetCharacterName;
    CHECK(ff7_test_access_query(pc, registers, &pc));
    CHECK(registers[2] == 0x9f000010u && pc == registers[31]);
    CHECK(registers[4] == 0x400 && registers[1] == 0x800495d0u && registers[3] == 0x8009c748u);
    registers[4] = 0x100; pc = PSX_FN_GetPartySlotArmorMateriaSlots;
    CHECK(ff7_test_access_query(pc, registers, &pc));
    CHECK(registers[2] == 0x80071e4du+6*36 && registers[1] == 0x9f00001du);
    registers[4] = 0x100; pc = PSX_FN_GetPartySlotWeaponMateriaSlots;
    CHECK(ff7_test_access_query(pc, registers, &pc));
    CHECK(registers[2] == 0x800738bcu+127*44 && registers[1] == 0x9f00001cu);
    psx_mod_write_byte(0x9f000060, 0x91); /* A materia byte in independent storage. */
    CHECK(ff7_party_access_snapshot(&snapshot) == FF7_PARTY_OK);
    CHECK(snapshot.extra[0].record[0x60] == 0x91 && snapshot.active[1] == 7 && snapshot.active[2] == 256);
    CHECK(!memcmp(native_before, s_ram+0x9c738, sizeof(native_before)));
    /* Every guard word is significant, not only the first instruction. */
    const size_t lengths[] = {sizeof(s_name_words), sizeof(s_armor_words), sizeof(s_weapon_words)};
    for (unsigned f = 0; f < 3; ++f) {
        for (size_t i = 0; i < lengths[f]; i += 4) {
            uint32_t at = s_addresses[f]+(uint32_t)i;
            uint8_t old = psx_mod_read_byte(at); psx_mod_write_byte(at, old^1);
            registers[4] = 256; memcpy(before, registers, sizeof(before)); pc = PSX_FN_GetCharacterName;
            CHECK(ff7_test_access_query(pc, registers, &pc) && registers[2] == 0);
            before[2] = 0; CHECK(!memcmp(registers, before, sizeof(before)));
            CHECK(ff7_party_access_record(256) == 0);
            psx_mod_write_byte(at, old);
        }
    }
    for (unsigned f = 0; f < 3; ++f) {
        registers[4] = 257; pc = s_addresses[f];
        CHECK(ff7_test_access_query(pc, registers, &pc) && registers[2] == 0);
    }
    psx_mod_write_byte(0x9f00001c, 128); registers[4] = 256; pc = PSX_FN_GetPartySlotWeaponMateriaSlots;
    CHECK(ff7_test_access_query(pc, registers, &pc) && registers[2] == 0);
    psx_mod_write_byte(0x9f00001d, 32); registers[4] = 256; pc = PSX_FN_GetPartySlotArmorMateriaSlots;
    CHECK(ff7_test_access_query(pc, registers, &pc) && registers[2] == 0);
    for (uint32_t i = 0; i < 12; ++i) psx_mod_write_byte(0x9f000010u+i, 0x37);
    registers[4] = 256; pc = PSX_FN_GetCharacterName;
    CHECK(ff7_test_access_query(pc, registers, &pc) && registers[2] == 0); /* No name overread. */
    /* Maximum published roster keeps every record at a distinct address. */
    FF7PartyState full;
    ff7_party_init(&full);
    for (unsigned i = 0; i < 16; ++i)
        CHECK(ff7_party_add(&full, (uint16_t)(256+i), 10, record) == FF7_PARTY_OK);
    CHECK(ff7_party_access_publish(&full) == FF7_PARTY_OK);
    for (unsigned i = 0; i < 16; ++i)
        CHECK(ff7_party_access_record((uint16_t)(256+i)) == 0x9f000000u+i*132);
    CHECK(ff7_party_access_record(272) == 0);
    CHECK(!memcmp(native_before, s_ram+0x9c738, sizeof(native_before)));
    memset(&sentinel, 0x55, sizeof(sentinel)); snapshot = sentinel;
    s_restore_callback();
    CHECK(ff7_party_access_record(256) == 0);
    CHECK(ff7_party_access_snapshot(&snapshot) == FF7_PARTY_INVALID);
    CHECK(!memcmp(&snapshot, &sentinel, sizeof(snapshot)));
    CHECK(ff7_test_access_publish(record));
    s_allocation_fail = 1; s_activate_callback();
    CHECK(!ff7_test_access_publish(record) && ff7_party_access_record(256) == 0);
    CHECK(s_counter_calls > 0);
    puts("ff7_party_access: independent records, guarded extended queries, native pass-through and restore invalidation passed");
    return 0;
}
