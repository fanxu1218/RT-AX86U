/* Test-only interposer: fault only the owned history pending/rename boundary. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
static int suffix(int fd,const char *tail){
 char p[64],b[512];snprintf(p,sizeof(p),"/proc/self/fd/%d",fd);ssize_t n=readlink(p,b,sizeof(b)-1);if(n<0)return 0;b[n]=0;
 size_t k=strlen(tail);return (size_t)n>=k&&!strcmp(b+n-k,tail);
}
static int mode(const char *expected){
 char b[64];int fd=open("/tmp/history-fault-mode",O_RDONLY|O_CLOEXEC);if(fd<0)return 0;ssize_t n=read(fd,b,sizeof(b)-1);close(fd);if(n<0)return 0;b[n]=0;return !strcmp(b,expected);
}
static void cut(void){
 ssize_t (*next_write)(int,const void *,size_t)=dlsym(RTLD_NEXT,"write");
 int fd=open("/tmp/history-cut-ready",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd>=0){next_write(fd,"ready",5);close(fd);}
 for(;;)sleep(1);
}
ssize_t write(int fd,const void *p,size_t n){
 static ssize_t (*next)(int,const void *,size_t);static int partial;
 if(!next)next=dlsym(RTLD_NEXT,"write");
 if(suffix(fd,"/.localmod/operations/pending")&&mode("partial")){
  if(!partial++){size_t take=n>17?17:n;return next(fd,p,take);}errno=ENOSPC;return -1;
 }return next(fd,p,n);
}
int fsync(int fd){
 static int (*next)(int);if(!next)next=dlsym(RTLD_NEXT,"fsync");int result=next(fd);
 if(!result&&suffix(fd,"/.localmod/operations/pending")&&mode("cut-before-rename"))cut();return result;
}
int renameat(int from,const char *old,int to,const char *name){
 static int (*next)(int,const char *,int,const char *);if(!next)next=dlsym(RTLD_NEXT,"renameat");
 int owned=!strcmp(old,"pending")&&suffix(from,"/.localmod/operations");
 if(owned&&mode("rename-fail")){errno=ENOSPC;return -1;}
 int result=next(from,old,to,name);if(!result&&owned&&mode("cut-after-rename"))cut();return result;
}
