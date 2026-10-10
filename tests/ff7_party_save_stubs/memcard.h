#ifndef FF7_PARTY_SAVE_TEST_MEMCARD_H
#define FF7_PARTY_SAVE_TEST_MEMCARD_H
#include <stdint.h>
#define MEMCARD_EXTENSION_MAX 65536
typedef int (*MemcardExtensionLoad)(int, const uint8_t*, const uint8_t*, uint32_t);
typedef int (*MemcardExtensionSave)(int, const uint8_t*, uint8_t*, uint32_t);
void memcard_set_extension_codec(MemcardExtensionLoad load, MemcardExtensionSave save);
#endif
