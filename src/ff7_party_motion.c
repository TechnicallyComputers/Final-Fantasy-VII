#include "ff7_party_motion.h"
#include <string.h>
#include <math.h>
typedef struct Bits {const uint8_t* in;uint8_t* out;size_t bit,capacity;int ok;} Bits;
static uint32_t get(Bits* b,unsigned n){
    if(!b->ok || n>16 || b->bit+n>b->capacity){b->ok=0;return 0;}
    uint32_t v=0;for(unsigned i=0;i<n;++i,++b->bit)v=(v<<1)|((b->in[b->bit/8]>>(7-b->bit%8))&1);return v;
}
static int signed_bits(Bits* b,unsigned n){uint32_t v=get(b,n);return (v&(1u<<(n-1)))?(int)v-(int)(1u<<n):(int)v;}
static void put(Bits* b,unsigned n,int value){
    if(!b->ok || b->bit+n>b->capacity){b->ok=0;return;}
    for(unsigned i=n;i;--i,++b->bit)if(((unsigned)value>>(i-1))&1)b->out[b->bit/8]|=(uint8_t)(1u<<(7-b->bit%8));
}
static unsigned half(const uint8_t* b){return b[0]|((unsigned)b[1]<<8);}
int ff7_motion_decode_frame(const uint8_t* in,size_t n,unsigned rotations,unsigned frame,FF7MotionPose* out){
    if(!in || !out || n<5 || !rotations || rotations>FF7_MOTION_ROTATIONS)return 0;
    unsigned frames=half(in),bytes=half(in+2),key=in[4];
    if(!frames || frames>4096 || frame>=frames || (key!=0&&key!=2&&key!=4) || bytes>n-5)return 0;
    Bits b={in+5,NULL,0,bytes*8u,1};FF7MotionPose p;memset(&p,0,sizeof p);
    for(unsigned j=0;j<3;++j)p.position[j]=(int16_t)signed_bits(&b,16);
    for(unsigned j=0;j<rotations*3;++j)p.angle[j/3][j%3]=(uint16_t)((signed_bits(&b,12-key)*(1<<key))&4095);
    for(unsigned f=1;f<=frame && b.ok;++f){
        for(unsigned j=0;j<3;++j){unsigned width=get(&b,1)?16:7;p.position[j]=(int16_t)((unsigned)p.position[j]+signed_bits(&b,width));}
        for(unsigned j=0;j<rotations*3;++j)if(get(&b,1)){
            unsigned width=get(&b,3);int delta;
            if(!width)delta=-1;
            else if(width==7)delta=signed_bits(&b,12-key);
            else {delta=signed_bits(&b,width);delta+=delta<0?-(1<<(width-1)):1<<(width-1);}
            p.angle[j/3][j%3]=(uint16_t)((p.angle[j/3][j%3]+delta*(1<<key))&4095);
        }
    }
    if(!b.ok)return 0;
    *out=p;return 1;
}
size_t ff7_motion_encode(const FF7MotionPose* poses,unsigned frames,unsigned rotations,uint8_t* out,size_t capacity){
    if(!poses || !out || capacity<5 || !frames || frames>4096 || !rotations || rotations>FF7_MOTION_ROTATIONS)return 0;
    memset(out,0,capacity);Bits b={NULL,out+5,0,(capacity-5)*8,1};
    for(unsigned j=0;j<3;++j)put(&b,16,poses[0].position[j]);
    for(unsigned j=0;j<rotations*3;++j)put(&b,12,poses[0].angle[j/3][j%3]);
    for(unsigned f=1;f<frames && b.ok;++f){
        for(unsigned j=0;j<3;++j){int d=(int16_t)((unsigned)poses[f].position[j]-(unsigned)poses[f-1].position[j]);
            unsigned width=(d>=-64&&d<=63)?7:16;put(&b,1,width==16);put(&b,width,d);}
        for(unsigned j=0;j<rotations*3;++j){int d=(poses[f].angle[j/3][j%3]-poses[f-1].angle[j/3][j%3])&4095;
            if(d>=2048)d-=4096;
            put(&b,1,d!=0);if(d){put(&b,3,7);put(&b,12,d);}}
    }
    size_t bytes=(b.bit+7)/8,total=(bytes+8)&~(size_t)3;
    if(!b.ok || bytes>65535 || total>capacity)return 0;
    out[0]=(uint8_t)frames;out[1]=(uint8_t)(frames>>8);out[2]=(uint8_t)bytes;out[3]=(uint8_t)(bytes>>8);return total;
}
static void roll(FF7MotionPose* p,int angle,int down){
    double r=angle*(6.28318530717958647692/4096.0),c=cos(r),s=sin(r);
    int x=p->position[0],y=p->position[1];
    p->position[0]=(int16_t)lround(c*x-s*y);p->position[1]=(int16_t)(lround(s*x+c*y)+down);
    /* Original resident RotMatrix8003BF8C uses Rx*Ry*Rz. Pre-multiply
     * a world Z roll and re-extract that convention, so the separate weapon
     * root receives the same rigid transform as the body, not a local twist. */
    const double units=6.28318530717958647692/4096.0;
    double ax=p->angle[0][0]*units,ay=p->angle[0][1]*units,az=p->angle[0][2]*units;
    double cx=cos(ax),sx=sin(ax),cy=cos(ay),sy=sin(ay),cz=cos(az),sz=sin(az);
    double row0[3]={cy*cz,-cy*sz,sy};
    double row1[3]={cx*sz+sx*sy*cz,cx*cz-sx*sy*sz,-sx*cy};
    double row2[3]={sx*sz-cx*sy*cz,sx*cz+cx*sy*sz,cx*cy};
    double m00=c*row0[0]-s*row1[0],m01=c*row0[1]-s*row1[1],m02=c*row0[2]-s*row1[2];
    double m12=s*row0[2]+c*row1[2];
    if(m02>1)m02=1;
    if(m02< -1)m02=-1;
    ay=asin(m02);
    if(fabs(cos(ay))>1e-8){ax=atan2(-m12,row2[2]);az=atan2(-m01,m00);}
    else {ax=atan2(row2[1],s*row0[1]+c*row1[1]);az=0;}
    p->angle[0][0]=(uint16_t)((int)lround(ax/units)&4095);
    p->angle[0][1]=(uint16_t)((int)lround(ay/units)&4095);
    p->angle[0][2]=(uint16_t)((int)lround(az/units)&4095);
}
int ff7_motion_synthesize(FF7MotionRole role,const FF7MotionPose* body,const FF7MotionPose* weapon,FF7MotionPose* bodies,FF7MotionPose* weapons){
    if((unsigned)role>FF7_MOTION_DEFEND || !body || !weapon || !bodies || !weapons)return 0;
    for(unsigned f=0;f<FF7_MOTION_FRAMES;++f){
        bodies[f]=*body;weapons[f]=*weapon;
        int angle=0,down=0,triangle=f<15?(int)f:29-(int)f;
        if(role==FF7_MOTION_LOW_HP){angle=56+triangle;down=28+triangle/2;}
        else if(role==FF7_MOTION_DEATH){
            /* Smooth rigid collapse about the model's floor origin. This is
             * intentionally a procedural starting pose for visual review. */
            double t=f/29.0;t=t*t*(3.0-2.0*t);angle=(int)lround(1024*t);down=(int)lround(-128*t);
        }else {angle=-24;down=triangle/3;}
        roll(&bodies[f],angle,down);roll(&weapons[f],angle,down);
    }
    return 1;
}
const FF7PartyMotionPolicy* ff7_party_motion_policy(unsigned policy){
    static const FF7PartyMotionPolicy seph={1,48,51420,0xb30ba230u,{0,0,5},{0,0,4},{1,15,11},35388,35392};
    return policy==seph.policy?&seph:NULL;
}
