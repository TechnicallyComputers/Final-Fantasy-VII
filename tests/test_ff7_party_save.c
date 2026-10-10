/* Standalone adapter test: compile this, ff7_party.c and ff7_party_save.c with
 * -Itests/ff7_party_save_stubs -Isrc. No runtime, real saves, or game assets. */
#include "ff7_party.h"
#include "memcard.h"
#include "mod_plugins.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); exit(1); \
} } while (0)

static MemcardExtensionLoad s_load;
static MemcardExtensionSave s_save;
static void (*s_activate)(void);
static unsigned s_loads, s_saves, s_rejects, s_directory_changes;

void memcard_set_extension_codec(MemcardExtensionLoad load, MemcardExtensionSave save) {
    s_load = load;
    s_save = save;
}

int psx_mod_register_activation_plugin(const char* id, void (*callback)(void)) {
    CHECK(!strcmp(id, "ff7.party-save"));
    CHECK(!s_activate);
    s_activate = callback;
    return 0;
}

void psx_mod_counter_add(const char* name, uint32_t delta) {
    CHECK(delta == 1);
    if (!strcmp(name, "ff7.party_save.load")) s_loads += delta;
    if (!strcmp(name, "ff7.party_save.save")) s_saves += delta;
    if (!strcmp(name, "ff7.party_save.reject")) s_rejects += delta;
    if (!strcmp(name, "ff7.party_save.directory_changed")) s_directory_changes += delta;
}

void register_ff7_party_save(void);

static void frame_crc(uint8_t* frame) {
    uint8_t checksum = 0;
    for (unsigned i = 0; i < 127; ++i) checksum ^= frame[i];
    frame[127] = checksum;
}

static size_t fixture(uint8_t* base, uint8_t* tail, uint8_t marker) {
    FF7PartyCard card;
    uint8_t record[132];
    size_t written;
    memset(base, 0, FF7_PARTY_CARD_BYTES);
    memcpy(base, "MC", 2); frame_crc(base);
    base[128] = 0x51;
    base[128+5] = 0x20;
    base[128+8] = base[128+9] = 0xff;
    memcpy(base+128+10, "FF7TEST", 7);
    frame_crc(base+128);
    memset(&card, 0, sizeof(card));
    card.count = 1;
    card.slots[0].directory_slot = 1;
    ff7_party_init(&card.slots[0].party);
    memset(record, marker, sizeof(record));
    CHECK(ff7_party_add_sephiroth(&card.slots[0].party, record) == FF7_PARTY_OK);
    const uint16_t active[] = {0, 7, FF7_PARTY_SEPHIROTH};
    CHECK(ff7_party_select(&card.slots[0].party, active) == FF7_PARTY_OK);
    CHECK(ff7_party_card_encode(&card, base, FF7_PARTY_CARD_BYTES, tail,
                                FF7_PARTY_CARD_EXTENSION_MAX, &written) == FF7_PARTY_OK);
    return written;
}

int main(void) {
    static uint8_t base[FF7_PARTY_CARD_BYTES], second[FF7_PARTY_CARD_BYTES];
    static uint8_t original[FF7_PARTY_CARD_BYTES];
    static uint8_t tail[FF7_PARTY_CARD_EXTENSION_MAX], tail2[FF7_PARTY_CARD_EXTENSION_MAX];
    static uint8_t output[FF7_PARTY_CARD_EXTENSION_MAX];
    FF7PartyCard decoded;
    size_t size = fixture(base, tail, 0x5a);
    size_t size2 = fixture(second, tail2, 0x77);
    memcpy(original, base, sizeof(base));
    register_ff7_party_save();
    CHECK(s_activate && !s_load && !s_save);
    s_activate();
    CHECK(s_load && s_save);
    CHECK(s_save(0, base, output, sizeof(output)) < 0); /* No load yet. */
    CHECK(s_load(-1, base, tail, (uint32_t)size) < 0);
    CHECK(s_load(2, base, tail, (uint32_t)size) < 0);
    CHECK(s_save(2, base, output, sizeof(output)) < 0);

    /* Raw cards get no invented extension or character. */
    CHECK(s_load(1, second, NULL, 0) == 0);
    memset(output, 0xcc, sizeof(output));
    CHECK(s_save(1, second, output, sizeof(output)) == 0);
    CHECK(output[0] == 0xcc);

    CHECK(s_load(0, base, tail, (uint32_t)size) == 0);
    CHECK(s_save(0, base, output, sizeof(output)) == (int)size);
    CHECK(!memcmp(output, tail, size));
    CHECK(!memcmp(base, original, sizeof(base)));
    CHECK(s_load(1, second, tail2, (uint32_t)size2) == 0);
    CHECK(s_save(1, second, output, sizeof(output)) == (int)size2);
    CHECK(!memcmp(output, tail2, size2));
    CHECK(s_save(0, base, output, sizeof(output)) == (int)size);
    CHECK(!memcmp(output, tail, size)); /* Cards do not share records. */

    /* Native writes change the binding, not the loaded extra records. */
    base[FF7_PARTY_CARD_BYTES-1] = 42;
    CHECK(s_save(0, base, output, sizeof(output)) == (int)size);
    CHECK(ff7_party_card_decode(&decoded, base, sizeof(base), output, size) == FF7_PARTY_OK);
    CHECK(decoded.slots[0].party.extra[0].record[0] == 0x5a);
    CHECK(decoded.slots[0].party.active[1] == 7);
    CHECK(decoded.slots[0].party.active[2] == 0x100);
    CHECK(ff7_party_card_decode(&decoded, original, sizeof(original), output, size) == FF7_PARTY_BASE_MISMATCH);
    base[FF7_PARTY_CARD_BYTES-1] = 0;

    memset(output, 0xcc, sizeof(output));
    CHECK(s_save(0, base, output, (uint32_t)size-1) < 0);
    CHECK(output[0] == 0xcc);
    base[128] = 0xa1; frame_crc(base+128); /* Deleted save. */
    CHECK(s_save(0, base, output, sizeof(output)) < 0);
    CHECK(output[0] == 0xcc);
    memcpy(base, original, sizeof(base));
    base[128+10] ^= 1; frame_crc(base+128); /* Different file in same slot. */
    CHECK(s_save(0, base, output, sizeof(output)) < 0);
    CHECK(s_directory_changes == 2);
    memcpy(base, original, sizeof(base));
    base[255] ^= 1; /* Directory XOR changed outside descriptor. */
    CHECK(s_save(0, base, output, sizeof(output)) < 0);
    memcpy(base, original, sizeof(base));

    /* Failed load clears the old state and blocks subsequent refresh. */
    CHECK(s_load(0, base, tail, (uint32_t)size-1) < 0);
    CHECK(s_save(0, base, output, sizeof(output)) < 0);
    base[FF7_PARTY_CARD_BYTES-1] = 1;
    CHECK(s_load(0, base, tail, (uint32_t)size) < 0); /* No stale recovery. */
    CHECK(s_save(0, base, output, sizeof(output)) < 0);
    base[FF7_PARTY_CARD_BYTES-1] = 0;
    CHECK(s_load(0, base, NULL, 0) == 0);
    CHECK(s_save(0, base, output, sizeof(output)) == 0); /* Old extras gone. */
    CHECK(s_save(1, second, output, sizeof(output)) == (int)size2); /* Other card intact. */
    s_activate();
    CHECK(s_save(0, base, output, sizeof(output)) < 0);
    CHECK(s_save(1, second, output, sizeof(output)) < 0);
    CHECK(s_loads > 0 && s_saves > 0 && s_rejects > 0);
    puts("ff7_party_save: isolated cards, strict reload, rebinding, rejection and activation reset passed");
    return 0;
}
