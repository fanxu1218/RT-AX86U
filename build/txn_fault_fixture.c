/* SPDX-License-Identifier: MIT -- test only, never staged in firmware. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
static int (*real_rename)(const char *,const char *);
static int (*real_fsync)(int);
static ssize_t (*real_write)(int,const void *,size_t);
static ssize_t (*real_read)(int,void *,size_t);
__attribute__((constructor))static void load(void){real_rename=dlsym(RTLD_NEXT,"rename");real_fsync=dlsym(RTLD_NEXT,"fsync");real_write=dlsym(RTLD_NEXT,"write");real_read=dlsym(RTLD_NEXT,"read");unsetenv("LD_PRELOAD");}
static int mode(const char *want){if(access("/tmp/txn-fault-armed",F_OK))return 0;char b[80]={0};int fd=open("/tmp/txn-fault-mode",O_RDONLY);if(fd<0)return 0;real_read(fd,b,sizeof(b)-1);close(fd);b[strcspn(b,"\r\n")]=0;return !strcmp(b,want);}
static void gate(const char *point){int fd=open("/tmp/txn-fault-gate",O_WRONLY|O_CREAT|O_TRUNC,0600);if(fd>=0){real_write(fd,point,strlen(point));close(fd);}for(;;)pause();}
int rename(const char *a,const char *b){
 if(mode("checkpoint")&&!strcmp(b,"/jffs/.localmod/plugin-txn/active/ready"))gate("checkpoint-not-sealed");
 if(mode("before-commit")&&!strcmp(b,"/jffs/.localmod/plugin-txn/active/committed"))gate("commit-not-sealed");
 return real_rename(a,b);
}
int fsync(int fd){int r=real_fsync(fd);char proc[80],p[4096];snprintf(proc,sizeof(proc),"/proc/self/fd/%d",fd);ssize_t n=readlink(proc,p,sizeof(p)-1);if(n<0)return r;p[n]=0;
 if(!r&&!strcmp(p,"/jffs/.localmod/plugin-txn/active")){
  if(mode("after-commit")&&!access("/jffs/.localmod/plugin-txn/active/committed",F_OK))gate("commit-sealed");
  if(mode("recover-center")&&!access("/jffs/.localmod/plugin-txn/active/failed-center",F_OK)&&access("/jffs/.koolshare",F_OK))gate("recovery-center-quarantined");
 }
 if(!r&&!strcmp(p,"/jffs/.localmod/plugin-txn")&&mode("committed-cleanup")&&access("/jffs/.localmod/plugin-txn/active",F_OK))gate("committed-record-detached-before-cleanup");
 return r;
}
ssize_t write(int fd,const void *b,size_t n){
 if(mode("space-replay")&&n>=18&&!memcmp(b,"set zzzz_recovery_",18)&&access("/tmp/safety-release",F_OK)){
  int mark=open("/tmp/txn-fault-gate",O_WRONLY|O_CREAT|O_TRUNC,0600);if(mark>=0){real_write(mark,"before-large-database-record",28);close(mark);}
  while(access("/tmp/safety-release",F_OK))usleep(10000);
 }
 if(mode("no-space")){char proc[80],p[4096];snprintf(proc,sizeof(proc),"/proc/self/fd/%d",fd);ssize_t count=readlink(proc,p,sizeof(p)-1);if(count>=0){p[count]=0;const char *prefix="/jffs/.localmod/plugin-txn/active/center/";if(!strncmp(p,prefix,strlen(prefix))){errno=ENOSPC;return -1;}}}
 return real_write(fd,b,n);
}
ssize_t read(int fd,void *b,size_t n){ssize_t r=real_read(fd,b,n);if(r>=4&&!memcmp(b,"set ",4)&&mode("recover-database"))gate("database-replay-partially-acknowledged");return r;}
