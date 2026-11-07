/* SPDX-License-Identifier: MIT
 * Validate an entire decompressed tar stream before invoking vendor tar.
 * Safe relative symlinks and hardlinks are supported; links may never be
 * extraction parents, chain through other links, or target outside the module.
 */
#define _GNU_SOURCE
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define ENTRIES 8192
#define PATHLEN 512
#define EXPANDED_MAX (128ULL*1024*1024)
#define COMPRESSED_MAX (64ULL*1024*1024)
#ifndef GZIP_PATH
#define GZIP_PATH "/bin/gzip"
#endif
struct member {char name[PATHLEN],target[PATHLEN];char type;};
static struct member *members;
static unsigned count;
static uint64_t expanded;
static double deadline;
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static int readfull(int fd,void *data,size_t n){
 unsigned char *p=data;while(n){double left=deadline-now();if(left<=0)return -1;
  struct pollfd f={.fd=fd,.events=POLLIN};int ready=poll(&f,1,(int)(left*1000)+1);
  if(ready<0 && errno==EINTR)continue;if(ready<=0)return -1;
  ssize_t got=read(fd,p,n);if(got<0 && errno==EINTR)continue;if(got<=0)return -1;
  expanded+=(uint64_t)got;if(expanded>EXPANDED_MAX)return -1;p+=got;n-=(size_t)got;
 }return 0;
}
static int zero(const unsigned char *p,size_t n){for(size_t i=0;i<n;i++)if(p[i])return 0;return 1;}
static int octal(const unsigned char *p,size_t n,uint64_t *value){
 *value=0;size_t i=0;while(i<n && p[i]==' ')i++;
 for(;i<n && p[i]>='0' && p[i]<='7';i++){if(*value>(UINT64_MAX-7)/8)return -1;*value=*value*8+(p[i]-'0');}
 for(;i<n;i++)if(p[i] && p[i]!=' ')return -1;return 0;
}
static int field(char *out,size_t cap,const unsigned char *p,size_t n){
 size_t len=strnlen((const char *)p,n);if(len>=cap)return -1;
 for(size_t i=0;i<len;i++)if(p[i]<32 || p[i]==127 || p[i]=='\\')return -1;
 memcpy(out,p,len);out[len]=0;return 0;
}
static int canonical(char *out,const char *raw){
 if(!*raw || *raw=='/' || strlen(raw)>=PATHLEN)return -1;
 char input[PATHLEN];strcpy(input,raw);char *save=NULL,*part;out[0]=0;
 for(part=strtok_r(input,"/",&save);part;part=strtok_r(NULL,"/",&save)){
  if(!strcmp(part,"."))continue;
  if(!strcmp(part,".."))return -1;
  size_t n=strlen(out),m=strlen(part);if(n+m+2>=PATHLEN)return -1;
  if(n)out[n++]='/';memcpy(out+n,part,m+1);
 }
 return !*out?-1:0;
}
static int normalize_target(char *out,const char *name,const char *link,int hard){
 if(!*link || *link=='/' || strlen(link)>=PATHLEN)return -1;
 char joined[PATHLEN*2];if(hard)snprintf(joined,sizeof(joined),"%s",link);
 else {char base[PATHLEN];strcpy(base,name);char *slash=strrchr(base,'/');if(!slash)return -1;*slash=0;snprintf(joined,sizeof(joined),"%s/%s",base,link);}
 char *save=NULL,*part;out[0]=0;
 for(part=strtok_r(joined,"/",&save);part;part=strtok_r(NULL,"/",&save)){
  if(!strcmp(part,"."))continue;
  if(!strcmp(part,"..")){char *slash=strrchr(out,'/');if(!slash)return -1;*slash=0;continue;}
  size_t n=strlen(out),m=strlen(part);if(n+m+2>=PATHLEN)return -1;
  if(n)out[n++]='/';memcpy(out+n,part,m+1);
 }return !*out?-1:0;
}
static int prefix(const char *p,const char *root){size_t n=strlen(root);return !strncmp(p,root,n) && (!p[n] || p[n]=='/');}
static int check(int fd,const char *expected,char *module){
 unsigned char block[512];int ended=0;uint64_t payload=0;
 while(!ended){
  if(readfull(fd,block,sizeof(block)))return -1;
  if(zero(block,sizeof(block))){if(readfull(fd,block,sizeof(block)) || !zero(block,sizeof(block)))return -1;ended=1;break;}
  uint64_t check_sum,size,mode;unsigned sum=0;
  for(unsigned i=0;i<512;i++)sum+=i>=148 && i<156?' ':block[i];
  if(octal(block+148,8,&check_sum) || check_sum!=sum || octal(block+124,12,&size) || octal(block+100,8,&mode))return -1;
  if((mode&07000) || size>64ULL*1024*1024 || payload+size>EXPANDED_MAX || count>=ENTRIES)return -1;
  char name[PATHLEN],pre[156],raw[PATHLEN],link[PATHLEN];
  if(field(name,sizeof(name),block,100) || field(pre,sizeof(pre),block+345,155) || field(link,sizeof(link),block+157,100))return -1;
  if(*pre){if(strncmp((char *)block+257,"ustar",5))return -1;if(snprintf(raw,sizeof(raw),"%s/%s",pre,name)>=(int)sizeof(raw))return -1;}else strcpy(raw,name);
  if(canonical(name,raw))return -1;
  char type=block[156]?block[156]:'0';if(type!='0' && type!='5' && type!='1' && type!='2')return -1;
  if(type!='0' && size)return -1;
  if(!*module){snprintf(module,65,"%.*s",(int)strcspn(name,"/"),name);
   size_t n=strcspn(name,"/");if(n>64 || !n)return -1;
   for(size_t i=0;i<n;i++)if(!isalnum((unsigned char)module[i]) && module[i]!='_' && module[i]!='-')return -1;
   if(expected && strcmp(module,expected))return -1;
  }
  if(!prefix(name,module) || (!strcmp(name,module) && type!='5'))return -1;
  for(unsigned i=0;i<count;i++)if(!strcmp(name,members[i].name))return -1;
  struct member *m=&members[count++];strcpy(m->name,name);m->type=type;
  if(type=='1' || type=='2'){if(normalize_target(m->target,name,link,type=='1') || !prefix(m->target,module))return -1;}
  payload+=size;uint64_t remain=(size+511)/512*512;
  while(remain){if(readfull(fd,block,sizeof(block)))return -1;remain-=512;}
 }
 /* Consume gzip to verified EOF, rejecting concatenated nonzero tar data. */
 for(;;){double left=deadline-now();if(left<=0)return -1;struct pollfd f={.fd=fd,.events=POLLIN};int ready=poll(&f,1,(int)(left*1000)+1);if(ready<0 && errno==EINTR)continue;if(ready<=0)return -1;
  ssize_t n=read(fd,block,sizeof(block));if(n<0 && errno==EINTR)continue;if(n<0)return -1;if(!n)break;expanded+=(uint64_t)n;if(expanded>EXPANDED_MAX || !zero(block,(size_t)n))return -1;
 }
 if(!count)return -1;
 for(unsigned i=0;i<count;i++){
  struct member *m=&members[i];
  for(unsigned j=0;j<count;j++)if(i!=j && members[j].type!='5'){
   size_t n=strlen(members[j].name);
   if(prefix(m->name,members[j].name) && m->name[n]=='/')return -1;
   if(*m->target && prefix(m->target,members[j].name) && m->target[n]=='/')return -1;
  }
  if(*m->target){int found=0;for(unsigned j=0;j<count;j++)if(!strcmp(m->target,members[j].name)){
    if((members[j].type!='0' && members[j].type!='5') || (m->type=='1' && (members[j].type!='0' || j>=i)))return -1;found=1;
   }
   if(!found)return -1;
  }
 }
 return 0;
}
int main(int argc,char **argv){
 if(argc<2 || argc>3)return 2;
 int archive=open(argv[1],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat st;
 if(archive<0 || fstat(archive,&st) || !S_ISREG(st.st_mode) || st.st_size<=0 || (uint64_t)st.st_size>COMPRESSED_MAX)return 1;
 members=calloc(ENTRIES,sizeof(*members));if(!members)return 1;
 int p[2];if(pipe(p))return 1;pid_t child=fork();
 if(!child){close(p[0]);dup2(archive,0);dup2(p[1],1);close(p[1]);close(archive);execl(GZIP_PATH,"gzip","-dc",(char *)NULL);_exit(127);}
 close(archive);close(p[1]);if(child<0)return 1;
 deadline=now()+20;char module[65]="";int valid=check(p[0],argc==3?argv[2]:NULL,module),status=0;close(p[0]);
 if(valid)kill(child,SIGKILL);
 while(waitpid(child,&status,0)<0){if(errno!=EINTR){valid=-1;break;}}
 free(members);if(valid || !WIFEXITED(status) || WEXITSTATUS(status)){fputs("Unsafe, unsupported, oversized or corrupt plugin archive; not extracted.\n",stderr);return 1;}
 puts(module);return 0;
}
