/* Test-only TLS and stream metadata; no credentials or payload bytes. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
static void logline(const char *fmt,...){int saved=errno;char b[256];struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);int off=snprintf(b,sizeof(b),"TLS_PROBE t=%ld.%03ld ",t.tv_sec,t.tv_nsec/1000000);va_list a;va_start(a,fmt);int n=vsnprintf(b+off,sizeof(b)-off,fmt,a);va_end(a);if(n>0&&off+n<(int)sizeof(b)){int fd=open("/tmp/httpd-tls-probe.log",O_CREAT|O_WRONLY|O_APPEND|O_CLOEXEC,0600);if(fd>=0){write(fd,b,off+n);close(fd);}}errno=saved;}
int SSL_accept(void *s){static int(*next)(void*);if(!next)next=dlsym(RTLD_NEXT,"SSL_accept");errno=0;int n=next(s);logline("SSL_accept returned=%d errno=%d\n",n,errno);return n;}
int SSL_read(void *s,void *b,int size){static int(*next)(void*,void*,int);static int(*get_error)(const void*,int);static int(*get_fd)(const void*);if(!next){next=dlsym(RTLD_NEXT,"SSL_read");get_error=dlsym(RTLD_NEXT,"SSL_get_error");get_fd=dlsym(RTLD_NEXT,"SSL_get_fd");}errno=0;int n=next(s,b,size),saved=errno,kind=n<=0&&get_error?get_error(s,n):0;struct timeval timeout={0};socklen_t len=sizeof(timeout);int fd=get_fd?get_fd(s):-1;if(fd>=0)getsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,&len);logline("SSL_read size=%d returned=%d errno=%d ssl_error=%d receive_timeout_ms=%ld\n",size,n,saved,kind,timeout.tv_sec*1000+timeout.tv_usec/1000);errno=saved;return n;}
int SSL_write(void *s,const void *b,int size){static int(*next)(void*,const void*,int);if(!next)next=dlsym(RTLD_NEXT,"SSL_write");errno=0;int n=next(s,b,size);logline("SSL_write size=%d returned=%d errno=%d\n",size,n,errno);return n;}
char *fgets(char *out,int size,FILE *f){static char*(*next)(char*,int,FILE*);if(!next)next=dlsym(RTLD_NEXT,"fgets");errno=0;char *r=next(out,size,f);if(!r)logline("fgets fd=%d returned=null errno=%d error=%d eof=%d\n",fileno(f),errno,ferror(f),feof(f));return r;}
