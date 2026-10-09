#include "ff7_party_limit.h"
#include <stddef.h>
/* Mod-authored balance. IDs96..102 occupy verified unused limit entries;
 * actions20/21 are the owner's existing Sephiroth strike/sweep scripts.
 * No animation, attack-record or text asset bytes are embedded. */
static const FF7LimitPolicy limit_seph={1,{80,160},{8,7,6},320,{140,260,380,500},{
 {96,0,20,48,0x13,"Masamune","Powerful sword strike."},
 {97,1,21,32,0x17,"Crescent Arc","Sweep all enemies."},
 {98,3,20,64,0x13,"Steel Requiem","Heavy sword strike."},
 {99,4,21,48,0x17,"Nightfall","Heavy sweep of all enemies."},
 {100,6,20,96,0x13,"Heaven's Edge","Devastating sword strike."},
 {101,7,21,64,0x17,"Black Horizon","Devastating sweep."},
 {102,9,21,128,0x17,"One-Winged End","Mastered strike at all foes."}}};
const FF7LimitPolicy* ff7_party_limit_policy(unsigned p){return p==1?&limit_seph:NULL;}
void ff7_party_limit_initial(unsigned p,uint8_t record[132]){
 if(!record||!ff7_party_limit_policy(p))return;
 record[14]=1;record[15]=0;for(unsigned i=0x22;i<0x2c;++i)record[i]=0;record[0x22]=1;
}
