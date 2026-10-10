#include "ff7_lzs.h"

#include <string.h>

/* Physical aliases refer to the same main RAM. The startup image really does
 * overwrite unread compressed bytes. Resolve subsequent reads through the
 * simulated output stores, just as the original MIPS code sees guest RAM.
 * Separate host scratch buffers leave the guest untouched on a decline. */
static uint8_t input_byte(const uint8_t *source, const uint8_t *output,
                          uint32_t source_address, uint32_t output_address,
                          size_t cursor, size_t count) {
    uint64_t input = (source_address & 0x1fffffffu) + (uint64_t)cursor;
    uint64_t destination = output_address & 0x1fffffffu;
    if (input >= destination && input - destination < count)
        return output[(size_t)(input - destination)];
    return source[cursor];
}

int ff7_lzs_decode(const uint8_t *source, size_t size, uint8_t *output,
                  size_t capacity, uint32_t source_address,
                  uint32_t output_address, uint32_t gpr[32], size_t *written) {
    size_t cursor = 4, count = 0;
    uint32_t flags = 0, remaining = 0, argument = source_address;
    uint32_t end_pointer;
    uint32_t length;
    if (!source || !output || !gpr || !written || size < 4 || size > UINT32_MAX)
        return 0;
    end_pointer = gpr[3];
    length = (uint32_t)source[0] | ((uint32_t)source[1] << 8) |
             ((uint32_t)source[2] << 16) | ((uint32_t)source[3] << 24);
    if (length != size - 4 || source_address > UINT32_MAX - size ||
        capacity > UINT32_MAX || output_address > UINT32_MAX - capacity)
        return 0;

    for (;;) {
        if (!remaining) {
            /* The original branch's delay slot sets t0 even at EOF. */
            remaining = 8;
            if (cursor >= size) break;
            flags = input_byte(source, output, source_address, output_address,
                               cursor++, count);
        }
        if (cursor >= size) break;
        if (flags & 1u) {
            uint8_t literal = input_byte(source, output, source_address,
                                         output_address, cursor++, count);
            if (count >= capacity) return 0;
            output[count++] = literal;
        } else {
            uint32_t token, distance;
            size_t end;
            int64_t reference;
            if (size - cursor < 2) return 0;
            uint8_t first = input_byte(source, output, source_address,
                                       output_address, cursor, count);
            uint8_t second = input_byte(source, output, source_address,
                                        output_address, cursor + 1u, count);
            token = first | ((second & 0xf0u) << 4);
            end = count + (second & 15u) + 3u;
            cursor += 2;
            distance = ((uint32_t)count + 0xfeeu - token) & 0xfffu;
            /* A zero-distance token reads unwritten guest RAM. Decline rather
             * than substitute zeros for memory the original would observe. */
            if (!distance || end > capacity) return 0;
            reference = (int64_t)count - distance;
            end_pointer = output_address + (uint32_t)end;
            /* The retail decoder zero-fills to the initial dictionary origin,
             * even when that is farther than this token's nominal end. */
            while (reference < 0) {
                if (count >= capacity) return 0;
                output[count++] = 0;
                ++reference;
            }
            while (count < end) {
                output[count++] = output[(size_t)reference++];
            }
            argument = output_address + (uint32_t)reference;
        }
        flags >>= 1;
        --remaining;
    }

    /* Publish only after successful decoding; preserve all other registers. */
    gpr[2] = 0;
    gpr[3] = end_pointer;
    gpr[4] = argument;
    gpr[5] = output_address + (uint32_t)count;
    gpr[6] = source_address + (uint32_t)cursor;
    gpr[7] = flags;
    gpr[8] = remaining;
    gpr[9] = output_address;
    gpr[10] = source_address + (uint32_t)size;
    *written = count;
    return 1;
}
