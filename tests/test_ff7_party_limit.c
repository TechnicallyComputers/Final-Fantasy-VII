/* Reuse the battle RAM/bridge fixture; this test owns its limit callbacks. */
#define main ff7_battle_fixture_main
#define psx_mod_alloc_guest_memory battle_fixture_alloc
#include "test_ff7_party_battle.c"
#undef psx_mod_alloc_guest_memory
#undef main
int ff7_party_game_ready(void){return 1;}
unsigned ff7_party_game_extra_count(void){return s_count;}
uint8_t ff7_party_game_extra_guest(unsigned i){return i<s_count?(uint8_t)(11+i):255;}
uint32_t psx_mod_alloc_guest_memory(uint32_t n,uint32_t a){if(n==1024&&a==16)return s_alloc_fail?0:0x9f000100u;return battle_fixture_alloc(n,a);}
int psx_mod_register_function_filter_plugin(const char*p,uint32_t a,int(*f)(CPUState*,uint32_t)){CHECK(p&&a&&f);return 1;}
#include "../src/ff7_party_limit.c"
void ff7_test_limit_reset(unsigned n){ff7_test_battle_reset(n);s_profile.limit_policy=1;CHECK(ff7_party_limit_init());}
void ff7_test_limit_hook(uint32_t pc,uint32_t* regs){CPUState cpu;memset(&cpu,0,sizeof cpu);cpu.pc=0x81234560;memcpy(cpu.gpr,regs,sizeof cpu.gpr);
 limit_instruction(&cpu,pc);CHECK(cpu.pc==0x81234560);memcpy(regs,cpu.gpr,sizeof cpu.gpr);}
int ff7_test_limit_filter(uint32_t* regs){CPUState cpu;memset(&cpu,0,sizeof cpu);memcpy(cpu.gpr,regs,sizeof cpu.gpr);int r=limit_name(&cpu,0x80015248);memcpy(regs,cpu.gpr,sizeof cpu.gpr);return r;}
uint32_t ff7_test_limit_data(void){return limit_storage;}
static unsigned limit_half(uint32_t p){return psx_mod_read_byte(p)|psx_mod_read_byte(p+1)<<8;}
int main(void){
 ff7_test_limit_reset(16);CHECK(!ff7_party_limit_policy(0));CHECK(!ff7_party_limit_policy(2));
 uint8_t rec[132],before[132];memset(rec,0xa5,sizeof rec);memcpy(before,rec,sizeof rec);ff7_party_limit_initial(0,rec);CHECK(!memcmp(rec,before,sizeof rec));
 ff7_party_limit_initial(1,rec);CHECK(rec[14]==1&&rec[15]==0&&rec[0x22]==1);for(unsigned i=0x23;i<0x2c;++i)CHECK(!rec[i]);
 for(unsigned i=0;i<sizeof limit_sites/sizeof limit_sites[0];++i){const LimitSite*s=&limit_sites[i];
  for(unsigned j=0;j<13;++j)psx_mod_write_word(s->pc-24+j*4,s->words[j]);
  uint32_t r[32]={0};r[4]=11;r[5]=0;
  if(s->action==L_GET){ff7_test_limit_hook(s->pc,r);CHECK(r[3]==96);r[4]=10;r[3]=127;ff7_test_limit_hook(s->pc,r);CHECK(r[3]==127);}
  psx_mod_write_word(s->pc-4,0);unsigned rejects=s_rejected;ff7_test_limit_hook(s->pc,r);CHECK(s_rejected==rejects+1);
 }
 /* Release preset: Masamune/Crescent Arc only; higher levels and mastery stay unpublished. */
 const FF7LimitPolicy*p=ff7_party_limit_policy(1);ff7_test_limit_reset(16);
 CHECK(p->move_count==2&&ff7_party_limit_learnable(p)==0x3);
 CHECK(ff7_party_limit_move_bit(p,0)->id==96&&ff7_party_limit_move_bit(p,1)->id==97);
 for(unsigned bit=2;bit<12;++bit)CHECK(!ff7_party_limit_move_bit(p,bit));
 uint32_t t=ff7_test_limit_data();
 CHECK(limit_half(t+24)==0xffff&&limit_half(t+26)==0xffff);
 CHECK(limit_half(t+28)==8&&limit_half(t+30)==0xffff);
 for(unsigned i=1;i<3;++i)CHECK(limit_half(t+28+4*i)==0xffff&&limit_half(t+30+4*i)==0xffff);
 for(unsigned id=98;id<103;++id)for(unsigned j=0;j<28;++j)CHECK(psx_mod_read_byte(t+64+(id-96)*28+j)==255);
 {static const uint32_t g[]={0x27bdfed0,0x00a01821,0xafb00118,0x00c08021,0x3c088006,0x25082d50,0x34020004,0xafbf0128,0xafb30124,0xafb20120,0x1482000e,0xafb1011c,0x00002821};
  for(unsigned j=0;j<13;++j)psx_mod_write_word(0x80015248+4*j,g[j]);
  uint32_t r[32]={0};r[4]=3;r[6]=8;for(unsigned id=96;id<104;++id){r[5]=id;CHECK(ff7_test_limit_filter(r)==(id<98));}}
 {const LimitSite*m=NULL;for(unsigned i=0;i<sizeof limit_sites/sizeof limit_sites[0];++i)if(limit_sites[i].action==L_MASTERY)m=&limit_sites[i];
  CHECK(m);for(unsigned j=0;j<13;++j)psx_mod_write_word(m->pc-24+j*4,m->words[j]);
  uint32_t r[32]={0};r[4]=0x9f010000;psx_mod_write_byte(r[4],11);r[7]=0xdb;r[11]=65535;ff7_test_limit_hook(m->pc,r);CHECK(r[7]==0xdb);}
 /* Canonical load: legacy missing bit0, diagnostic higher-level records. */
 memset(rec,0,sizeof rec);rec[14]=1;rec[15]=200;CHECK(ff7_party_limit_canonical(1,rec));CHECK(rec[0x22]==1&&rec[14]==1&&rec[15]==200);
 CHECK(!ff7_party_limit_canonical(1,rec));
 rec[0x22]=0x03;CHECK(!ff7_party_limit_canonical(1,rec));
 memset(rec,0x5a,sizeof rec);rec[14]=3;rec[15]=180;rec[0x22]=0xdb;rec[0x23]=0x02;memcpy(before,rec,sizeof rec);
 CHECK(ff7_party_limit_canonical(1,rec));CHECK(rec[14]==1&&rec[15]==0&&rec[0x22]==0x03&&rec[0x23]==0);
 for(unsigned i=0;i<132;++i)if(i!=14&&i!=15&&i!=0x22&&i!=0x23)CHECK(rec[i]==before[i]);
 rec[14]=0;rec[15]=9;CHECK(ff7_party_limit_canonical(1,rec));CHECK(rec[14]==1&&rec[15]==0);
 rec[14]=5;CHECK(ff7_party_limit_canonical(1,rec));CHECK(rec[14]==1);
 memcpy(before,rec,sizeof rec);CHECK(!ff7_party_limit_canonical(0,rec)&&!memcmp(rec,before,sizeof rec));
 s_alloc_fail=1;CHECK(!ff7_party_limit_init());puts("limit release preset,canonical load,native isolation,allocation failure and every exact guard passed");return 0;
}
