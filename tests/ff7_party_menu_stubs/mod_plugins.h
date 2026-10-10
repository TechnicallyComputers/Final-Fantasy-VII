#ifndef FF7_PARTY_MENU_TEST_MOD_H
#define FF7_PARTY_MENU_TEST_MOD_H
#include <stdint.h>
struct CPUState;
int psx_mod_register_instruction_plugin(const char*,uint32_t,uint32_t,void (*)(struct CPUState*,uint32_t));
uint32_t psx_mod_alloc_guest_memory(uint32_t,uint32_t);
uint32_t psx_mod_read_word(uint32_t);
uint8_t psx_mod_read_byte(uint32_t);
void psx_mod_write_word(uint32_t,uint32_t);
void psx_mod_write_half(uint32_t,uint16_t);
void psx_mod_write_byte(uint32_t,uint8_t);
int psx_mod_read_disc_file(const char*,void*,uint32_t,uint32_t*);
int psx_mod_disc_file_extent(const char*,uint32_t*,uint32_t*);
void psx_mod_counter_add(const char*,uint32_t);
#define PSX_MOD_CONSTRUCTOR(name) void name(void)
#endif
