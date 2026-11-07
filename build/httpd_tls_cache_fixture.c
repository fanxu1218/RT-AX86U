/* Test-only observation; never change TLS/cache policy or record identifiers.
 * SSL_CTX_ctrl statistics constants are the public OpenSSL 1.1.1 ABI.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <malloc.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int SSL_accept(void *ssl){
 static int (*real_accept)(void *);
 static void *(*get_ctx)(const void *);
 static long (*ctrl)(void *,int,long,void *);
 static long (*get_timeout)(const void *);
 static int (*reused)(const void *);
 static unsigned count;
 if(!real_accept){real_accept=dlsym(RTLD_NEXT,"SSL_accept");get_ctx=dlsym(RTLD_NEXT,"SSL_get_SSL_CTX");ctrl=dlsym(RTLD_NEXT,"SSL_CTX_ctrl");get_timeout=dlsym(RTLD_NEXT,"SSL_CTX_get_timeout");reused=dlsym(RTLD_NEXT,"SSL_session_reused");}
 if(!real_accept)return -1;
 int result=real_accept(ssl);
 if(result==1 && get_ctx && ctrl && get_timeout && reused){
  void *ctx=get_ctx(ssl);struct mallinfo m=mallinfo();char b[512],phase[24]="setup";
  int source=open("/tmp/httpd-tls-phase",O_RDONLY|O_CLOEXEC);if(source>=0){ssize_t n=read(source,phase,sizeof(phase)-1);close(source);if(n>0)phase[n]=0;}
  if(strspn(phase,"abcdefghijklmnopqrstuvwxyz0123456789_")!=strlen(phase))strcpy(phase,"invalid");
  int n=snprintf(b,sizeof(b),"TLS_CACHE phase=%s accepts=%u sessions=%ld capacity=%ld mode=%ld timeout_seconds=%ld reused=%d arena_bytes=%u live_allocator_bytes=%u free_allocator_bytes=%u mmap_bytes=%u\n",phase,++count,ctrl(ctx,20,0,NULL),ctrl(ctx,43,0,NULL),ctrl(ctx,45,0,NULL),get_timeout(ctx),reused(ssl),(unsigned)m.arena,(unsigned)m.uordblks,(unsigned)m.fordblks,(unsigned)m.hblkhd);
  int fd=open("/tmp/httpd-tls-cache.log",O_CREAT|O_WRONLY|O_APPEND|O_CLOEXEC,0600);if(fd>=0){write(fd,b,(size_t)n);close(fd);}
 }
 return result;
}
