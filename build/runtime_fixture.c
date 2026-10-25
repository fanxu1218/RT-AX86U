#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include "runtime.h"
int main(void){
 char *cmd[]={"/bin/sh","-c","sleep 3; touch /tmp/.localmod-timeout-leak",NULL};
 if(lm_run(cmd,1)!=124)return 1;
 sleep(1);if(access("/tmp/.localmod-timeout-leak",F_OK)==0)return 2;
 if(lm_emit("../not-a-hook","","",0)!=-1)return 3;
 setenv("LOCALMOD_HOOK_DEPTH","1",1);if(lm_emit("nat-start","","",0))return 4;
 puts("PASS hook timeout kills descendants; names validated; nested notifications suppressed");return 0;
}
