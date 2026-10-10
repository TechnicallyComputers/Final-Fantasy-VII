#include "ff7_party_limit.h"
#include <stddef.h>
/* Mod-authored balance. IDs96..102 occupy verified unused limit entries;
 * actions20/21 are the owner's existing Sephiroth strike/sweep scripts.
 * No animation, attack-record or text asset bytes are embedded.
 * First release defines the two level-1 techniques only. Higher levels and
 * mastery stay unavailable because their thresholds are never published.
 * Future techniques add an entry with an unused reserved ID and native bit
 * (level2: 3/4, level3: 6/7, mastery: 9) plus validated choreography. */
static const FF7LimitPolicy limit_seph={1,{80,160},{8,7,6},320,{140,260,380,500},2,{
 {96,0,20,48,0x13,"Masamune","Powerful sword strike."},
 {97,1,21,32,0x17,"Crescent Arc","Sweep all enemies."}}};
const FF7LimitPolicy* ff7_party_limit_policy(unsigned p){return p==1?&limit_seph:NULL;}
const FF7LimitMove* ff7_party_limit_move_bit(const FF7LimitPolicy*p,unsigned bit){
 if(p)for(unsigned i=0;i<p->move_count&&i<FF7_LIMIT_MOVES;++i)if(p->moves[i].bit==bit)return &p->moves[i];
 return NULL;
}
uint16_t ff7_party_limit_learnable(const FF7LimitPolicy*p){
 uint16_t mask=0;if(p)for(unsigned i=0;i<p->move_count&&i<FF7_LIMIT_MOVES;++i)if(p->moves[i].bit<12)mask|=(uint16_t)(1u<<p->moves[i].bit);
 return mask;
}
void ff7_party_limit_initial(unsigned p,uint8_t record[132]){
 if(!record||!ff7_party_limit_policy(p))return;
 record[14]=1;record[15]=0;for(unsigned i=0x22;i<0x2c;++i)record[i]=0;record[0x22]=1;
}
int ff7_party_limit_canonical(unsigned p,uint8_t record[132]){
 const FF7LimitPolicy*policy=ff7_party_limit_policy(p);
 if(!record||!policy)return 0;
 unsigned stored=record[0x22]|record[0x23]<<8,learned=(stored&ff7_party_limit_learnable(policy))|1u;
 unsigned level=record[14];int changed=learned!=stored;
 if(level<1||level>4||!(learned>>(3*(level-1))&7)){changed|=level!=1||record[15]!=0;level=1;record[15]=0;}
 record[14]=(uint8_t)level;record[0x22]=(uint8_t)learned;record[0x23]=(uint8_t)(learned>>8);
 return changed;
}
