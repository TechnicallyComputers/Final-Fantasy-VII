#ifndef FF7_PARTY_PROJECTION_H
#define FF7_PARTY_PROJECTION_H
#include <stddef.h>
#include <stdint.h>

enum { FF7_NATIVE_SAVE_BYTES = 4340, FF7_NATIVE_FILE_BYTES = 8192,
       FF7_NATIVE_SAVE_HEADER = 512, FF7_NATIVE_ACTIVE_OFFSET = 0x4f8,
       FF7_NATIVE_STORED_OFFSET = 0xcad };

/* The original SAVEMENU CRC routine covers bytes4..4339, starts atFFFF,
 * uses polynomial1021 (MSB first), and complements its16-bit result. */
uint16_t ff7_native_save_checksum(const uint8_t* save);
int ff7_native_save_valid(const uint8_t* save, size_t size);
/* Project only proved party/preview fields. Native records, inventory, story,
 * location and map bytes are preserved. Input is a private outgoing copy;
 * live guest records/party are never temporarily replaced. */
int ff7_native_save_project(uint8_t* save, size_t size,
                            const uint8_t fallback[3]);
#endif
