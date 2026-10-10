#ifndef FF7_PARTY_SAVE_TEST_MOD_PLUGINS_H
#define FF7_PARTY_SAVE_TEST_MOD_PLUGINS_H
#include <stdint.h>
int psx_mod_register_activation_plugin(const char* id, void (*callback)(void));
void psx_mod_counter_add(const char* name, uint32_t delta);
#define PSX_MOD_CONSTRUCTOR(name) void name(void)
#endif
