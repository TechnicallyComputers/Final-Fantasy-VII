#ifndef FF7_PARTY_LIMIT_H
#define FF7_PARTY_LIMIT_H
#include <stdint.h>
enum {FF7_LIMIT_UNCHANGED=0,FF7_LIMIT_SEPHIROTH=1,FF7_LIMIT_MOVES=7};
typedef struct FF7LimitMove {uint8_t id,bit,action,power,targets;const char*name;const char*description;} FF7LimitMove;
typedef struct FF7LimitPolicy {unsigned id;uint16_t kills[2],uses[3],master_kills;uint32_t divisor[4];FF7LimitMove moves[7];} FF7LimitPolicy;
const FF7LimitPolicy* ff7_party_limit_policy(unsigned id);
/* New-game defaults only. Canonical load separately adds first-technique bit0
 * to legacy matching-policy records, preserving every other progression byte. */
void ff7_party_limit_initial(unsigned policy,uint8_t record[132]);
int ff7_party_limit_init(void);
void ff7_party_limit_restore(void);
#endif
