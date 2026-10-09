#include "mod_plugins.h"
#include "cpu_state.h"
#include "ff7_lzs.h"
#include "../psx_symbols.h"

#include <stdlib.h>
#include <string.h>

#define PACKAGE "ff7.enhancement.loading"
#define FEATURE "fast-loading"

static uint8_t *source_buffer, *output_buffer;
static uint32_t source_capacity, output_capacity;
static int decoder_enabled;

#define DECLINE(reason) do { \
    psx_mod_counter_add("ff7.loading.reject_" reason, 1u); \
    goto fallback; \
} while (0)

static int ensure_buffer(uint8_t **buffer, uint32_t *capacity, uint32_t size) {
    uint8_t *replacement;
    if (*capacity >= size) return 1;
    replacement = (uint8_t *)realloc(*buffer, size);
    if (!replacement) return 0;
    *buffer = replacement;
    *capacity = size;
    return 1;
}

static int ff7_lzs_hle(CPUState *cpu, uint32_t address) {
    uint32_t source = cpu->gpr[4], destination = cpu->gpr[5];
    uint32_t source_offset = source & 0x1fffffffu;
    uint32_t output_offset = destination & 0x1fffffffu;
    uint32_t size, registers[32];
    size_t written;
    uint32_t code_hash = 2166136261u;
    (void)address;
    if (!decoder_enabled) return 0;
    for (uint32_t i = 0; i < 0xfcu; i += 4u)
        code_hash = (code_hash ^ psx_mod_read_word(address + i)) * 16777619u;
    if (code_hash != 0x176b8b96u) DECLINE("code");
    /* Main-memory spans only. The decoder models overlapping input/output
     * reads, including physical aliases, without mutating live RAM early. */
    if (source & 3u) DECLINE("alignment");
    if (source_offset > 0x200000u - 4u ||
        output_offset >= 0x200000u ||
        (source >> 29 != 0u && source >> 29 != 4u && source >> 29 != 5u) ||
        (destination >> 29 != 0u && destination >> 29 != 4u && destination >> 29 != 5u))
        DECLINE("span");
    size = psx_mod_read_word(source);
    if (size > 0x200000u - source_offset - 4u) DECLINE("size");
    size += 4u;
    if (!ensure_buffer(&source_buffer, &source_capacity, size) ||
        !ensure_buffer(&output_buffer, &output_capacity, 0x200000u - output_offset))
        DECLINE("allocation");
    for (uint32_t i = 0; i < size; ++i)
        source_buffer[i] = psx_mod_read_byte(source + i);
    memcpy(registers, cpu->gpr, sizeof registers);
    if (!ff7_lzs_decode(source_buffer, size, output_buffer,
                        0x200000u - output_offset, source, destination,
                        registers, &written)) DECLINE("input");
    if (output_offset < 0x34cacu && 0x34bb0u < output_offset + written)
        DECLINE("self_write");
    if (!psx_mod_host_write_ram(destination, output_buffer, (uint32_t)written))
        DECLINE("store");
    memcpy(cpu->gpr, registers, sizeof registers);
    psx_mod_counter_add("ff7.loading.lzs_hle", 1u);
    psx_mod_counter_add("ff7.loading.decoded_bytes", (uint32_t)written);
    return 1;

fallback:
    psx_mod_counter_add("ff7.loading.lzs_fallback", 1u);
    return 0;
}

static void ff7_loading_activate(void) {
    char hle[16];
    /* Host acceleration ends on the first nonloading frame. XA and FMV
     * streaming retain the runtime's original timing and pacing guards. */
    (void)psx_mod_set_load_acceleration(0u, 0u);
    decoder_enabled = !psx_mod_option_value(PACKAGE, FEATURE, "lzs_hle",
                                            hle, sizeof hle) ||
                      strcmp(hle, "true") == 0;
    /* Keep the native CD cadence. Burst delivery produced incomplete battle
     * actors in the opening fight. Host pacing and pure CPU HLE are separate
     * from an eventual verified game-specific asynchronous file-read adapter. */
}

PSX_MOD_CONSTRUCTOR(ff7_register_loading) {
    (void)psx_mod_register_activation_plugin("ff7.loading", ff7_loading_activate);
    (void)psx_mod_register_function_filter_plugin("ff7.loading",
        PSX_FN_SystemLzsDecompress, ff7_lzs_hle);
}
