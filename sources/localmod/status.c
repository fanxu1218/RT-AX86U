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
 if(argc==1){char out[2048];int n=lm_health_json(out,sizeof(out));return n<0 || fwrite(out,1,(size_t)n,stdout)!=(size_t)n;}
 if(argc!=5 || strcmp(argv[1],"record") || !lm_module_safe(argv[2]) ||
    (strcmp(argv[3],"running")&&strcmp(argv[3],"finished")&&strcmp(argv[3],"interrupted")))return 2;
 char *end;long code=strtol(argv[4],&end,10);if(!*argv[4]||*end||code<0||code>255)return 2;
 struct stat st;if(lstat("/tmp/.localmod",&st)||!S_ISDIR(st.st_mode)||st.st_uid!=0||(st.st_mode&077))return 1;
 char tmp[96];snprintf(tmp,sizeof(tmp),LM_OPERATION ".%ld",(long)getpid());
 int fd=open(tmp,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0)return 1;
 int failed=dprintf(fd,"%lld %s %s %ld\n",(long long)time(NULL),argv[2],argv[3],code)<0;
 if(close(fd))failed=1;
 if(!failed && rename(tmp,LM_OPERATION)==0)return 0;
 unlink(tmp);return 1;
}
