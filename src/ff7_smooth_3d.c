#include "mod_plugins.h"
#include "pgxp.h"

/* PGXP with CPU propagation; precise culling stays off so the game's own
 * NCLIP results are unchanged. The request is session-scoped (pgxp.h). */
static void ff7_smooth_3d_activate(void) {
    pgxp_mod_request(1, 1, 0);
}

PSX_MOD_CONSTRUCTOR(ff7_register_smooth_3d) {
    (void)psx_mod_register_activation_plugin("ff7.smooth-3d", ff7_smooth_3d_activate);
}
