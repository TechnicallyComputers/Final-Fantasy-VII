#ifndef FF7_LZS_H
#define FF7_LZS_H

#include <stddef.h>
#include <stdint.h>

/* Independently implemented from SCUS-94163's original MIPS routine.
 * source includes the four-byte compressed length. On success gpr contains
 * every register effect of SystemLzsDecompress, including caller temporaries.
 * Host buffers must be distinct. Guest overlap is modeled as physical RAM:
 * later input reads observe previous output stores, including unread input.
 * On failure callers discard the temporary output and execute the original.
 */
int ff7_lzs_decode(const uint8_t *source, size_t size, uint8_t *output,
                  size_t capacity, uint32_t source_address,
                  uint32_t output_address, uint32_t gpr[32], size_t *written);

#endif
