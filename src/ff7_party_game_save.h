#ifndef FF7_PARTY_GAME_SAVE_H
#define FF7_PARTY_GAME_SAVE_H
/* Installs the gameplay codec and allocates snapshot-owned pending packets.
 * The developer-only transport is a separate feature. */
int ff7_party_game_save_init(void);
void ff7_party_game_save_restore(void);
#endif
