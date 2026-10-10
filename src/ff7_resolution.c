#include "mod_plugins.h"

#include <stdlib.h>
#include <string.h>

#define PACKAGE "ff7.enhancement.resolution"
#define FEATURE "internal-resolution"

/* Session-scoped request: the runtime clears it before each activation, keeps
 * the player's saved setting, and lets PSX_INTERNAL_RESOLUTION override. */
static void ff7_resolution_activate(void) {
    char option[16];
    if (!psx_mod_option_value(PACKAGE, FEATURE, "resolution", option, sizeof option))
        strcpy(option, "1080");
    (void)psx_mod_set_internal_resolution((uint32_t)strtoul(option, NULL, 10));
}

PSX_MOD_CONSTRUCTOR(ff7_register_resolution) {
    (void)psx_mod_register_activation_plugin("ff7.resolution", ff7_resolution_activate);
}
