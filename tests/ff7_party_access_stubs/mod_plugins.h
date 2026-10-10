#ifndef FF7_PARTY_ACCESS_TEST_MOD_PLUGINS_H
#define FF7_PARTY_ACCESS_TEST_MOD_PLUGINS_H
#include <stdint.h>
struct CPUState;
typedef int (*PSXModFunctionFilterCallback)(struct CPUState*, uint32_t);
int psx_mod_register_activation_plugin(const char*, void (*)(void));
int psx_mod_register_savestate_plugin(const char*, void (*)(void));
int psx_mod_register_function_filter_plugin(const char*, uint32_t, PSXModFunctionFilterCallback);
void psx_mod_counter_add(const char*, uint32_t);
uint32_t psx_mod_alloc_guest_memory(uint32_t, uint32_t);
uint8_t psx_mod_read_byte(uint32_t);
uint32_t psx_mod_read_word(uint32_t);
void psx_mod_write_byte(uint32_t, uint8_t);
#define PSX_MOD_CONSTRUCTOR(name) void name(void)
#endif
