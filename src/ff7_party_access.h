#ifndef FF7_PARTY_ACCESS_H
#define FF7_PARTY_ACCESS_H
#include "ff7_party.h"

/* Developer-only, emulation-thread ABI. Requires the party-access feature.
 * Activation allocates Expansion 1 records but creates no characters. Publish
 * copies a validated host roster into that allocation. It never edits native
 * records, guest byte-sized party IDs, alias tables, equipment or inventories.
 * Republish/unpublish/activation/savestate restore invalidate prior pointers.
 * Publish only after the game's resident code and equipment tables are loaded.
 * Callers must unpublish on save/scene/card ownership changes; this module is
 * not yet connected to gameplay slot selection or the card metadata adapter.
 */
FF7PartyResult ff7_party_access_publish(const FF7PartyState* state);
void ff7_party_access_unpublish(void);
/* Native IDs0..8 resolve to native records; added IDs resolve independently.
 * Returns0 unless a valid roster is published and all code guards still match.
 * Guest IDs9/10 are NOT accepted here as independent storage identities. */
uint32_t ff7_party_access_record(uint16_t identity);
/* Capture extra record changes from guest enhancement memory transactionally.
 * Native records are never copied into the extra roster. This is not a save
 * lifecycle adapter; the caller must coordinate scene/slot/rewind ownership. */
FF7PartyResult ff7_party_access_snapshot(FF7PartyState* state);

/* Function filters extend ONLY a0>=0x100 calls:
 * GetCharacterName(0x800257CC): a0=extra ID; v0=record+0x10. Success clobbers
 * a0=id*4, at=0x800491D0+id*4, v1=0x8009C748, as the original addressing
 * sequence would; v0 is redirected to enhancement memory.
 * GetPartySlotArmorMateriaSlots(0x80025668), Weapon...(0x800256DC): a0>=0x100
 * means extra ID instead of the STOCK party-slot0..2 ABI. Success sets at to
 * extra record+0x1D/0x1C, v1 to0x80071E4D/0x800738BC, and v0 to v1 plus
 * armorID*36/weaponID*44. a0 and all other GPRs are unchanged.
 * The runtime returns PC to ra on a consumed call. Error on an extended query:
 * consume, v0=0, preserve all other GPRs. All a0<0x100 calls execute stock code,
 * including flashback characterID10. No stock menu caller is converted yet.
 */
#endif
