#ifndef FF7_PARTY_MOTION_H
#define FF7_PARTY_MOTION_H
#include <stddef.h>
#include <stdint.h>
enum {FF7_MOTION_ROTATIONS=48,FF7_MOTION_FRAMES=30};
typedef struct FF7MotionPose {int16_t position[3];uint16_t angle[FF7_MOTION_ROTATIONS][3];} FF7MotionPose;
typedef enum FF7MotionRole {FF7_MOTION_LOW_HP,FF7_MOTION_DEATH,FF7_MOTION_DEFEND} FF7MotionRole;
/* Bounded PSX bitstreams. Angles use one turn=4096; no asset bytes embedded. */
int ff7_motion_decode_frame(const uint8_t*,size_t,unsigned,unsigned,FF7MotionPose*);
size_t ff7_motion_encode(const FF7MotionPose*,unsigned,unsigned,uint8_t*,size_t);
int ff7_motion_synthesize(FF7MotionRole,const FF7MotionPose*,const FF7MotionPose*,FF7MotionPose*,FF7MotionPose*);
typedef struct FF7PartyMotionPolicy {
    unsigned policy,rotations,body_bytes;uint32_t body_crc;
    uint8_t source[3],source_frame[3],target[3];
    uint32_t near_death_script,death_script;
} FF7PartyMotionPolicy;
const FF7PartyMotionPolicy* ff7_party_motion_policy(unsigned policy);
/* Runtime adapter storage is allocator-owned guest RAM, including role state. */
int ff7_party_motion_init(void);
void ff7_party_motion_clear(unsigned slot);
int ff7_party_motion_prepare(unsigned slot,uint32_t model,unsigned policy);
void ff7_party_motion_restore(void);
#endif
