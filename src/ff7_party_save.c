/* Developer-only persistence transport. No gameplay state creation, guest
 * writes, filesystem access, or implicit stale-metadata recovery. */
#include "ff7_party.h"
#include "memcard.h"
#include "mod_plugins.h"

#include <string.h>

enum { PARTY_SAVE_CARDS = 2, DIRECTORY_DESCRIPTOR_BYTES = 32 };

static FF7PartyCard s_cards[PARTY_SAVE_CARDS];
static uint8_t s_ready[PARTY_SAVE_CARDS];
static uint8_t s_had_tail[PARTY_SAVE_CARDS];
static uint8_t s_directories[PARTY_SAVE_CARDS][FF7_PARTY_CARD_SLOTS][DIRECTORY_DESCRIPTOR_BYTES];

_Static_assert(FF7_PARTY_CARD_EXTENSION_MAX <= MEMCARD_EXTENSION_MAX,
               "Memory-card transport cannot hold the FFVII extension");

static int reject(const char* counter) {
    psx_mod_counter_add("ff7.party_save.reject", 1);
    psx_mod_counter_add(counter, 1);
    return -1;
}

static int party_save_load(int card, const uint8_t* base,
                           const uint8_t* tail, uint32_t tail_size) {
    psx_mod_counter_add("ff7.party_save.load", 1);
    if (card < 0 || card >= PARTY_SAVE_CARDS)
        return reject("ff7.party_save.load_reject");

    /* A failed reload must not retain another file's previously valid state. */
    memset(&s_cards[card], 0, sizeof(s_cards[card]));
    memset(s_directories[card], 0, sizeof(s_directories[card]));
    s_ready[card] = s_had_tail[card] = 0;
    if (ff7_party_card_decode(&s_cards[card], base, FF7_PARTY_CARD_BYTES,
                              tail, tail_size) != FF7_PARTY_OK)
        return reject("ff7.party_save.load_reject");

    for (size_t i = 0; i < s_cards[card].count; ++i) {
        unsigned slot = s_cards[card].slots[i].directory_slot;
        memcpy(s_directories[card][i], base + slot * 128, DIRECTORY_DESCRIPTOR_BYTES);
    }
    s_ready[card] = 1;
    s_had_tail[card] = tail_size != 0;
    psx_mod_counter_add("ff7.party_save.load_ok", 1);
    if (!tail_size) psx_mod_counter_add("ff7.party_save.raw_load", 1);
    return 0;
}

static int party_save_store(int card, const uint8_t* base,
                            uint8_t* tail, uint32_t capacity) {
    size_t written = 0;
    psx_mod_counter_add("ff7.party_save.save", 1);
    if (card < 0 || card >= PARTY_SAVE_CARDS || !s_ready[card] || !base)
        return reject("ff7.party_save.save_reject");

    if (!s_had_tail[card] && !s_cards[card].count) {
        psx_mod_counter_add("ff7.party_save.raw_save", 1);
        return 0; /* Ordinary cards stay ordinary. No automatic unlock/init. */
    }
    for (size_t i = 0; i < s_cards[card].count; ++i) {
        unsigned slot = s_cards[card].slots[i].directory_slot;
        if (memcmp(s_directories[card][i], base + slot * 128, DIRECTORY_DESCRIPTOR_BYTES)) {
            psx_mod_counter_add("ff7.party_save.directory_changed", 1);
            return reject("ff7.party_save.save_reject");
        }
    }
    /* Encode validates allocation and frame XOR again, then refreshes every
     * full-card SHA binding. A rejected encode never publishes a partial tail. */
    if (ff7_party_card_encode(&s_cards[card], base, FF7_PARTY_CARD_BYTES,
                              tail, capacity, &written) != FF7_PARTY_OK)
        return reject("ff7.party_save.save_reject");
    psx_mod_counter_add("ff7.party_save.save_ok", 1);
    return (int)written;
}

static void party_save_activate(void) {
    memset(s_cards, 0, sizeof(s_cards));
    memset(s_ready, 0, sizeof(s_ready));
    memset(s_had_tail, 0, sizeof(s_had_tail));
    memset(s_directories, 0, sizeof(s_directories));
    psx_mod_counter_add("ff7.party_save.activate", 1);
    memcard_set_extension_codec(party_save_load, party_save_store);
}

PSX_MOD_CONSTRUCTOR(register_ff7_party_save) {
    (void)psx_mod_register_activation_plugin("ff7.party-save", party_save_activate);
}
