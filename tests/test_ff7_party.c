/* Standalone: cc -std=c11 -Wall -Wextra -Werror -Isrc
 * tests/test_ff7_party.c src/ff7_party.c -o test_ff7_party */
#include "ff7_party.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #expr); exit(1); \
} } while (0)

static void repair_crc(uint8_t* data, size_t size) {
    uint32_t crc = UINT32_MAX;
    memset(data + 60, 0, 4);
    for (size_t i = 0; i < size; ++i) {
        crc ^= data[i];
        for (int j = 0; j < 8; ++j)
            crc = (crc >> 1) ^ ((crc & 1) ? 0xedb88320u : 0);
    }
    crc = ~crc;
    for (int i = 0; i < 4; ++i) data[60 + i] = (uint8_t)(crc >> (8 * i));
}

static void storage_and_roster(void) {
    uint8_t native[FF7_PARTY_NATIVE_COUNT * FF7_PARTY_RECORD_SIZE];
    uint8_t original[sizeof(native)], sephiroth[FF7_PARTY_RECORD_SIZE];
    FF7PartyState party, before;
    const uint16_t active[] = {0, 7, FF7_PARTY_SEPHIROTH};
    const uint16_t duplicate[] = {0, FF7_PARTY_SEPHIROTH, FF7_PARTY_SEPHIROTH};
    const uint16_t legacy_alias[] = {0, 7, 10};
    for (size_t i = 0; i < sizeof(native); ++i) native[i] = (uint8_t)i;
    memcpy(original, native, sizeof(native));
    memset(sephiroth, 0x5a, sizeof(sephiroth));
    ff7_party_init(&party);
    CHECK(ff7_party_select(&party, active) == FF7_PARTY_INVALID);
    CHECK(ff7_party_add_sephiroth(&party, sephiroth) == FF7_PARTY_OK);
    CHECK(ff7_party_add_sephiroth(&party, sephiroth) == FF7_PARTY_INVALID);
    CHECK(ff7_party_select(&party, active) == FF7_PARTY_OK);
    CHECK(ff7_party_record(&party, 7, native, sizeof(native)) == native + 7 * 132);
    CHECK(ff7_party_record(&party, 0, native, sizeof(native)) == native);
    CHECK(ff7_party_record(&party, 10, native, sizeof(native)) == NULL);
    CHECK(ff7_party_record(&party, 7, native, 7 * 132) == NULL);
    CHECK(ff7_party_record(&party, FF7_PARTY_EMPTY, native, sizeof(native)) == NULL);
    CHECK(ff7_party_extra(&party, FF7_PARTY_SEPHIROTH)->presentation_id == 10);
    ff7_party_extra(&party, FF7_PARTY_SEPHIROTH)->record[0x28] = 0x99;
    CHECK(ff7_party_record(&party, FF7_PARTY_SEPHIROTH, native, sizeof(native))[0x28] == 0x99);
    CHECK(memcmp(original, native, sizeof(native)) == 0);
    CHECK(sephiroth[0x28] == 0x5a);
    before = party;
    CHECK(ff7_party_select(&party, duplicate) == FF7_PARTY_INVALID);
    CHECK(ff7_party_select(&party, legacy_alias) == FF7_PARTY_INVALID);
    CHECK(memcmp(&party, &before, sizeof(party)) == 0);
    CHECK(ff7_party_select(&party, party.active) == FF7_PARTY_OK);
}

static void payload(void) {
    FF7PartyState party, decoded, sentinel;
    uint8_t record[FF7_PARTY_RECORD_SIZE], digest[32], other[32];
    uint8_t encoded[FF7_PARTY_PAYLOAD_MAX], corrupt[sizeof(encoded)];
    size_t size = 0, second_size = 0;
    const uint16_t active[] = {0, 7, FF7_PARTY_SEPHIROTH};
    memset(record, 0xa3, sizeof(record));
    memset(digest, 0x21, sizeof(digest));
    memset(other, 0x22, sizeof(other));
    ff7_party_init(&party);
    CHECK(ff7_party_add_sephiroth(&party, record) == FF7_PARTY_OK);
    CHECK(ff7_party_select(&party, active) == FF7_PARTY_OK);
    CHECK(ff7_party_encode(&party, digest, NULL, 0, &size) == FF7_PARTY_BUFFER_SMALL);
    CHECK(size == 200);
    memset(encoded, 0xcc, sizeof(encoded));
    CHECK(ff7_party_encode(&party, digest, encoded, size - 1, NULL) == FF7_PARTY_BUFFER_SMALL);
    CHECK(encoded[0] == 0xcc);
    CHECK(ff7_party_encode(&party, digest, encoded, sizeof(encoded), &size) == FF7_PARTY_OK);
    CHECK(!memcmp(encoded, "FF7PARTY\x02\x00\x40\x00\xc8\x00\x00\x00", 16));
    CHECK(encoded[22] == 0 && encoded[23] == 1); /* Independent 16-bit identity. */
    CHECK(encoded[64] == 0 && encoded[65] == 1 && encoded[66] == 10);
    CHECK(ff7_party_decode(&decoded, digest, encoded, size) == FF7_PARTY_OK);
    CHECK(!memcmp(&party, &decoded, sizeof(party)));
    CHECK(ff7_party_encode(&decoded, digest, corrupt, sizeof(corrupt), &second_size) == FF7_PARTY_OK);
    CHECK(second_size == size && !memcmp(encoded, corrupt, size));
    memset(&sentinel, 0x55, sizeof(sentinel));
    decoded = sentinel;
    CHECK(ff7_party_decode(&decoded, other, encoded, size) == FF7_PARTY_BASE_MISMATCH);
    CHECK(!memcmp(&decoded, &sentinel, sizeof(decoded)));
    for (size_t n = 0; n < size; ++n) {
        CHECK(ff7_party_decode(&decoded, digest, encoded, n) != FF7_PARTY_OK);
        CHECK(!memcmp(&decoded, &sentinel, sizeof(decoded)));
    }
    for (size_t byte = 0; byte < size; ++byte) {
        memcpy(corrupt, encoded, size);
        corrupt[byte] ^= 1;
        CHECK(ff7_party_decode(&decoded, digest, corrupt, size) != FF7_PARTY_OK);
        CHECK(!memcmp(&decoded, &sentinel, sizeof(decoded)));
    }
    /* Structurally invalid inputs with VALID checksums also fail atomically. */
    const size_t invalid_offsets[] = {16, 20, 56, 64, 66, 67};
    const uint8_t invalid_values[] = {17, 0, 1, 0xff, 11, 0x80};
    for (size_t i = 0; i < sizeof(invalid_offsets) / sizeof(invalid_offsets[0]); ++i) {
        memcpy(corrupt, encoded, size);
        corrupt[invalid_offsets[i]] = invalid_values[i];
        if (invalid_offsets[i] == 64) corrupt[65] = 0xff;
        repair_crc(corrupt, size);
        CHECK(ff7_party_decode(&decoded, digest, corrupt, size) != FF7_PARTY_OK);
        CHECK(!memcmp(&decoded, &sentinel, sizeof(decoded)));
    }
    /* Empty and maximum rosters, including independent extra characters. */
    ff7_party_init(&party);
    CHECK(ff7_party_encode(&party, digest, encoded, sizeof(encoded), &size) == FF7_PARTY_OK);
    CHECK(size == FF7_PARTY_PAYLOAD_HEADER);
    CHECK(ff7_party_decode(&decoded, digest, encoded, size) == FF7_PARTY_OK);
    for (int i = 0; i < FF7_PARTY_EXTRA_CAPACITY; ++i) {
        CHECK(ff7_party_add(&party, (uint16_t)(0x100 + i), 10, record) == FF7_PARTY_OK);
    }
    CHECK(ff7_party_add(&party, 0x200, 10, record) == FF7_PARTY_FULL);
    CHECK(ff7_party_encode(&party, digest, encoded, sizeof(encoded), &size) == FF7_PARTY_OK);
    CHECK(size == FF7_PARTY_PAYLOAD_MAX);
    CHECK(ff7_party_decode(&decoded, digest, encoded, size) == FF7_PARTY_OK);
    memcpy(corrupt, encoded, size);
    memcpy(corrupt + 64 + 136, corrupt + 64, 2); /* Duplicate identity. */
    repair_crc(corrupt, size);
    CHECK(ff7_party_decode(&decoded, digest, corrupt, size) == FF7_PARTY_CORRUPT);
}

static void original_template(void) {
    const uint8_t ids[] = {0, 1, 2, 3, 4, 5, 9, 10, 8};
    uint8_t initial[9 * FF7_PARTY_RECORD_SIZE];
    FF7PartyState state;
    memset(initial, 0x43, sizeof(initial));
    for (size_t i = 0; i < sizeof(ids); ++i) initial[i * 132] = ids[i];
    ff7_party_init(&state);
    CHECK(ff7_party_import_sephiroth(&state, initial, sizeof(initial) - 1) == FF7_PARTY_INVALID);
    initial[7 * 132] = 7; /* A live Vincent record must not be imported. */
    CHECK(ff7_party_import_sephiroth(&state, initial, sizeof(initial)) == FF7_PARTY_INVALID);
    CHECK(state.count == 0);
    initial[7 * 132] = 10;
    CHECK(ff7_party_import_sephiroth(&state, initial, sizeof(initial)) == FF7_PARTY_OK);
    CHECK(!memcmp(state.extra[0].record, initial + 7 * 132, 132));
    CHECK(state.extra[0].flags == FF7_PARTY_UNLOCKED);
}

static void repair_frame(uint8_t* frame) {
    uint8_t sum = 0;
    for (size_t i = 0; i < 127; ++i) sum ^= frame[i];
    frame[127] = sum;
}

static void extended_card(void) {
    static uint8_t base[FF7_PARTY_CARD_BYTES], original[FF7_PARTY_CARD_BYTES];
    static uint8_t tail[FF7_PARTY_CARD_EXTENSION_MAX], corrupt[FF7_PARTY_CARD_EXTENSION_MAX];
    FF7PartyCard card, decoded, sentinel;
    uint8_t record[FF7_PARTY_RECORD_SIZE];
    size_t size;
    memset(base, 0, sizeof(base));
    base[0] = 'M'; base[1] = 'C'; repair_frame(base);
    for (unsigned slot = 1; slot <= 15; ++slot) {
        uint8_t* frame = base + slot * 128;
        frame[0] = 0x51;
        frame[5] = 0x20;
        frame[8] = frame[9] = 0xff;
        memcpy(frame+10, "FF7TEST", 7);
        repair_frame(frame);
    }
    memcpy(original, base, sizeof(base));
    memset(&card, 0, sizeof(card));
    memset(&sentinel, 0x55, sizeof(sentinel));
    memset(record, 0xa3, sizeof(record));
    card.count = 1;
    card.slots[0].directory_slot = 1;
    ff7_party_init(&card.slots[0].party);
    CHECK(ff7_party_add_sephiroth(&card.slots[0].party, record) == FF7_PARTY_OK);
    const uint16_t active[] = {0, 7, 0x100};
    CHECK(ff7_party_select(&card.slots[0].party, active) == FF7_PARTY_OK);
    CHECK(ff7_party_card_encode(&card, base, sizeof(base), NULL, 0, &size) == FF7_PARTY_BUFFER_SMALL);
    CHECK(size == 272);
    memset(tail, 0xcc, sizeof(tail));
    CHECK(ff7_party_card_encode(&card, base, sizeof(base), tail, size-1, NULL) == FF7_PARTY_BUFFER_SMALL);
    CHECK(tail[0] == 0xcc);
    CHECK(ff7_party_card_encode(&card, base, sizeof(base), tail, sizeof(tail), &size) == FF7_PARTY_OK);
    CHECK(!memcmp(tail, "FF7MCEXT\x01\0\x40\0\x10\x01\0\0", 16));
    CHECK(ff7_party_card_decode(&decoded, base, sizeof(base), tail, size) == FF7_PARTY_OK);
    CHECK(!memcmp(&card, &decoded, sizeof(card)));
    CHECK(!memcmp(base, original, sizeof(base)));
    decoded = sentinel;
    for (size_t n = 1; n < size; ++n) {
        CHECK(ff7_party_card_decode(&decoded, base, sizeof(base), tail, n) != FF7_PARTY_OK);
        CHECK(!memcmp(&decoded, &sentinel, sizeof(decoded)));
    }
    for (size_t n = 0; n < size; ++n) {
        memcpy(corrupt, tail, size); corrupt[n] ^= 1;
        CHECK(ff7_party_card_decode(&decoded, base, sizeof(base), corrupt, size) != FF7_PARTY_OK);
        CHECK(!memcmp(&decoded, &sentinel, sizeof(decoded)));
    }
    base[sizeof(base)-1] ^= 1; /* Outside this save: binding is the WHOLE card. */
    CHECK(ff7_party_card_decode(&decoded, base, sizeof(base), tail, size) == FF7_PARTY_BASE_MISMATCH);
    CHECK(!memcmp(&decoded, &sentinel, sizeof(decoded)));
    base[sizeof(base)-1] ^= 1;
    const size_t invalid[] = {16, 18, 20, 56, 64, 65, 68};
    for (size_t n = 0; n < sizeof(invalid)/sizeof(invalid[0]); ++n) {
        memcpy(corrupt, tail, size); corrupt[invalid[n]] = 0xff; repair_crc(corrupt, size);
        CHECK(ff7_party_card_decode(&decoded, base, sizeof(base), corrupt, size) != FF7_PARTY_OK);
        CHECK(!memcmp(&decoded, &sentinel, sizeof(decoded)));
    }
    memcpy(corrupt, tail, size);
    corrupt[72+8] = 1; /* Old slot-bound payload not accepted inside new envelope. */
    repair_crc(corrupt+72, 200); repair_crc(corrupt, size);
    CHECK(ff7_party_card_decode(&decoded, base, sizeof(base), corrupt, size) == FF7_PARTY_VERSION);
    CHECK(ff7_party_card_decode(&decoded, base, sizeof(base)-1, tail, size) == FF7_PARTY_INVALID);
    base[127] ^= 1;
    CHECK(ff7_party_card_decode(&decoded, base, sizeof(base), tail, size) == FF7_PARTY_INVALID);
    base[127] ^= 1;
    CHECK(ff7_party_card_decode(&decoded, base, sizeof(base), NULL, 0) == FF7_PARTY_OK);
    CHECK(decoded.count == 0);
    /* All 15 save entries, each with the maximum independent extra roster. */
    memset(&card, 0, sizeof(card)); card.count = 15;
    for (unsigned slot = 0; slot < 15; ++slot) {
        card.slots[slot].directory_slot = (uint8_t)(slot+1);
        ff7_party_init(&card.slots[slot].party);
        for (unsigned i = 0; i < 16; ++i)
            CHECK(ff7_party_add(&card.slots[slot].party, (uint16_t)(0x100+i), 10, record) == FF7_PARTY_OK);
    }
    CHECK(ff7_party_card_encode(&card, base, sizeof(base), tail, sizeof(tail), &size) == FF7_PARTY_OK);
    CHECK(size == FF7_PARTY_CARD_EXTENSION_MAX);
    CHECK(ff7_party_card_decode(&decoded, base, sizeof(base), tail, size) == FF7_PARTY_OK);
    CHECK(!memcmp(&card, &decoded, sizeof(card)));
    card.slots[1].directory_slot = 1;
    CHECK(ff7_party_card_encode(&card, base, sizeof(base), tail, sizeof(tail), &size) == FF7_PARTY_INVALID);
    CHECK(!memcmp(base, original, sizeof(base)));
}

int main(void) {
    storage_and_roster();
    payload();
    original_template();
    extended_card();
    puts("ff7_party: storage isolation, roster validation, appended card integrity and rollback passed");
    return 0;
}
