/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include "health.h"
int main(int argc,char **argv) {
 if(geteuid()!=0)return 1;
 if(argc==1){char out[LM_HEALTH_CAP];int n=lm_health_json(out,sizeof(out));return n<0 || fwrite(out,1,(size_t)n,stdout)!=(size_t)n;}
 if((argc!=5&&argc!=6) || strcmp(argv[1],"record") || !lm_module_safe(argv[2]) ||
    (strcmp(argv[3],"running")&&strcmp(argv[3],"finished")&&strcmp(argv[3],"interrupted")))return 2;
 char *end;long code=strtol(argv[4],&end,10);if(!*argv[4]||*end||code<0||code>255)return 2;
 const char *kind=argc==6?argv[5]:"manual";if(!lm_kind_safe(kind))return 2;
 lm_operation e={0};e.epoch=(long long)time(NULL);if(e.epoch<0)e.epoch=0;
 if(lm_boot(e.boot))return 1;
 snprintf(e.module,sizeof(e.module),"%s",argv[2]);snprintf(e.kind,sizeof(e.kind),"%s",kind);snprintf(e.state,sizeof(e.state),"%s",argv[3]);e.code=(int)code;
 e.pid=(long)getppid();const char *owner=getenv("LOCALMOD_OPERATION_OWNER");
 if(owner&&*owner){errno=0;char *tail;long pid=strtol(owner,&tail,10);if(errno||*tail||pid<1||pid>INT_MAX)return 2;e.pid=pid;}
 e.start=lm_start(e.pid);
 const char *error=lm_journal_append(&e);lm_ram_write(&e,error);
 if(strcmp(error,"ready")){fprintf(stderr,"operation history: %s; plugin/UU data untouched\n",error);return 1;}return 0;
}
