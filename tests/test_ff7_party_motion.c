#include "ff7_party_motion.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line%d: %s\n",__LINE__,#x);abort();}}while(0)
int main(void){
    FF7MotionPose in[30]={0},out,body[30],weapon[30];uint8_t encoded[16384];
    for(unsigned f=0;f<30;++f){
        for(unsigned j=0;j<3;++j)in[f].position[j]=(int16_t)(f*2271u+j*31991u);
        for(unsigned i=0;i<48;++i)for(unsigned j=0;j<3;++j)in[f].angle[i][j]=(uint16_t)((f*213u+i*175u+j*999u)&4095);
    }
    size_t n=ff7_motion_encode(in,30,48,encoded,sizeof encoded);CHECK(n&&n<=sizeof encoded);
    for(unsigned f=0;f<30;++f){CHECK(ff7_motion_decode_frame(encoded,n,48,f,&out));CHECK(!memcmp(&out,&in[f],sizeof out));}
    CHECK(!ff7_motion_decode_frame(encoded,5,48,0,&out));CHECK(!ff7_motion_decode_frame(encoded,n,49,0,&out));
    CHECK(!ff7_motion_decode_frame(encoded,n,48,30,&out));CHECK(!ff7_motion_encode(in,30,48,encoded,32));
    CHECK(!ff7_motion_encode(in,0,48,encoded,sizeof encoded));CHECK(!ff7_motion_synthesize((FF7MotionRole)-1,in,in,body,weapon));
    memset(in,0,sizeof in);in[0].position[1]=-700;
    for(unsigned role=0;role<3;++role){CHECK(ff7_motion_synthesize((FF7MotionRole)role,in,in,body,weapon));
        CHECK(!memcmp(body,weapon,sizeof body));
        if(role==FF7_MOTION_DEATH){CHECK(body[0].angle[0][2]==0&&body[29].angle[0][2]==1024);CHECK(body[29].position[0]==700&&body[29].position[1]==-128);}
    }
    CHECK(ff7_party_motion_policy(1)&&!ff7_party_motion_policy(0)&&!ff7_party_motion_policy(255));
    puts("paired motion codec wraparound/precision,capacity/truncation,procedural endpoints and policy bounds passed");return 0;
}
