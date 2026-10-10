#include "ff7_party_field_assets.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do{if(!(x)){fprintf(stderr,"line%d: %s\n",__LINE__,#x);return 1;}}while(0)
int main(void){
    uint8_t out[1024],raw[]={7,0,0,0,7,'A','B','C',0xee,0xf0,0};
    /* Three literals then a self-ring reference, followed by a literal in a
     * separate flag group. Truncated two-byte references fail closed. */
    raw[0]=6;CHECK(ff7_field_decode_lzs(raw,10,out,sizeof out)==6);CHECK(!memcmp(out,"ABCABC",6));
    CHECK(!ff7_field_decode_lzs(raw,10,out,5));raw[0]=5;CHECK(!ff7_field_decode_lzs(raw,9,out,sizeof out));
    uint8_t script[108]={2,5,1,0,104,0},guests[16];
    for(unsigned i=0;i<32;++i)script[40+2*i]=104;
    for(unsigned i=0;i<16;++i)guests[i]=(uint8_t)(11+i);
    uint8_t* large=malloc(4096);CHECK(large);
    CHECK(ff7_field_append_script(script,sizeof script,guests,16,large,4096)==sizeof script+16*112);
    CHECK(large[2]==17 && large[3]==16 && large[4]==232 && large[5]==4);
    guests[15]=11;CHECK(!ff7_field_append_script(script,sizeof script,guests,16,large,4096));
    guests[15]=26;script[2]=63;CHECK(!ff7_field_append_script(script,sizeof script,guests,16,large,4096));
    script[2]=1;script[40]=0;CHECK(!ff7_field_append_script(script,sizeof script,guests,1,large,4096));
    free(large);puts("bounded LZS ring, truncation/capacity,16 distinct script rows,duplicate/overflow/offset rejection passed");return 0;
}
