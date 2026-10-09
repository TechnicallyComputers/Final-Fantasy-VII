#ifndef FF7_PARTY_GAME_H
#define FF7_PARTY_GAME_H
#include <stdint.h>
typedef struct FF7PartyProfile {
    uint16_t identity;
    uint8_t presentation,kernel_template_row,weapon_compatibility,armor_compatibility,
            accessory_compatibility,growth_identity;
    const char *battle_model,*portrait;
} FF7PartyProfile;
unsigned ff7_party_game_extra_count(void);
uint8_t ff7_party_game_extra_guest(unsigned);
uint32_t ff7_party_game_record(uint8_t);
uint8_t ff7_party_game_presentation(uint8_t);
int ff7_party_game_is_extra(uint8_t);
void ff7_party_game_observe_active(void);
const FF7PartyProfile* ff7_party_game_profile(uint8_t);
#endif
