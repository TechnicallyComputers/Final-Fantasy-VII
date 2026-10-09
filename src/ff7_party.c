#include "ff7_party.h"

#include <string.h>

static uint16_t get16(const uint8_t* p) {
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}
static uint32_t get32(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void put16(uint8_t* p, uint16_t value) {
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
}
static void put32(uint8_t* p, uint32_t value) {
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
    p[2] = (uint8_t)(value >> 16);
    p[3] = (uint8_t)(value >> 24);
}

static uint32_t checksum(const uint8_t* data, size_t size) {
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < size; ++i) {
        /* CRC's own field is treated as zero. */
        crc ^= (i >= 60 && i < 64) ? 0 : data[i];
        for (int bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

void ff7_party_init(FF7PartyState* state) {
    if (!state) return;
    memset(state, 0, sizeof(*state));
    for (size_t i = 0; i < FF7_PARTY_ACTIVE_COUNT; ++i)
        state->active[i] = FF7_PARTY_EMPTY;
}

static const FF7PartyMember* find_extra(const FF7PartyState* state, uint16_t id) {
    if (!state || state->count > FF7_PARTY_EXTRA_CAPACITY) return NULL;
    for (size_t i = 0; i < state->count; ++i)
        if (state->extra[i].id == id) return &state->extra[i];
    return NULL;
}

FF7PartyMember* ff7_party_extra(FF7PartyState* state, uint16_t id) {
    if (!state || state->count > FF7_PARTY_EXTRA_CAPACITY) return NULL;
    for (size_t i = 0; i < state->count; ++i)
        if (state->extra[i].id == id) return &state->extra[i];
    return NULL;
}

static int valid_member(const FF7PartyMember* member) {
    return member->id >= FF7_PARTY_EXTRA_FIRST && member->id != FF7_PARTY_EMPTY &&
           member->presentation_id <= 10 && !(member->flags & ~FF7_PARTY_UNLOCKED);
}

static int valid_active(const FF7PartyState* state, const uint16_t* active) {
    for (size_t i = 0; i < FF7_PARTY_ACTIVE_COUNT; ++i) {
        uint16_t id = active[i];
        if (id == FF7_PARTY_EMPTY) continue;
        if (id >= FF7_PARTY_NATIVE_COUNT) {
            const FF7PartyMember* member = find_extra(state, id);
            if (!member || !(member->flags & FF7_PARTY_UNLOCKED)) return 0;
        }
        for (size_t j = 0; j < i; ++j)
            if (active[j] == id) return 0;
    }
    return 1;
}

static int valid_state(const FF7PartyState* state) {
    if (!state || state->count > FF7_PARTY_EXTRA_CAPACITY) return 0;
    for (size_t i = 0; i < state->count; ++i) {
        if (!valid_member(&state->extra[i])) return 0;
        for (size_t j = 0; j < i; ++j)
            if (state->extra[i].id == state->extra[j].id) return 0;
    }
    return valid_active(state, state->active);
}

FF7PartyResult ff7_party_add(FF7PartyState* state, uint16_t id,
    uint8_t presentation_id, const uint8_t record[FF7_PARTY_RECORD_SIZE]) {
    FF7PartyMember member;
    if (!record || !valid_state(state)) return FF7_PARTY_INVALID;
    memset(&member, 0, sizeof(member));
    member.id = id;
    member.presentation_id = presentation_id;
    member.flags = FF7_PARTY_UNLOCKED;
    if (!valid_member(&member) || find_extra(state, id)) return FF7_PARTY_INVALID;
    if (state->count == FF7_PARTY_EXTRA_CAPACITY) return FF7_PARTY_FULL;
    memcpy(member.record, record, FF7_PARTY_RECORD_SIZE);
    state->extra[state->count++] = member;
    return FF7_PARTY_OK;
}

FF7PartyResult ff7_party_add_sephiroth(FF7PartyState* state,
    const uint8_t record[FF7_PARTY_RECORD_SIZE]) {
    return ff7_party_add(state, FF7_PARTY_SEPHIROTH, 10, record);
}

FF7PartyResult ff7_party_import_sephiroth(FF7PartyState* state,
    const uint8_t* initial_data, size_t size) {
    static const uint8_t ids[] = {0, 1, 2, 3, 4, 5, 9, 10, 8};
    if (!initial_data || size < FF7_PARTY_NATIVE_COUNT * FF7_PARTY_RECORD_SIZE)
        return FF7_PARTY_INVALID;
    for (size_t i = 0; i < sizeof(ids); ++i)
        if (initial_data[i * FF7_PARTY_RECORD_SIZE] != ids[i]) return FF7_PARTY_INVALID;
    return ff7_party_add_sephiroth(state, initial_data + 7 * FF7_PARTY_RECORD_SIZE);
}

const uint8_t* ff7_party_record(const FF7PartyState* state, uint16_t id,
    const uint8_t* native_records, size_t native_size) {
    if (id < FF7_PARTY_NATIVE_COUNT) {
        size_t end = ((size_t)id + 1) * FF7_PARTY_RECORD_SIZE;
        return native_records && end <= native_size ?
            native_records + (size_t)id * FF7_PARTY_RECORD_SIZE : NULL;
    }
    const FF7PartyMember* member = find_extra(state, id);
    return member ? member->record : NULL;
}

FF7PartyResult ff7_party_select(FF7PartyState* state,
    const uint16_t active[FF7_PARTY_ACTIVE_COUNT]) {
    if (!active || !valid_state(state) || !valid_active(state, active))
        return FF7_PARTY_INVALID;
    memmove(state->active, active, sizeof(state->active));
    return FF7_PARTY_OK;
}

FF7PartyResult ff7_party_encode(const FF7PartyState* state,
    const uint8_t base_sha256[32], uint8_t* out, size_t capacity, size_t* written) {
    if (written) *written = 0;
    if (!base_sha256 || !valid_state(state)) return FF7_PARTY_INVALID;
    size_t size = FF7_PARTY_PAYLOAD_HEADER +
                  (size_t)state->count * FF7_PARTY_PAYLOAD_RECORD;
    if (written) *written = size;
    if (!out || capacity < size) return FF7_PARTY_BUFFER_SMALL;
    memset(out, 0, size);
    memcpy(out, "FF7PARTY", 8);
    put16(out + 8, 2);
    put16(out + 10, FF7_PARTY_PAYLOAD_HEADER);
    put32(out + 12, (uint32_t)size);
    put16(out + 16, state->count);
    for (size_t i = 0; i < FF7_PARTY_ACTIVE_COUNT; ++i)
        put16(out + 18 + 2 * i, state->active[i]);
    memcpy(out + 24, base_sha256, 32);
    for (size_t i = 0; i < state->count; ++i) {
        const FF7PartyMember* member = &state->extra[i];
        uint8_t* p = out + FF7_PARTY_PAYLOAD_HEADER + i * FF7_PARTY_PAYLOAD_RECORD;
        put16(p, member->id);
        p[2] = member->presentation_id;
        p[3] = member->flags;
        memcpy(p + 4, member->record, FF7_PARTY_RECORD_SIZE);
    }
    put32(out + 60, checksum(out, size));
    return FF7_PARTY_OK;
}

FF7PartyResult ff7_party_decode(FF7PartyState* state,
    const uint8_t base_sha256[32], const uint8_t* data, size_t size) {
    FF7PartyState next;
    if (!state || !base_sha256 || !data) return FF7_PARTY_INVALID;
    if (size < FF7_PARTY_PAYLOAD_HEADER || size > FF7_PARTY_PAYLOAD_MAX ||
        memcmp(data, "FF7PARTY", 8)) return FF7_PARTY_CORRUPT;
    if (get16(data + 8) != 2) return FF7_PARTY_VERSION;
    if (get16(data + 10) != FF7_PARTY_PAYLOAD_HEADER ||
        get32(data + 12) != size || get32(data + 56) != 0 ||
        get32(data + 60) != checksum(data, size)) return FF7_PARTY_CORRUPT;
    if (memcmp(data + 24, base_sha256, 32)) return FF7_PARTY_BASE_MISMATCH;
    ff7_party_init(&next);
    next.count = get16(data + 16);
    if (next.count > FF7_PARTY_EXTRA_CAPACITY ||
        size != FF7_PARTY_PAYLOAD_HEADER + (size_t)next.count * FF7_PARTY_PAYLOAD_RECORD)
        return FF7_PARTY_CORRUPT;
    for (size_t i = 0; i < FF7_PARTY_ACTIVE_COUNT; ++i)
        next.active[i] = get16(data + 18 + 2 * i);
    for (size_t i = 0; i < next.count; ++i) {
        const uint8_t* p = data + FF7_PARTY_PAYLOAD_HEADER + i * FF7_PARTY_PAYLOAD_RECORD;
        next.extra[i].id = get16(p);
        next.extra[i].presentation_id = p[2];
        next.extra[i].flags = p[3];
        memcpy(next.extra[i].record, p + 4, FF7_PARTY_RECORD_SIZE);
    }
    if (!valid_state(&next)) return FF7_PARTY_CORRUPT;
    *state = next;
    return FF7_PARTY_OK;
}

static uint32_t ror32(uint32_t value, unsigned bits) {
    return (value >> bits) | (value << (32 - bits));
}

/* SHA-256 compression for exactly one raw 128KiB card. Standard SHA-256
 * arithmetic/constants; no third-party implementation is incorporated. */
static void card_digest(const uint8_t* base, uint8_t digest[32]) {
    static const uint32_t k[64] = {
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
    };
    uint32_t h[8] = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                     0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    uint8_t padding[64] = {0x80};
    /* Big-endian length: 131072 * 8 = 0x100000 bits. */
    padding[61] = 0x10;
    for (size_t offset = 0; offset <= FF7_PARTY_CARD_BYTES; offset += 64) {
        const uint8_t* p = offset == FF7_PARTY_CARD_BYTES ? padding : base + offset;
        uint32_t w[64], a=h[0], b=h[1], c=h[2], d=h[3], e=h[4], f=h[5], g=h[6], v=h[7];
        for (unsigned i = 0; i < 16; ++i)
            w[i] = ((uint32_t)p[i*4] << 24) | ((uint32_t)p[i*4+1] << 16) |
                   ((uint32_t)p[i*4+2] << 8) | p[i*4+3];
        for (unsigned i = 16; i < 64; ++i) {
            uint32_t s0 = ror32(w[i-15],7) ^ ror32(w[i-15],18) ^ (w[i-15] >> 3);
            uint32_t s1 = ror32(w[i-2],17) ^ ror32(w[i-2],19) ^ (w[i-2] >> 10);
            w[i] = w[i-16] + s0 + w[i-7] + s1;
        }
        for (unsigned i = 0; i < 64; ++i) {
            uint32_t sum1 = ror32(e,6) ^ ror32(e,11) ^ ror32(e,25);
            uint32_t choose = (e & f) ^ (~e & g);
            uint32_t t1 = v + sum1 + choose + k[i] + w[i];
            uint32_t sum0 = ror32(a,2) ^ ror32(a,13) ^ ror32(a,22);
            uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
            v=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+sum0+majority;
        }
        h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d; h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=v;
    }
    for (unsigned i = 0; i < 8; ++i)
        for (unsigned j = 0; j < 4; ++j)
            digest[i*4+j] = (uint8_t)(h[i] >> (24-j*8));
}

static int frame_xor_valid(const uint8_t* frame) {
    uint8_t value = 0;
    for (size_t i = 0; i < 128; ++i) value ^= frame[i];
    return value == 0;
}

static int valid_base_card(const uint8_t* base, size_t size) {
    return base && size == FF7_PARTY_CARD_BYTES && base[0] == 'M' &&
           base[1] == 'C' && frame_xor_valid(base);
}

static int valid_directory_slot(const uint8_t* base, unsigned slot) {
    if (slot < 1 || slot > FF7_PARTY_CARD_SLOTS) return 0;
    const uint8_t* frame = base + slot * 128;
    return get32(frame) == 0x51 && frame_xor_valid(frame);
}

FF7PartyResult ff7_party_card_encode(const FF7PartyCard* card,
    const uint8_t* base, size_t base_size,
    uint8_t* out, size_t capacity, size_t* written) {
    size_t size = FF7_PARTY_CARD_HEADER;
    uint8_t digest[32];
    if (written) *written = 0;
    if (!card || card->count > FF7_PARTY_CARD_SLOTS || !valid_base_card(base, base_size))
        return FF7_PARTY_INVALID;
    for (size_t i = 0; i < card->count; ++i) {
        const FF7PartyCardSlot* slot = &card->slots[i];
        if (!valid_directory_slot(base, slot->directory_slot) || !valid_state(&slot->party) ||
            (i && slot->directory_slot <= card->slots[i-1].directory_slot)) return FF7_PARTY_INVALID;
        size += FF7_PARTY_CARD_ENTRY + FF7_PARTY_PAYLOAD_HEADER +
                (size_t)slot->party.count * FF7_PARTY_PAYLOAD_RECORD;
    }
    if (written) *written = size;
    if (!out || capacity < size) return FF7_PARTY_BUFFER_SMALL;
    card_digest(base, digest);
    memset(out, 0, size);
    memcpy(out, "FF7MCEXT", 8);
    put16(out+8, 1);
    put16(out+10, FF7_PARTY_CARD_HEADER);
    put32(out+12, (uint32_t)size);
    put16(out+16, card->count);
    put32(out+20, FF7_PARTY_CARD_BYTES);
    memcpy(out+24, digest, 32);
    size_t cursor = FF7_PARTY_CARD_HEADER;
    for (size_t i = 0; i < card->count; ++i) {
        size_t payload_size = 0;
        out[cursor] = card->slots[i].directory_slot;
        FF7PartyResult result = ff7_party_encode(&card->slots[i].party, digest,
            out+cursor+FF7_PARTY_CARD_ENTRY, size-cursor-FF7_PARTY_CARD_ENTRY, &payload_size);
        if (result != FF7_PARTY_OK) return result; /* Prevalidated above. */
        put32(out+cursor+4, (uint32_t)payload_size);
        cursor += FF7_PARTY_CARD_ENTRY + payload_size;
    }
    put32(out+60, checksum(out, size));
    return FF7_PARTY_OK;
}

FF7PartyResult ff7_party_card_decode(FF7PartyCard* card,
    const uint8_t* base, size_t base_size, const uint8_t* tail, size_t tail_size) {
    FF7PartyCard next;
    uint8_t digest[32];
    if (!card || !valid_base_card(base, base_size)) return FF7_PARTY_INVALID;
    memset(&next, 0, sizeof(next));
    if (!tail_size) { *card = next; return FF7_PARTY_OK; }
    if (!tail) return FF7_PARTY_INVALID;
    if (tail_size < FF7_PARTY_CARD_HEADER || tail_size > FF7_PARTY_CARD_EXTENSION_MAX ||
        memcmp(tail, "FF7MCEXT", 8)) return FF7_PARTY_CORRUPT;
    if (get16(tail+8) != 1) return FF7_PARTY_VERSION;
    if (get16(tail+10) != FF7_PARTY_CARD_HEADER || get32(tail+12) != tail_size ||
        get16(tail+18) || get32(tail+20) != FF7_PARTY_CARD_BYTES || get32(tail+56) ||
        get32(tail+60) != checksum(tail, tail_size)) return FF7_PARTY_CORRUPT;
    next.count = get16(tail+16);
    if (next.count > FF7_PARTY_CARD_SLOTS) return FF7_PARTY_CORRUPT;
    card_digest(base, digest);
    if (memcmp(tail+24, digest, 32)) return FF7_PARTY_BASE_MISMATCH;
    size_t cursor = FF7_PARTY_CARD_HEADER;
    for (size_t i = 0; i < next.count; ++i) {
        if (tail_size-cursor < FF7_PARTY_CARD_ENTRY) return FF7_PARTY_CORRUPT;
        unsigned slot = tail[cursor];
        size_t payload_size = get32(tail+cursor+4);
        if (!valid_directory_slot(base, slot) || tail[cursor+1] || tail[cursor+2] || tail[cursor+3] ||
            (i && slot <= next.slots[i-1].directory_slot) ||
            payload_size > tail_size-cursor-FF7_PARTY_CARD_ENTRY) return FF7_PARTY_CORRUPT;
        next.slots[i].directory_slot = (uint8_t)slot;
        FF7PartyResult result = ff7_party_decode(&next.slots[i].party, digest,
            tail+cursor+FF7_PARTY_CARD_ENTRY, payload_size);
        if (result != FF7_PARTY_OK) return result;
        cursor += FF7_PARTY_CARD_ENTRY + payload_size;
    }
    if (cursor != tail_size) return FF7_PARTY_CORRUPT;
    *card = next;
    return FF7_PARTY_OK;
}

/* Opt-in runtime observation only. The core above remains buildable without
 * the emulator for save-format and storage-isolation validation. */
#ifdef FF7_PARTY_WITH_RUNTIME
#include "cpu_state.h"
#include "mod_plugins.h"
#include "../psx_symbols.h"
#include <stdio.h>

static unsigned s_party_audit_count;
static int s_party_audit_active;

static void ff7_party_audit_activate(void) {
    s_party_audit_count = 0;
    s_party_audit_active = 1;
    puts("[ff7.party-audit] read-only alias audit armed; expanded party gameplay is not implemented");
}

static void ff7_party_audit_entry(struct CPUState* cpu, uint32_t address) {
    static const uint32_t signature[] = {
        0x00042080, 0x3c018005, 0x242191d0, 0x00240821, 0x8c230000,
        0x00000000, 0x00031140, 0x00431021, 0x00021080, 0x3c03800a,
        0x2463c748, 0x03e00008, 0x00431021
    };
    if (!s_party_audit_active || !cpu || address != PSX_FN_GetCharacterName ||
        s_party_audit_count >= 24) return;
    /* Independently checked against the user's original NTSC-U executable.
     * Refuse observations if a patch or other revision changed this routine. */
    for (size_t i = 0; i < sizeof(signature) / sizeof(signature[0]); ++i) {
        if (psx_mod_read_word(address + (uint32_t)i * 4) != signature[i]) {
            puts("[ff7.party-audit] unsupported name lookup bytes; audit disabled");
            s_party_audit_active = 0;
            return;
        }
    }
    uint32_t id = cpu->gpr[4];
    ++s_party_audit_count;
    if (id <= 10) {
        uint32_t record = psx_mod_read_word(PSX_FN_g_BattleCharIdToCharId + id * 4);
        printf("[ff7.party-audit] guest character %u -> native record %u; caller 0x%08X%s\n",
            id, record, cpu->gpr[31], id == 10 && record == 7 ? " (shares Vincent)" : "");
    } else {
        printf("[ff7.party-audit] out-of-range guest character %u; caller 0x%08X\n",
            id, cpu->gpr[31]);
    }
    fflush(stdout);
}

PSX_MOD_CONSTRUCTOR(register_ff7_party_audit) {
    (void)psx_mod_register_activation_plugin("ff7.party-audit", ff7_party_audit_activate);
    (void)psx_mod_register_function_entry_plugin("ff7.party-audit",
        PSX_FN_GetCharacterName, ff7_party_audit_entry);
}
#endif
