#include "mod_plugins.h"

/* Stable minification for proven 3D polygons; untracked UI stays nearest.
 * A session reset restores the player's configured filter (mod_plugins.h). */
static void ff7_texture_filter_activate(void) {
    psx_mod_set_texture_filter(2);
}

PSX_MOD_CONSTRUCTOR(ff7_register_texture_filter) {
    (void)psx_mod_register_activation_plugin("ff7.texture-filter", ff7_texture_filter_activate);
}
