/* Real codec + title adapter + actual runtime file transport, synthetic cards. */
#include "ff7_party.h"
#include "memcard.h"
#include "mod_plugins.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
static PSXModActivationCallback activate;
static uint8_t base[MEMCARD_SIZE], original[MEMCARD_SIZE];
static uint8_t tail[FF7_PARTY_CARD_EXTENSION_MAX], decoded_tail[FF7_PARTY_CARD_EXTENSION_MAX];

int psx_mod_register_activation_plugin(const char* id, PSXModActivationCallback fn) {
    CHECK(strcmp(id, "ff7.party-save") == 0);
    activate = fn;
    return 1;
}
void psx_mod_counter_add(const char* name, uint32_t value) {
    (void)name; (void)value;
}

static size_t read_file(void) {
    FILE* f = fopen("card1.mcd", "rb");
    CHECK(f && fread(base, 1, sizeof base, f) == sizeof base);
    size_t size = fread(decoded_tail, 1, sizeof decoded_tail, f);
    CHECK(fgetc(f) == EOF && !ferror(f));
    CHECK(fclose(f) == 0);
    return size;
}
static void write_file(size_t size) {
    FILE* f = fopen("card1.mcd", "wb");
    CHECK(f && fwrite(base, 1, sizeof base, f) == sizeof base);
    CHECK(!size || fwrite(tail, 1, size, f) == size);
    CHECK(fclose(f) == 0);
}

int main(void) {
    uint8_t record[FF7_PARTY_RECORD_SIZE], sector[MEMCARD_SECTOR_SIZE];
    const MemcardSlotConfig slots[2] = {{"card1.mcd", 1}, {"card2.mcd", 1}};
    FF7PartyCard card = {0}, restored;
    size_t size;
    CHECK(activate);
    CHECK(memcard_format_file("card1.mcd") == 0);
    CHECK(memcard_format_file("card2.mcd") == 0);
    CHECK(read_file() == 0);
    memset(base + 128, 0, 128);
    base[128] = 0x51;
    base[132] = 0; base[133] = 0x20; /* synthetic allocated 8KiB file */
    base[136] = base[137] = 0xff;
    memcpy(base + 138, "FF7TEST", 7);
    for (unsigned i = 128; i < 255; ++i) base[255] ^= base[i];
    memcpy(original, base, sizeof base);
    memset(record, 0x45, sizeof record);
    record[0] = 10;
    card.count = 1;
    card.slots[0].directory_slot = 1;
    ff7_party_init(&card.slots[0].party);
    CHECK(ff7_party_add_sephiroth(&card.slots[0].party, record) == FF7_PARTY_OK);
    const uint16_t active[3] = {0, 7, FF7_PARTY_SEPHIROTH};
    CHECK(ff7_party_select(&card.slots[0].party, active) == FF7_PARTY_OK);
    CHECK(ff7_party_card_encode(&card, base, sizeof base, tail, sizeof tail, &size) == FF7_PARTY_OK);
    write_file(size);

    activate();
    memcard_init_slots(NULL, slots);
    CHECK(memcard_export_raw(0, base) == 0);
    CHECK(memcmp(base, original, sizeof base) == 0);
    memset(sector, 0x92, sizeof sector);
    CHECK(memcard_write_sector(0, 600, sector) == 0);
    memcard_flush(0);
    CHECK(memcard_last_flush_result(0) == 0);
    CHECK(read_file() == size);
    CHECK(base[600 * 128] == 0x92);
    CHECK(ff7_party_card_decode(&restored, base, sizeof base, decoded_tail, size) == FF7_PARTY_OK);
    CHECK(restored.count == 1 && restored.slots[0].party.active[2] == FF7_PARTY_SEPHIROTH);
    CHECK(memcmp(restored.slots[0].party.extra[0].record, record, sizeof record) == 0);

    /* Rebinding a tail to unrelated or stale base bytes is never implicit. */
    memcpy(tail, decoded_tail, size);
    base[MEMCARD_SIZE - 1] ^= 1;
    write_file(size);
    memcpy(original, base, sizeof base);
    CHECK(memcard_reload_bound() == 0);
    CHECK(memcard_write_sector(0, 601, sector) == 0);
    memcard_flush(0);
    CHECK(memcard_last_flush_result(0) == -2);
    CHECK(read_file() == size);
    CHECK(memcmp(base, original, sizeof base) == 0);

    /* Explicit raw import clears old extra state and stays a standard card. */
    CHECK(memcard_import_raw(0, base) == 0);
    CHECK(read_file() == 0);
    CHECK(memcmp(base, original, sizeof base) == 0);
    memcard_set_extension_codec(NULL, NULL);
    puts("FFVII extended-card adapter: actual file refresh, strict rejection and standard import passed");
    return 0;
}
