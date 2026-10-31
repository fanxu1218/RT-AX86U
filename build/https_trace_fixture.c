/* Test-only metadata tracing; no credentials or response bodies recorded. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
static void trace(const char *fmt,...) {
 int before=errno;
 if(access("/tmp/https-trace-quiet",F_OK)==0&&access("/tmp/https-fault-mode",F_OK)!=0){errno=before;return;}
 errno=before;
 int saved=errno;char line[240];va_list a;va_start(a,fmt);int n=vsnprintf(line,sizeof(line),fmt,a);va_end(a);
 int fd=open("/tmp/https-relay-trace",O_WRONLY|O_APPEND|O_CREAT,0600);
 if(fd>=0){if(n>0&&n<(int)sizeof(line))write(fd,line,(size_t)n);close(fd);}errno=saved;
}
static int backend(int fd){struct sockaddr_in p;socklen_t n=sizeof(p);int e=errno;int ok=!getpeername(fd,(struct sockaddr*)&p,&n)&&p.sin_family==AF_INET&&ntohs(p.sin_port)==3032;errno=e;return ok;}
static struct {int header,injected;} state[64];
int connect(int fd,const struct sockaddr *p,socklen_t n){
 static int(*next)(int,const struct sockaddr*,socklen_t);if(!next)next=dlsym(RTLD_NEXT,"connect");
 int result=next(fd,p,n),saved=errno;
 if(!result&&fd>=0&&fd<64&&backend(fd))memset(&state[fd],0,sizeof(state[fd]));errno=saved;return result;
}
ssize_t recv(int fd,void *data,size_t size,int flags){
 static ssize_t(*next)(int,void*,size_t,int);if(!next)next=dlsym(RTLD_NEXT,"recv");
 int is_backend=backend(fd);char mode[40]={0};
 if(is_backend&&fd>=0&&fd<64){
  int file=open("/tmp/https-fault-mode",O_RDONLY);if(file>=0){read(file,mode,sizeof(mode)-1);close(file);}
  if(!state[fd].injected&&(!strcmp(mode,"before")||(!strcmp(mode,"after")&&state[fd].header))){
   state[fd].injected=1;trace("INJECT_EINTR phase=%s fd=%d\n",mode,fd);errno=EINTR;return -1;
  }
  if(!strcmp(mode,"signal")&&state[fd].header){
   file=open("/tmp/https-recv-ready",O_WRONLY|O_CREAT|O_EXCL,0600);if(file>=0){write(file,"ready\n",6);close(file);}
  }
 }
 ssize_t n=next(fd,data,size,flags);int e=errno;
 if(is_backend){int header=n>=5&&!memcmp(data,"HTTP/",5);if(header&&fd>=0&&fd<64)state[fd].header=1;trace("recv fd=%d requested=%zu returned=%zd errno=%d header=%d\n",fd,size,n,n<0?e:0,header);}errno=e;return n;
}
unsigned alarm(unsigned seconds){static unsigned(*next)(unsigned);if(!next)next=dlsym(RTLD_NEXT,"alarm");unsigned n=next(seconds);trace("native_alarm seconds=%u previous=%u\n",seconds,n);return n;}
size_t fwrite(const void *data,size_t size,size_t count,FILE *f){
 static size_t(*next)(const void*,size_t,size_t,FILE*);if(!next)next=dlsym(RTLD_NEXT,"fwrite");
 size_t n=next(data,size,count,f);int e=errno;
 trace("fwrite stream=%p size=%zu count=%zu returned=%zu error=%d errno=%d\n",f,size,count,n,ferror(f),e);errno=e;return n;
}
int SSL_write(void *ssl,const void *data,int size){
 static int(*next)(void*,const void*,int);if(!next)next=dlsym(RTLD_NEXT,"SSL_write");
 int n=next(ssl,data,size),e=errno;trace("SSL_write ssl=%p requested=%d returned=%d errno=%d\n",ssl,size,n,e);errno=e;return n;
}
int SSL_shutdown(void *ssl){
 static int(*next)(void*);if(!next)next=dlsym(RTLD_NEXT,"SSL_shutdown");
 int n=next(ssl),e=errno;trace("SSL_shutdown ssl=%p returned=%d errno=%d\n",ssl,n,e);errno=e;return n;
}
