#include "mod_plugins.h"
#include "gpu.h"

#include <string.h>

#define PACKAGE "ff7.enhancement.renderer"
#define FEATURE "enhanced-renderer"

/* FIELD.BIN, BATTLE.X and WORLD.BIN share 0x800A0000. These words are
 * independently read from the NTSC-U owner's images (FIELD.BIN after gzip
 * decoding; BATTLE.X identical on all three discs and unchanged in RAM for
 * the whole battle). Classify the live image instead of carrying a host scene
 * flag across loads or restores.
 * Fields keep their authored 4:3 bitmap until a real tile and camera adapter
 * can expose its available artwork. Battles keep 4:3 because their authored
 * ground meshes end inside the native-wide margins (nothing is culled there;
 * the uncovered pixels would be black wedges). The world map presents wide. */
static int ff7_image_is(const uint32_t signature[8]) {
    for (uint32_t i = 0; i < 8u; ++i)
        if (psx_mod_read_word(0x800a0000u + i * 4u) != signature[i])
            return 0;
    return 1;
}

static int ff7_authored_43_scene(void) {
    static const uint32_t field_signature[8] = {
        0x00000000u, 0x01d801e0u, 0x800a21a4u, 0x800a21b8u,
        0x800a21ccu, 0x800a21e0u, 0x800a21f4u, 0x800a2208u
    };
    static const uint32_t battle_signature[8] = {
        0x00000000u, 0x00001114u, 0x0000001du, 0x0000001fu,
        0x00003721u, 0x00060022u, 0x04120026u, 0x00000a21u
    };
    if (!psx_mod_game_started()) return 1;
    return ff7_image_is(field_signature) || ff7_image_is(battle_signature);
}

static void ff7_renderer_activate(void) {
    char option[32];
    uint32_t width = 16u;
    int fit = 1;
    if (psx_mod_option_value(PACKAGE, FEATURE, "aspect", option, sizeof option)) {
        if (strcmp(option, "16:9") == 0) fit = 0;
        else if (strcmp(option, "21:9") == 0) { width = 21u; fit = 0; }
        else if (strcmp(option, "32:9") == 0) { width = 32u; fit = 0; }
    }
    (void)psx_mod_set_fixed_display_aspect(width, 9u);
    if (fit) (void)psx_mod_set_adaptive_display_aspect(0u, 0u);
    gpu_ws_set_native_scene_predicate(ff7_authored_43_scene);
    psx_mod_set_native_wide_projection_correction(1);

    /* Precision (src/ff7_smooth_3d.c), texture filtering
     * (src/ff7_texture_filter.c) and internal resolution (src/ff7_resolution.c)
     * are their own packages so each applies to the original 4:3 presentation. */
}

PSX_MOD_CONSTRUCTOR(ff7_register_enhanced_renderer) {
    (void)psx_mod_register_activation_plugin("ff7.renderer", ff7_renderer_activate);
}
