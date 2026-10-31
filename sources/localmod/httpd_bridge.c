/* Local software-center adapter for the exact ASUS 24437 httpd.
 * SPDX-License-Identifier: MIT
 * The vendor server remains responsible for TLS, login, and session validation.
 * Only authenticated software-center requests are relayed to a loopback service.
 */
#define _GNU_SOURCE
#define _LARGEFILE64_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <limits.h>
#include <netinet/in.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

#define HEAD_MAX 8192
#define BODY_MAX (64UL * 1024 * 1024)
#ifndef SC_ROOT
#define SC_ROOT "/jffs/.koolshare"
#endif
static char *(*next_fgets)(char *, int, FILE *);
static int (*next_vfprintf)(FILE *, const char *, va_list);
static size_t (*next_fwrite)(const void *, size_t, size_t, FILE *);
static int (*next_fputs)(const char *, FILE *);
static int (*next_fputc)(int, FILE *);
static int (*next_fgetc)(FILE *);
static int (*next_fclose)(FILE *);
static FILE *(*next_fopen64)(const char *, const char *);
static int (*next_xstat64)(int, const char *, struct stat64 *);
static int (*next_exists)(const char *);
static int *vendor_auth_result, *vendor_url_do_auth;
static struct {
 FILE *stream;
 char method[8], uri[2048], headers[HEAD_MAX], replay[HEAD_MAX];
 size_t replay_at, replay_len, body_len;
 int rejected, suppress, replied;
} request;

/* Other DSOs may use stdio from a constructor before ours runs. Resolve on
 * first interception too, rather than assuming constructor ordering. */
static void resolve(void) {
 static int resolved;
 if(resolved)return;
#define RESOLVE(field, name) field = dlsym(RTLD_NEXT, name)
 RESOLVE(next_fgets,"fgets"); RESOLVE(next_vfprintf,"vfprintf");
 RESOLVE(next_fwrite,"fwrite"); RESOLVE(next_fputs,"fputs");
 RESOLVE(next_fputc,"fputc");
 RESOLVE(next_fgetc,"fgetc");
 RESOLVE(next_fclose,"fclose"); RESOLVE(next_fopen64,"fopen64");
 RESOLVE(next_xstat64,"__xstat64"); RESOLVE(next_exists,"check_if_file_exist");
 vendor_auth_result=dlsym(RTLD_DEFAULT,"auth_result");
 vendor_url_do_auth=dlsym(RTLD_DEFAULT,"url_do_auth");
 resolved=1;
}
__attribute__((constructor)) static void setup(void) {
 resolve();
 /* The adapter belongs only to this server, never to programs it launches. */
 unsetenv("LD_PRELOAD");
}

static int api_uri(const char *p) {
 size_t n=strcspn(p,"?");
 return !strncmp(p,"/_api/",6) || (n==5 && !strncmp(p,"/_api",5)) ||
        (n==8 && !strncmp(p,"/_upload",8)) || !strncmp(p,"/_temp/",7) ||
        !strncmp(p,"/_result/",9) || !strncmp(p,"/_root/",7);
}
static int field(const char *line,const char *name) {
 size_t n=strlen(name); return !strncasecmp(line,name,n) && line[n]==':';
}
static void value(char *dest,size_t capacity,const char *line) {
 const char *s=strchr(line,':'); if(!s){dest[0]=0;return;} s++;
 while(*s==' ' || *s=='\t')s++;
 size_t n=strcspn(s,"\r\n"); if(n>=capacity)n=capacity-1;
 memcpy(dest,s,n);dest[n]=0;
}
static int same_origin(const char *host,const char *origin) {
 if(!*host || !*origin || strchr(host,'/') || strchr(host,'@')) return 0;
 const char *s=!strncmp(origin,"https://",8)?origin+8:
               !strncmp(origin,"http://",7)?origin+7:NULL;
 if(!s)return 0;
 size_t n=strcspn(s,"/?#");
 return n==strlen(host) && !strncasecmp(s,host,n);
}
static int session_cookie(const char *cookies) {
 static const char *names[]={"asus_token=","asus_s_token="};
 for(const char *p=cookies;*p;){
  while(*p==' ' || *p=='\t' || *p==';')p++;
  size_t length=strcspn(p,";");
  for(size_t i=0;i<sizeof(names)/sizeof(names[0]);i++){
   size_t n=strlen(names[i]);
   if(length>n && !strncmp(p,names[i],n))return 1;
  }
  p+=length;
 }
 return 0;
}

char *fgets(char *out,int capacity,FILE *stream) {
 resolve();
 if(capacity<=0){errno=EINVAL;return NULL;}
 if(request.stream==stream && request.replay_at<request.replay_len) {
  char *p=request.replay+request.replay_at, *end=strchr(p,'\n');
  size_t len=end?(size_t)(end-p+1):strlen(p);
  if(len>=(size_t)capacity){errno=EOVERFLOW;return NULL;}
  memcpy(out,p,len);out[len]=0;request.replay_at+=len;return out;
 }
 char *result=next_fgets(out,capacity,stream);
 if(!result || request.stream)return result;
 char method[8],uri[2048],protocol[16];
 if(sscanf(out,"%7s %2047s %15s",method,uri,protocol)!=3 ||
    strncmp(protocol,"HTTP/1.",7) || !api_uri(uri))return result;
 memset(&request,0,sizeof(request));request.stream=stream;
 snprintf(request.method,sizeof(request.method),"%s",method);
 snprintf(request.uri,sizeof(request.uri),"%s",uri);
 if(strcmp(method,"GET") && strcmp(method,"POST"))request.rejected=405;
 size_t path_len=strcspn(uri,"?");
 for(size_t i=0;i<path_len;i++)if(uri[i]=='\\' || uri[i]=='%' || (uri[i]=='.' && i+1<path_len && uri[i+1]=='.'))request.rejected=400;
 char line[4096],host[512]="",origin[1024]="",referer[1024]="",cookie[4096]="";
 size_t used=0,replayed=0;int length_seen=0,ended=0;
 while(next_fgets(line,sizeof(line),stream)) {
  size_t len=strlen(line);
  if(!len || line[len-1]!='\n' || used+len+3>=HEAD_MAX){request.rejected=431;break;}
  if(!strcmp(line,"\r\n") || !strcmp(line,"\n")){ended=1;break;}
  if(line[0]==' ' || line[0]=='\t'){request.rejected=400;break;}
  if(field(line,"Host")){if(*host)request.rejected=400;value(host,sizeof(host),line);}
  if(field(line,"Origin"))value(origin,sizeof(origin),line);
  if(field(line,"Referer"))value(referer,sizeof(referer),line);
  if(field(line,"Cookie"))value(cookie,sizeof(cookie),line);
  if(field(line,"Transfer-Encoding") || field(line,"Expect"))request.rejected=400;
  if(field(line,"Content-Length")) {
   char number[64],*end;value(number,sizeof(number),line);errno=0;
   unsigned long n=strtoul(number,&end,10);
   if(length_seen++ || !*number || *end || errno || n>BODY_MAX)request.rejected=413;
   else request.body_len=n;
  }
  if(field(line,"Kauth-Need") ||
     field(line,"Kauth-Success") || field(line,"Connection") ||
     field(line,"Content-Length") || field(line,"Transfer-Encoding") || field(line,"Expect"))continue;
  memcpy(request.headers+used,line,len);used+=len;
  memcpy(request.replay+replayed,line,len);replayed+=len;
 }
 request.headers[used]=0;
 if(!ended)request.rejected=400;
 /* Native HTTPS sessions use asus_s_token; the vendor still validates the
  * token and its transport. This is only an exact cookie-name presence gate. */
 if(!session_cookie(cookie))request.rejected=401;
 if(!strcmp(method,"POST") && !same_origin(host,*origin?origin:referer))request.rejected=403;
 /* Serialize writes across online/offline installers and configuration RPCs.
  * Reads and native UU endpoints stay available during a checkpoint/recovery. */
 struct stat checkpoint,store;
 if(!request.rejected && !strcmp(method,"POST") &&
    (lstat("/jffs/.localmod/plugin-txn/active",&checkpoint)==0 ||
     (lstat("/jffs/.localmod/plugin-txn",&store)==0&&!S_ISDIR(store.st_mode))))request.rejected=423;
 memcpy(request.replay+replayed,"\r\n",3);request.replay_len=replayed+2;
 /* index.asp uses the stock authenticated MIME handler. No auth exception is added. */
 snprintf(out,(size_t)capacity,"GET /index.asp HTTP/1.0\r\n");return out;
}

static void error_reply(FILE *stream,int code) {
 char discard[4096];size_t left=request.body_len;
 while(left){size_t got=fread(discard,1,left<sizeof(discard)?left:sizeof(discard),stream);
  if(!got)break;left-=got;}
 request.body_len=0;
 char buf[256];
 int len=snprintf(buf,sizeof(buf),"HTTP/1.0 %d Error\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: 20\r\n\r\n{\"error\":\"rejected\"}",code);
 next_fwrite(buf,1,(size_t)len,stream);
}
static int send_all(int fd,const void *data,size_t length) {
 const char *p=data;
 while(length){ssize_t n=send(fd,p,length,MSG_NOSIGNAL);if(n<0 && errno==EINTR)continue;
  if(n<=0)return -1;p+=n;length-=(size_t)n;}return 0;
}
static void relay(FILE *stream) {
 int fd=socket(AF_INET,SOCK_STREAM,0);
 if(fd<0){error_reply(stream,503);return;}
 int reuse=1;setsockopt(fd,SOL_SOCKET,SO_REUSEADDR,&reuse,sizeof(reuse));
 /* Linux 4.1 reserves source ports below 1024 for privileged callers. */
 if(bindresvport(fd,NULL)){close(fd);error_reply(stream,503);return;}
 struct timeval timeout={120,0};
 setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));
 setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
 struct sockaddr_in target={.sin_family=AF_INET,.sin_port=htons(3032)};
 inet_pton(AF_INET,"127.0.0.1",&target.sin_addr);
 if(connect(fd,(struct sockaddr *)&target,sizeof(target))<0){close(fd);error_reply(stream,503);return;}
 char head[HEAD_MAX+2400];
 int n=snprintf(head,sizeof(head),"%s %s HTTP/1.0\r\n%sContent-Length: %zu\r\nConnection: close\r\n\r\n",request.method,request.uri,request.headers,request.body_len);
 if(n<0 || n>=(int)sizeof(head) || send_all(fd,head,(size_t)n)){close(fd);error_reply(stream,503);return;}
 char chunk[8192];
 while(request.body_len){size_t want=request.body_len<sizeof(chunk)?request.body_len:sizeof(chunk);size_t got=fread(chunk,1,want,stream);
  request.body_len-=got;
  if(!got || send_all(fd,chunk,got)){close(fd);error_reply(stream,503);return;}}
 int received=0;ssize_t got;
 while((got=recv(fd,chunk,sizeof(chunk),0))>0){received=1;next_fwrite(chunk,1,(size_t)got,stream);}
 close(fd);if(!received)error_reply(stream,503);
}
static int bridge_print(FILE *stream,const char *format,va_list args) {
 resolve();
 if(request.stream==stream){
  va_list copy;va_copy(copy,args);char preview[96];int count=vsnprintf(preview,sizeof(preview),format,copy);va_end(copy);
  if(request.suppress)return count;
  if(!request.replied && !strncmp(preview,"HTTP/1.",7)) {
   request.replied=1;
   if(request.rejected)error_reply(stream,request.rejected);
   else if(!vendor_auth_result || !vendor_url_do_auth ||
           *vendor_auth_result!=0 || *vendor_url_do_auth!=1 ||
           (!strstr(preview," 200 ")))error_reply(stream,401);
   else relay(stream);
   request.suppress=1;return count;
  }
 }
 return next_vfprintf(stream,format,args);
}
int vfprintf(FILE *stream,const char *format,va_list args){return bridge_print(stream,format,args);}
int fprintf(FILE *stream,const char *format,...){va_list args;va_start(args,format);int n=bridge_print(stream,format,args);va_end(args);return n;}
size_t fwrite(const void *p,size_t size,size_t count,FILE *stream){
 resolve();
 if(request.stream==stream && request.suppress)return count;
 return next_fwrite(p,size,count,stream);
}
int fputs(const char *s,FILE *stream){resolve();if(request.stream==stream && request.suppress)return 0;return next_fputs(s,stream);}
int fputc(int c,FILE *stream){resolve();if(request.stream==stream && request.suppress)return (unsigned char)c;return next_fputc(c,stream);}
int fgetc(FILE *stream){
 resolve();
 /* The authenticated index MIME handler probes for trailing POST bytes even
  * though its replayed Content-Length is zero. Keep the original body for
  * relay(), which owns its consumption after native authentication. */
 if(request.stream==stream && !request.replied){errno=EAGAIN;return EOF;}
 return next_fgetc(stream);
}
int fclose(FILE *stream){resolve();if(request.stream==stream)memset(&request,0,sizeof(request));return next_fclose(stream);}

static const char *mapped(const char *path,char *dest,size_t size) {
 const char *name=path;
 if(!strncmp(name,"/www/",5))name+=5;
 if(strstr(name,"..") || strchr(name,'\\'))return NULL;
 if(!strncmp(name,"Module_",7) && !strchr(name,'/'))
  snprintf(dest,size,SC_ROOT "/webs/%s",name);
 else if(!strncmp(name,"res/",4))snprintf(dest,size,SC_ROOT "/%s",name);
 else return NULL;
 return dest;
}
FILE *fopen64(const char *path,const char *mode){
 resolve();
 FILE *f=next_fopen64(path,mode);if(f || mode[0]!='r')return f;
 char dest[PATH_MAX];const char *p=mapped(path,dest,sizeof(dest));return p?next_fopen64(p,mode):NULL;
}
int __xstat64(int version,const char *path,struct stat64 *st){
 resolve();
 int ret=next_xstat64(version,path,st);if(!ret)return ret;
 char dest[PATH_MAX];const char *p=mapped(path,dest,sizeof(dest));return p?next_xstat64(version,p,st):ret;
}
int check_if_file_exist(const char *path){
 resolve();
 int ret=next_exists?next_exists(path):0;if(ret)return ret;
 char dest[PATH_MAX];const char *p=mapped(path,dest,sizeof(dest));
 if(!p)return ret;FILE *f=next_fopen64(p,"r");if(!f)return 0;next_fclose(f);return 1;
}
