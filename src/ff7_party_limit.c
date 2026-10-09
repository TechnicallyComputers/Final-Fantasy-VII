#include "ff7_party_limit.h"
#include "ff7_party_game.h"
#include "cpu_state.h"
#include "mod_plugins.h"
#include <stddef.h>
#include <string.h>
enum LimitAction {L_GET,L_INIT_ENABLE,L_DIVISOR,L_LEARN_ENABLE,L_KILLS_TABLE,L_USES_TABLE,L_MASTERY,L_COMMAND,L_ACTION,L_MENU_ATTACK,L_ALIAS,L_OFFSET};
typedef struct {uint32_t pc;enum LimitAction action;unsigned reg;uint32_t words[13];} LimitSite;
static const LimitSite limit_sites[]={
#include "ff7_party_limit_sites.inc"
};
enum {LIMIT_STORAGE=1024,LIMIT_ATTACKS=64,LIMIT_NAMES=288,LIMIT_DESCRIPTIONS=512};
static uint32_t limit_storage;
static void sh(uint32_t p,unsigned v){psx_mod_write_byte(p,(uint8_t)v);psx_mod_write_byte(p+1,(uint8_t)(v>>8));}
static const FF7LimitPolicy* policy(uint32_t guest){
 if(guest>255||!ff7_party_game_is_extra((uint8_t)guest))return NULL;
 const FF7PartyProfile*p=ff7_party_game_profile((uint8_t)guest);
 return p?ff7_party_limit_policy(p->limit_policy):NULL;
}
static const FF7LimitMove* move_id(const FF7LimitPolicy*p,unsigned id){
 if(p)for(unsigned i=0;i<p->move_count&&i<FF7_LIMIT_MOVES;++i)if(p->moves[i].id==id)return &p->moves[i];
 return NULL;
}
static unsigned get_limit(const FF7LimitPolicy*p,unsigned bit){
 const FF7LimitMove*m=bit<12?ff7_party_limit_move_bit(p,bit):NULL;return m?m->id:127;
}
static uint32_t attack(unsigned id){return id>=FF7_LIMIT_FIRST_ID&&id<FF7_LIMIT_FIRST_ID+FF7_LIMIT_MOVES?limit_storage+LIMIT_ATTACKS+(id-FF7_LIMIT_FIRST_ID)*28:0;}
static void text(uint32_t dest,const char*s,unsigned capacity){
 unsigned i=0;for(;s[i]&&i+1<capacity;++i)psx_mod_write_byte(dest+i,(uint8_t)((unsigned char)s[i]-32));
 psx_mod_write_byte(dest+i,255);
}
static int site_guard(const LimitSite*s){for(unsigned i=0;i<13;++i)if(psx_mod_read_word(s->pc-24+4*i)!=s->words[i])return 0;return 1;}
static void cache(unsigned guest,uint32_t derived){
 const FF7LimitPolicy*p=policy(guest);uint32_t record=ff7_party_game_record((uint8_t)guest);
 if(!p||!record)return;
 unsigned level=psx_mod_read_byte(record+14);if(level<1||level>4)return;
 for(unsigned i=0;i<3;++i){unsigned id=get_limit(p,(level-1)*3+i);psx_mod_write_byte(derived+0xac+i,(uint8_t)id);
  uint32_t source=attack(id);for(unsigned j=0;j<28;++j)psx_mod_write_byte(derived+0xb4+i*28+j,source?psx_mod_read_byte(source+j):255);
 }
}
static void limit_instruction(CPUState*cpu,uint32_t pc){
 if(!cpu||!limit_storage||!ff7_party_game_ready())return;
 pc=(pc&0x1fffffffu)|0x80000000u;
 const LimitSite*s=NULL;for(unsigned i=0;i<sizeof limit_sites/sizeof limit_sites[0];++i)if(limit_sites[i].pc==pc){s=&limit_sites[i];break;}
 if(!s)return;
 if(!site_guard(s)){psx_mod_counter_add("ff7.party_limit.guard_reject",1);return;}
 uint32_t*r=cpu->gpr;const FF7LimitPolicy*p=NULL;
 switch(s->action){
 case L_GET:p=policy(r[4]);if(p)r[3]=get_limit(p,r[5]);break;
 case L_INIT_ENABLE:p=policy(r[30]);if(p){unsigned level=psx_mod_read_byte(r[19]+14);if(level>=1&&level<=4){cache(r[30],r[16]);r[2]=1;}}break;
 case L_DIVISOR:if(policy(r[30]))r[2]=limit_storage+40-r[4];break;
 case L_LEARN_ENABLE:if(policy(r[9]))r[2]=1;break;
 case L_KILLS_TABLE:if(policy(r[9]))r[2]=limit_storage+24-r[3];break;
 case L_USES_TABLE:if(policy(r[9]))r[2]=limit_storage+28-r[3];break;
 case L_MASTERY:p=policy(psx_mod_read_byte(r[4]));if(ff7_party_limit_move_bit(p,9)&&(r[7]&0xdb)==0xdb&&r[11]>=p->master_kills)r[7]|=0x200;break;
 case L_COMMAND:if(r[5]<3){p=policy(psx_mod_read_byte(0x801636b8+16*r[5]));if(move_id(p,r[3]))r[2]=1;}break;
 case L_ACTION:p=policy(r[22]);if(p){const FF7LimitMove*m=move_id(p,r[18]);if(m)r[2]=m->action;}break;
 case L_MENU_ATTACK:{unsigned slot=psx_mod_read_word(0x801d2410);unsigned guest=s->pc==0x801d1290?r[19]:(slot<3?psx_mod_read_byte(0x8009cbdc+slot):255);
  uint32_t delta=r[3]-0x801d1324u;if(policy(guest)&&delta%28==0&&move_id(policy(guest),delta/28))r[3]=attack(delta/28);break;}
 case L_ALIAS:{uint32_t delta=r[s->reg]-0x800491d0u;if(!(delta&3)&&delta<27*4&&ff7_party_game_is_extra((uint8_t)(delta/4)))r[s->reg]=ff7_party_game_alias_word((uint8_t)(delta/4));break;}
 case L_OFFSET:for(unsigned i=0;i<ff7_party_game_extra_count();++i){uint8_t g=ff7_party_game_extra_guest(i);if(r[s->reg]==33u*g){r[s->reg]=ff7_party_game_record_offset(g)/4;break;}}break;
 }
 psx_mod_counter_add("ff7.party_limit.hook",1);
}
static int limit_name(CPUState*cpu,uint32_t address){
 if(!cpu||!limit_storage||!ff7_party_game_ready()||(address&0x1fffffffu)!=0x15248||cpu->gpr[4]!=3||!move_id(ff7_party_limit_policy(FF7_LIMIT_SEPHIROTH),cpu->gpr[5]))return 0;
 static const uint32_t guard[]={0x27bdfed0,0x00a01821,0xafb00118,0x00c08021,0x3c088006,0x25082d50,0x34020004,0xafbf0128,0xafb30124,0xafb20120,0x1482000e,0xafb1011c,0x00002821};
 for(unsigned i=0;i<13;++i)if(psx_mod_read_word(0x80015248+i*4)!=guard[i])return 0;
 int enabled=0;for(unsigned i=0;i<ff7_party_game_extra_count();++i)if(policy(ff7_party_game_extra_guest(i)))enabled=1;if(!enabled)return 0;
 if(cpu->gpr[6]!=0&&cpu->gpr[6]!=8)return 0;
 cpu->gpr[2]=limit_storage+(cpu->gpr[6]?LIMIT_NAMES:LIMIT_DESCRIPTIONS)+(cpu->gpr[5]-FF7_LIMIT_FIRST_ID)*(cpu->gpr[6]?32:64);return 1;
}
/* Publish a threshold only when the technique it unlocks exists. */
static unsigned threshold(const FF7LimitPolicy*p,unsigned bit,unsigned value){return ff7_party_limit_move_bit(p,bit)?value:FF7_LIMIT_NONE;}
int ff7_party_limit_init(void){
 limit_storage=psx_mod_alloc_guest_memory(LIMIT_STORAGE,16);if(!limit_storage)return 0;
 const FF7LimitPolicy*p=ff7_party_limit_policy(FF7_LIMIT_SEPHIROTH);for(unsigned i=0;i<LIMIT_STORAGE;++i)psx_mod_write_byte(limit_storage+i,255);
 for(unsigned i=0;i<12;++i)psx_mod_write_byte(limit_storage+12+i,(uint8_t)(get_limit(p,i)+128));
 sh(limit_storage+24,threshold(p,3,p->kills[0]));sh(limit_storage+26,threshold(p,6,p->kills[1]));
 for(unsigned i=0;i<3;++i)sh(limit_storage+28+i*4,threshold(p,3*i+1,p->uses[i]));
 for(unsigned i=0;i<4;++i)psx_mod_write_word(limit_storage+40+i*4,p->divisor[i]);
 for(unsigned i=0;i<p->move_count&&i<FF7_LIMIT_MOVES;++i){const FF7LimitMove*m=&p->moves[i];uint32_t a=attack(m->id);if(!a)return 0;
  unsigned ordinal=m->id-FF7_LIMIT_FIRST_ID;
  psx_mod_write_byte(a+2,0);sh(a+4,0);sh(a+8,0xffff);sh(a+10,0xffff);
  psx_mod_write_byte(a+12,m->targets);psx_mod_write_byte(a+13,255);psx_mod_write_byte(a+14,0x11);psx_mod_write_byte(a+15,m->power);sh(a+24,0);
  text(limit_storage+LIMIT_NAMES+ordinal*32,m->name,32);text(limit_storage+LIMIT_DESCRIPTIONS+ordinal*64,m->description,64);
 }
 return 1;
}
void ff7_party_limit_restore(void){/* Immutable guest tables are included in runtime snapshots. */}
PSX_MOD_CONSTRUCTOR(register_ff7_party_limit){
 for(unsigned i=0;i<sizeof limit_sites/sizeof limit_sites[0];++i)(void)psx_mod_register_instruction_plugin("ff7.party-gameplay",limit_sites[i].pc,limit_sites[i].words[6],limit_instruction);
 (void)psx_mod_register_function_filter_plugin("ff7.party-gameplay",0x80015248,limit_name);
}
