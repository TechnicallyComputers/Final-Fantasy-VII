#ifndef FF7_PARTY_LIMIT_H
#define FF7_PARTY_LIMIT_H
#include <stdint.h>
/* FF7_LIMIT_MOVES is the reserved attack-ID capacity (IDs96..102), not the
 * number of techniques a policy defines; move_count says that. */
enum {FF7_LIMIT_UNCHANGED=0,FF7_LIMIT_SEPHIROTH=1,FF7_LIMIT_MOVES=7,FF7_LIMIT_FIRST_ID=96,FF7_LIMIT_NONE=0xffff};
typedef struct FF7LimitMove {uint8_t id,bit,action,power,targets;const char*name;const char*description;} FF7LimitMove;
/* Native learning thresholds: kills[] unlock bits3/6, uses[] unlock bits1/4/7.
 * A threshold whose technique is absent from moves[] is never written; the
 * guest table keeps 0xFFFF, which the original learner treats as unavailable.
 * master_kills unlocks bit9 only when the policy defines a bit9 technique. */
typedef struct FF7LimitPolicy {unsigned id;uint16_t kills[2],uses[3],master_kills;uint32_t divisor[4];unsigned move_count;FF7LimitMove moves[FF7_LIMIT_MOVES];} FF7LimitPolicy;
const FF7LimitPolicy* ff7_party_limit_policy(unsigned id);
const FF7LimitMove* ff7_party_limit_move_bit(const FF7LimitPolicy* policy,unsigned bit);
/* Learned-bit mask of every technique the policy defines. */
uint16_t ff7_party_limit_learnable(const FF7LimitPolicy* policy);
/* New-game defaults only. */
void ff7_party_limit_initial(unsigned policy,uint8_t record[132]);
/* Load canonicalization for a registered policy: adds first-technique bit0,
 * drops learned bits the policy does not define, and returns a selected level
 * without a learned technique to level1 with an empty gauge (the native level
 * change also clears the gauge). Kills and use counters are preserved.
 * Returns nonzero when the record changed. */
int ff7_party_limit_canonical(unsigned policy,uint8_t record[132]);
int ff7_party_limit_init(void);
void ff7_party_limit_restore(void);
#endif
