#ifndef FF7_PARTY_H
#define FF7_PARTY_H

#include <stddef.h>
#include <stdint.h>

/* Host-side expanded roster and appended card-extension codec. No file I/O.
 * Gameplay adapters must explicitly resolve these IDs; never truncate them to
 * the game's byte IDs. In particular, stock ID 10 aliases Vincent's record.
 * Native character records are opaque until their individual fields are proved.
 */
enum {
    FF7_PARTY_NATIVE_COUNT = 9,
    FF7_PARTY_RECORD_SIZE = 132,
    FF7_PARTY_ACTIVE_COUNT = 3,
    FF7_PARTY_EXTRA_CAPACITY = 16,
    FF7_PARTY_EXTRA_FIRST = 0x100,
    FF7_PARTY_SEPHIROTH = 0x100,
    FF7_PARTY_EMPTY = 0xffff,
    FF7_PARTY_UNLOCKED = 1,
    FF7_PARTY_PAYLOAD_HEADER = 64,
    FF7_PARTY_PAYLOAD_RECORD = 136,
    FF7_PARTY_PAYLOAD_MAX = 64 + 16 * 136,
    FF7_PARTY_CARD_BYTES = 131072,
    FF7_PARTY_CARD_SLOTS = 15,
    FF7_PARTY_CARD_HEADER = 64,
    FF7_PARTY_CARD_ENTRY = 8,
    FF7_PARTY_CARD_EXTENSION_MAX = 64 + 15 * (8 + 64 + 16 * 136)
};

typedef struct FF7PartyMember {
    uint16_t id;
    uint8_t presentation_id; /* Asset identity only; never a storage index. */
    uint8_t flags;
    uint8_t record[FF7_PARTY_RECORD_SIZE];
} FF7PartyMember;

typedef struct FF7PartyState {
    uint16_t active[FF7_PARTY_ACTIVE_COUNT];
    uint16_t count;
    FF7PartyMember extra[FF7_PARTY_EXTRA_CAPACITY];
} FF7PartyState;

typedef struct FF7PartyCardSlot {
    uint8_t directory_slot; /* First allocated directory frame, 1..15. */
    FF7PartyState party;
} FF7PartyCardSlot;

typedef struct FF7PartyCard {
    uint16_t count;
    FF7PartyCardSlot slots[FF7_PARTY_CARD_SLOTS]; /* Strictly ascending slot IDs. */
} FF7PartyCard;

typedef enum FF7PartyResult {
    FF7_PARTY_OK = 0,
    FF7_PARTY_INVALID,
    FF7_PARTY_FULL,
    FF7_PARTY_BUFFER_SMALL,
    FF7_PARTY_CORRUPT,
    FF7_PARTY_VERSION,
    FF7_PARTY_BASE_MISMATCH
} FF7PartyResult;

/* Empty party, no invented stats. Caller supplies the desired initial party and
 * a validated template for each new member. Sephiroth's helper unlocks him. */
void ff7_party_init(FF7PartyState* state);
FF7PartyResult ff7_party_add(FF7PartyState* state, uint16_t id,
    uint8_t presentation_id, const uint8_t record[FF7_PARTY_RECORD_SIZE]);
FF7PartyResult ff7_party_add_sephiroth(FF7PartyState* state,
    const uint8_t record[FF7_PARTY_RECORD_SIZE]);
/* Decompressed INIT/KERNEL.BIN section 4 starts with the nine default records.
 * Its row 7 is Sephiroth (ID 10), BEFORE the story replaces it with Vincent.
 * This copies the original template into independent storage; it never reads
 * the live Vincent record. Verify the source disc identity before calling. */
FF7PartyResult ff7_party_import_sephiroth(FF7PartyState* state,
    const uint8_t* initial_data, size_t size);
FF7PartyMember* ff7_party_extra(FF7PartyState* state, uint16_t id);
const uint8_t* ff7_party_record(const FF7PartyState* state, uint16_t id,
    const uint8_t* native_records, size_t native_size);
FF7PartyResult ff7_party_select(FF7PartyState* state,
    const uint16_t active[FF7_PARTY_ACTIVE_COUNT]);

/* Version 2 payload: explicit little-endian, CRC32, and SHA-256 binding supplied
 * by the caller for the entire exact 128KiB base card, NOT an individual save.
 * Decode validates before replacing state, including duplicate IDs and parties.
 * Encoding does not modify state, native saves or native character records.
 * Buffer arguments must not overlap state or the digest. Version 1 sidecars
 * are rejected; their digest meant an individual slot and cannot be migrated
 * without the original slot identity. Prefer the card APIs below.
 */
FF7PartyResult ff7_party_encode(const FF7PartyState* state,
    const uint8_t base_sha256[32], uint8_t* out, size_t capacity, size_t* written);
FF7PartyResult ff7_party_decode(FF7PartyState* state,
    const uint8_t base_sha256[32], const uint8_t* data, size_t size);

/* FF7MCEXT v1 tail, appended at offset 0x20000 after a raw MC image. These
 * functions calculate SHA-256 over the whole base card internally, validate
 * its MC/header XOR and each referenced allocated directory frame, and never
 * modify base bytes. Empty tails decode as a standard card with no metadata.
 * Nonempty tails must validate completely before decode replaces card state.
 * Encode's output contains ONLY the tail. The frontend must atomically save
 * base[131072] + tail, refresh every payload binding after ANY base change,
 * remove metadata when a save is deleted/replaced, and snapshot base+metadata
 * together for rewind/savestates. Keep native fallback parties in base saves;
 * extra IDs belong only in the extension. See docs/SEPHIROTH_SAVE_FORMAT.md.
 * Buffers and state must not overlap. Both APIs use approximately 34KiB stack
 * scratch during decode; callers should not use tiny worker stacks.
 */
FF7PartyResult ff7_party_card_encode(const FF7PartyCard* card,
    const uint8_t* base, size_t base_size,
    uint8_t* out, size_t capacity, size_t* written);
FF7PartyResult ff7_party_card_decode(FF7PartyCard* card,
    const uint8_t* base, size_t base_size, const uint8_t* tail, size_t tail_size);

#endif
