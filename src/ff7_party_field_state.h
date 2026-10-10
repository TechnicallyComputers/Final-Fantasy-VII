#ifndef FF7_PARTY_FIELD_STATE_H
#define FF7_PARTY_FIELD_STATE_H
#include <stdint.h>
int ff7_party_field_state_init(void);
/* Call end before each field preparation. Commit begin only after all other
 * buffers validate; pass its returned pointer as BA534 a1. Zero rejects. */
void ff7_party_field_state_end(void);
uint32_t ff7_party_field_state_begin(uint32_t native_base,unsigned native_entities,unsigned native_models,unsigned extras);
void ff7_party_field_state_restore(void);
#endif
