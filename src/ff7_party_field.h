#ifndef FF7_PARTY_FIELD_H
#define FF7_PARTY_FIELD_H
#include <stdint.h>
int ff7_party_field_init(void);
void ff7_party_field_restore(void);
/* Loader-owned allocation bases; permits validated enhancement script/model
 * headers without treating arbitrary expansion addresses as native RAM. */
void ff7_party_field_owned_storage(uint32_t script,uint32_t metadata);
/* Bind an already-created, mod-owned script entity/model to a canonical member.
 * The caller must own that entity; this API does not load or steal a story NPC.
 * Rejects invalid entities/models and entities used by native/other members.
 * Binding lasts until the native per-field entity-map reset and rewinds with
 * guest memory. A future field asset loader owns creation and profile matching. */
int ff7_party_field_bind(uint16_t identity,uint8_t entity);
uint8_t ff7_party_field_entity(uint8_t guest);
#endif
