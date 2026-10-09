#ifndef FF7_PARTY_MENU_H
#define FF7_PARTY_MENU_H
#include <stdint.h>
/* Called by the default-off party-gameplay activation, on the emulation thread.
 * Enhancement memory holds the alias operand, expanded exchange list and PHS
 * portrait backup. No original alias table, inventory or native record changes.
 * Returning zero means allocation failed; the bridge must not publish extras.
 */
int ff7_party_menu_init(void);
/* Prepare a registered member's portrait in the native atlas. Returns its
 * atlas index, or -1 when no supported cell/asset is available. Original
 * portrait copy/draw code remains responsible for its destination slot. */
int ff7_party_menu_prepare_portrait(uint8_t guest);
void ff7_party_menu_restore(void);
#endif
