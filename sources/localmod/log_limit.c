/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/wait.h>
#include "bounded_log.h"
int main(int argc,char **argv){
 if(argc==3 && !strcmp(argv[1],"--tee") && (!strcmp(argv[2],"install") || !strcmp(argv[2],"offline"))){
  char buffer[4096];int failed=0;for(;;){ssize_t n=read(0,buffer,sizeof(buffer));if(n<0 && errno==EINTR)continue;if(n<=0)break;if(lm_log_write(argv[2],buffer,(size_t)n))failed=1;
   if(!strcmp(argv[2],"offline") && lm_log_write("offline-backup",buffer,(size_t)n))failed=1;
  }return failed?1:0;
 }
 if(argc==4 && !strcmp(argv[1],"--sink")){
  char *end;long fd=strtol(argv[3],&end,10);if(*end || fd<0 || fd>65535)return 2;
  char buffer[4096];int failed=0;for(;;){ssize_t n=read((int)fd,buffer,sizeof(buffer));if(n<0 && errno==EINTR)continue;if(n<=0)break;if(lm_log_write(argv[2],buffer,(size_t)n))failed=1;}
  close((int)fd);return failed?1:0;
 }
 if(argc<3 || (strcmp(argv[1],"bootstrap") && strcmp(argv[1],"skipd")))return 2;
 if(lm_log_write(argv[1],"",0))return 1;
 if(lm_capture_log(argv[1]))return 1;
 if(!strcmp(argv[1],"bootstrap"))setenv("LOCALMOD_BOOTSTRAP_LOGGING","1",1);
 execv(argv[2],argv+2);return 127;
}
