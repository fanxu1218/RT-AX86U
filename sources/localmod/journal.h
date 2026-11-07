/* SPDX-License-Identifier: MIT
 * Bounded diagnostic history. This never owns plugin checkpoints or UU data.
 * Damaged slots/pending writes are preserved read-only, not silently repaired.
 */
#ifndef LOCALMOD_JOURNAL_H
#define LOCALMOD_JOURNAL_H
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include "sha256.h"
#define LM_OPERATION "/tmp/.localmod/last-operation"
#define LM_JOURNAL_LIMIT 32
#define LM_JOURNAL_BYTES 12288
#define LM_HEALTH_CAP 16384
#define LM_JOURNAL_RESERVE (128U * 1024U)
typedef struct {
 unsigned long long sequence,start;
 long long epoch;
 long pid;
 int code;
 char boot[37],module[65],kind[16],state[16];
} lm_operation;
typedef struct {
 unsigned long long generation;
 unsigned count;
 int present;
 const char *status;
 lm_operation events[LM_JOURNAL_LIMIT];
} lm_journal;
static int lm_module_safe(const char *s){
 size_t n=strlen(s);if(!n||n>64)return 0;
 for(;*s;s++)if(!((*s>='a'&&*s<='z')||(*s>='A'&&*s<='Z')||(*s>='0'&&*s<='9')||*s=='_'||*s=='-'))return 0;
 return 1;
}
static int lm_state_safe(const char *s){return !strcmp(s,"running")||!strcmp(s,"finished")||!strcmp(s,"interrupted");}
static int lm_kind_safe(const char *s){
 return !strcmp(s,"install")||!strcmp(s,"update")||!strcmp(s,"uninstall")||!strcmp(s,"offline")||!strcmp(s,"recovery")||!strcmp(s,"manual");
}
static int lm_boot_safe(const char *s){
 if(strlen(s)!=36)return 0;
 for(int i=0;i<36;i++)if(i==8||i==13||i==18||i==23){if(s[i]!='-')return 0;}else if(!strchr("0123456789abcdef",s[i]))return 0;
 return 1;
}
static int lm_boot(char out[37]){
 char b[64];int fd=open("/proc/sys/kernel/random/boot_id",O_RDONLY|O_CLOEXEC);if(fd<0)return -1;
 ssize_t n=read(fd,b,sizeof(b)-1);close(fd);if(n<1)return -1;b[n]=0;b[strcspn(b,"\n")]=0;
 if(!lm_boot_safe(b))return -1;memcpy(out,b,37);return 0;
}
static unsigned long long lm_start(long pid){
 if(pid<1||pid>INT_MAX)return 0;
 char path[64],raw[2048];snprintf(path,sizeof(path),"/proc/%ld/stat",pid);
 int fd=open(path,O_RDONLY|O_CLOEXEC);if(fd<0)return 0;ssize_t n=read(fd,raw,sizeof(raw)-1);close(fd);if(n<=0)return 0;
 raw[n]=0;char *p=strrchr(raw,')');if(!p||p[1]!=' ')return 0;p+=2;
 for(int field=3;field<=22;field++){
  char *end=strchr(p,' ');if(!end)return 0;
  if(field==3&&(*p=='Z'||*p=='X'))return 0;
  if(field==22){*end=0;char *tail;errno=0;unsigned long long value=strtoull(p,&tail,10);return !errno&&*p&&!*tail?value:0;}
  p=end+1;
 }
 return 0;
}
static int lm_private_file(int fd,size_t limit){
 struct stat s;return !fstat(fd,&s)&&S_ISREG(s.st_mode)&&s.st_uid==0&&!(s.st_mode&077)&&s.st_nlink==1&&s.st_size>=0&&(uint64_t)s.st_size<limit;
}
static int lm_read_at(int dir,const char *name,char *out,size_t cap){
 int fd=openat(dir,name,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC|O_NOATIME);if(fd<0)return errno==ENOENT?-2:-1;
 if(!lm_private_file(fd,cap)){close(fd);return -1;}
 size_t used=0;ssize_t n;
 while(used<cap-1){n=read(fd,out+used,cap-1-used);if(n<0&&errno==EINTR)continue;if(n<0){close(fd);return -1;}if(!n)break;used+=(size_t)n;}
 close(fd);out[used]=0;return (int)used;
}
static int lm_directory(int parent,const char *name,int create,int private){
 int created=0;if(create){if(!mkdirat(parent,name,0700))created=1;else if(errno!=EEXIST)return -1;}
 int fd=openat(parent,name,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC|O_NOATIME);if(fd<0)return -1;
 struct stat s;if(fstat(fd,&s)||s.st_uid!=0||(s.st_mode&(private?077:022))){close(fd);errno=EPERM;return -1;}
 if(created&&fsync(parent)){close(fd);return -1;}
 return fd;
}
static int lm_journal_dir(int create){
 int jffs=open("/jffs",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(jffs<0)return -1;
 struct stat root,s;int local=-1,dir=-1;
 if(stat("/",&root)||fstat(jffs,&s)||s.st_uid!=0||(s.st_mode&022)||s.st_dev==root.st_dev){errno=EPERM;goto done;}
 if(create){struct statvfs fs;if(fstatvfs(jffs,&fs))goto done;if((uint64_t)fs.f_bavail*fs.f_frsize<LM_JOURNAL_RESERVE){errno=ENOSPC;goto done;}if(fsync(jffs))goto done;}
 local=lm_directory(jffs,".localmod",create,0);if(local<0)goto done;
 dir=lm_directory(local,"operations",create,1);
done:if(local>=0)close(local);close(jffs);return dir;
}
static int lm_event_line(char *out,size_t cap,const lm_operation *e);
static int lm_event_parse(char *line,lm_operation *e){
 char extra;
 int n=sscanf(line,"%llu %lld %36s %64s %15s %15s %d %ld %llu %c",&e->sequence,&e->epoch,e->boot,e->module,e->kind,e->state,&e->code,&e->pid,&e->start,&extra);
 if(!(n==9&&e->epoch>=0&&lm_boot_safe(e->boot)&&lm_module_safe(e->module)&&lm_kind_safe(e->kind)&&lm_state_safe(e->state)&&e->code>=0&&e->code<=255&&e->pid>0&&e->pid<=INT_MAX))return 0;
 char canonical[300];int size=lm_event_line(canonical,sizeof(canonical),e);return size>0&&(size_t)size==strlen(line)+1&&!memcmp(line,canonical,(size_t)size-1);
}
static int lm_event_line(char *out,size_t cap,const lm_operation *e){
 return snprintf(out,cap,"%llu %lld %s %s %s %s %d %ld %llu\n",e->sequence,e->epoch,e->boot,e->module,e->kind,e->state,e->code,e->pid,e->start);
}
static int lm_slot_read(int dir,const char *name,lm_journal *j){
 char raw[LM_JOURNAL_BYTES];int n=lm_read_at(dir,name,raw,sizeof(raw));if(n<0)return n;
 if(n<72||memchr(raw,0,(size_t)n)||strncmp(raw+n-72,"SHA256 ",7)||raw[n-1]!='\n')return -1;
 lm_sha h;unsigned char digest[32];char hex[65];sha_init(&h);sha_add(&h,raw,(size_t)n-72);sha_end(&h,digest);hex_digest(digest,hex);
 if(memcmp(hex,raw+n-65,64))return -1;raw[n-72]=0;
 char *save,*line=strtok_r(raw,"\n",&save),extra;
 if(!line||sscanf(line,"LMOPS1 %llu %u %c",&j->generation,&j->count,&extra)!=2||!j->count||j->count>LM_JOURNAL_LIMIT||j->generation<j->count)return -1;
 char canonical[80];snprintf(canonical,sizeof(canonical),"LMOPS1 %llu %u",j->generation,j->count);if(strcmp(canonical,line))return -1;
 for(unsigned i=0;i<j->count;i++){
  line=strtok_r(NULL,"\n",&save);if(!line||!lm_event_parse(line,&j->events[i])||j->events[i].sequence!=j->generation-j->count+1+i)return -1;
 }
 return strtok_r(NULL,"\n",&save)?-1:0;
}
static void lm_journal_load(int dir,lm_journal *j){
 memset(j,0,sizeof(*j));j->status="ready";
 lm_journal other={0};int a=lm_slot_read(dir,"slot0",j),b=lm_slot_read(dir,"slot1",&other);
 unsigned long long first_generation=!a?j->generation:0;
 if(a&&a!=-2){memset(j,0,sizeof(*j));j->status="corrupt";}
 if(!b&&((a!=0)||other.generation>j->generation)){*j=other;}
 if(a==-1||b==-1)j->status="corrupt";
 /* Both valid slots must be adjacent generations. Duplicate snapshots also
  * indicate a damaged/modified store; neither may be discarded automatically. */
 if(!a&&!b&&(first_generation>other.generation?first_generation-other.generation:other.generation-first_generation)!=1)j->status="corrupt";
 if((!a&&b==-2&&j->generation!=1)||(!b&&a==-2&&j->generation!=1))j->status="corrupt";
 j->present=!(a==-2&&b==-2);
 struct stat st;if(!fstatat(dir,"pending",&st,AT_SYMLINK_NOFOLLOW))j->status="write-interrupted";
 else if(errno!=ENOENT)j->status="store-invalid";
 int clone=fcntl(dir,F_DUPFD_CLOEXEC,0);DIR *d=clone>=0?fdopendir(clone):NULL;
 if(!d){if(clone>=0)close(clone);j->status="unavailable";return;}
 struct dirent *e;unsigned seen=0;
 while((e=readdir(d))){if(++seen>8){j->status="store-invalid";break;}
  if(strcmp(e->d_name,".")&&strcmp(e->d_name,"..")&&strcmp(e->d_name,"slot0")&&strcmp(e->d_name,"slot1")&&strcmp(e->d_name,"lock")&&strcmp(e->d_name,"pending")){j->status="store-invalid";break;}}
 closedir(d);
 if(!j->status)j->status="ready";
}
static int lm_lock(int dir,int writer){
 int fd=openat(dir,"lock",(writer?O_RDWR|O_CREAT:O_RDONLY)|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC,0600);
 if(fd<0)return errno==ENOENT&&!writer?-2:-1;
 if(!lm_private_file(fd,1)){close(fd);errno=EPERM;return -1;}
 if(flock(fd,(writer?LOCK_EX:LOCK_SH)|LOCK_NB)){close(fd);return -1;}return fd;
}
static void lm_journal_read(lm_journal *j){
 memset(j,0,sizeof(*j));int dir=lm_journal_dir(0);
 if(dir<0){j->status=errno==ENOENT?"empty":"store-invalid";return;}
 int lock=lm_lock(dir,0);
 if(lock==-1){j->status=errno==EWOULDBLOCK?"busy":"store-invalid";close(dir);return;}
 lm_journal_load(dir,j);
 if(!strcmp(j->status,"ready")){
  struct statvfs fs;if(fstatvfs(dir,&fs))j->status="unavailable";
  else if((uint64_t)fs.f_bavail*fs.f_frsize<LM_JOURNAL_RESERVE)j->status="space-low";
 }
 if(lock>=0)close(lock);close(dir);
}
static int lm_write_all(int fd,const void *value,size_t n){
 const char *p=value;while(n){ssize_t w=write(fd,p,n);if(w<0&&errno==EINTR)continue;if(w<=0)return -1;p+=w;n-=(size_t)w;}return 0;
}
static const char *lm_journal_append(lm_operation *event){
 int dir=lm_journal_dir(1);if(dir<0)return errno==ENOSPC?"space-low":"store-invalid";
 int lock=lm_lock(dir,1);if(lock<0){const char *s=errno==EWOULDBLOCK?"busy":"store-invalid";close(dir);return s;}
 lm_journal j;lm_journal_load(dir,&j);const char *status=j.status;
 if(strcmp(status,"ready"))goto done;
 struct statvfs fs;if(fstatvfs(dir,&fs)){status="unavailable";goto done;}
 if((uint64_t)fs.f_bavail*fs.f_frsize<LM_JOURNAL_RESERVE){status="space-low";goto done;}
 if(j.generation==ULLONG_MAX){status="store-invalid";goto done;}
 event->sequence=++j.generation;
 if(j.count==LM_JOURNAL_LIMIT){memmove(j.events,j.events+1,sizeof(j.events[0])*(LM_JOURNAL_LIMIT-1));j.count--;}
 j.events[j.count++]=*event;
 char raw[LM_JOURNAL_BYTES];int used=snprintf(raw,sizeof(raw),"LMOPS1 %llu %u\n",j.generation,j.count);
 for(unsigned i=0;i<j.count;i++){int n=lm_event_line(raw+used,sizeof(raw)-(size_t)used,&j.events[i]);if(n<0||(size_t)n>=sizeof(raw)-(size_t)used){status="write-failed";goto done;}used+=n;}
 lm_sha h;unsigned char digest[32];char hex[65];sha_init(&h);sha_add(&h,raw,(size_t)used);sha_end(&h,digest);hex_digest(digest,hex);
 int n=snprintf(raw+used,sizeof(raw)-(size_t)used,"SHA256 %s\n",hex);if(n!=72){status="write-failed";goto done;}used+=n;
 int fd=openat(dir,"pending",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0){status="write-failed";goto done;}
 int failed=lm_write_all(fd,raw,(size_t)used)||fsync(fd);if(close(fd))failed=1;
 /* Never unlink a failed pending write. Last good slots remain untouched. */
 if(failed){status="write-failed";goto done;}
 const char *slot=(j.generation&1)?"slot1":"slot0";
 if(renameat(dir,"pending",dir,slot)||fsync(dir)){status="write-failed";goto done;}
 status="ready";
done:close(lock);close(dir);return status;
}
static int lm_error_safe(const char *s){
 return !strcmp(s,"ready")||!strcmp(s,"space-low")||!strcmp(s,"busy")||!strcmp(s,"store-invalid")||!strcmp(s,"corrupt")||!strcmp(s,"write-interrupted")||!strcmp(s,"write-failed")||!strcmp(s,"unavailable");
}
static int lm_ram_write(const lm_operation *e,const char *error){
 int dir=open("/tmp/.localmod",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(dir<0)return -1;
 struct stat st;if(fstat(dir,&st)||st.st_uid!=0||(st.st_mode&077)){close(dir);return -1;}
 char name[64],raw[512];snprintf(name,sizeof(name),"operation.%ld",(long)getpid());
 int used=snprintf(raw,sizeof(raw),"LMRAM1 %s\n",error);int n=lm_event_line(raw+used,sizeof(raw)-(size_t)used,e);if(n<0||(size_t)n>=sizeof(raw)-(size_t)used){close(dir);return -1;}used+=n;
 int fd=openat(dir,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0){close(dir);return -1;}
 int failed=lm_write_all(fd,raw,(size_t)used);if(close(fd))failed=1;
 if(!failed&&renameat(dir,name,dir,"last-operation")==0){close(dir);return 0;}
 unlinkat(dir,name,0);close(dir);return -1;
}
static int lm_ram_read(lm_operation *e,char error[24]){
 int dir=open("/tmp/.localmod",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC|O_NOATIME);if(dir<0)return 0;
 struct stat st;if(fstat(dir,&st)||st.st_uid!=0||(st.st_mode&077)){close(dir);return 0;}
 char raw[512];int n=lm_read_at(dir,"last-operation",raw,sizeof(raw));close(dir);if(n<1)return 0;
 char *line=strchr(raw,'\n');if(!line)return 0;*line++=0;
 char extra;if(sscanf(raw,"LMRAM1 %23s %c",error,&extra)!=1||!lm_error_safe(error))return 0;
 char *end=strchr(line,'\n');if(!end||end[1])return 0;*end=0;return lm_event_parse(line,e);
}
static int lm_add(char *out,size_t cap,size_t *used,const char *format,...){
 if(*used>=cap)return -1;va_list a;va_start(a,format);int n=vsnprintf(out+*used,cap-*used,format,a);va_end(a);
 if(n<0||(size_t)n>=cap-*used)return -1;*used+=(size_t)n;return 0;
}
static int lm_event_closed(const lm_journal *j,unsigned at){
 const lm_operation *e=&j->events[at];if(strcmp(e->state,"running"))return 0;
 for(unsigned k=at+1;k<j->count;k++){const lm_operation *other=&j->events[k];
  if(e->pid==other->pid&&e->start==other->start&&!strcmp(e->boot,other->boot)&&!strcmp(e->module,other->module)&&!strcmp(e->kind,other->kind))return strcmp(other->state,"running")!=0;
 }return 0;
}
static int lm_event_json(char *out,size_t cap,size_t *used,const lm_operation *e,int persisted,int closed,const char *boot){
 int interrupted=!closed&&lm_boot_safe(boot)&&!strcmp(e->state,"running")&&(strcmp(e->boot,boot)||!e->start||lm_start(e->pid)!=e->start);
 return lm_add(out,cap,used,"{\"module\":\"%s\",\"state\":\"%s\",\"code\":%d,\"epoch\":%lld,\"kind\":\"%s\",\"sequence\":%llu,\"persisted\":%s,\"inferred_interruption\":%s,\"closed\":%s}",e->module,interrupted?"interrupted":e->state,interrupted?1:e->code,e->epoch,e->kind,e->sequence,persisted?"true":"false",interrupted?"true":"false",closed?"true":"false");
}
static int lm_history_json(char *out,size_t cap,char *last,size_t last_cap){
 lm_journal j;lm_journal_read(&j);char boot[37]="",error[24]="ready";lm_boot(boot);
 lm_operation ram,*latest=j.count?&j.events[j.count-1]:NULL;int have_ram=lm_ram_read(&ram,error);
 if(have_ram&&(!latest||(!strcmp(ram.boot,boot)&&(strcmp(error,"ready")||ram.sequence>=latest->sequence))))latest=&ram;
 int persisted=latest&&j.count&&latest->sequence==j.events[j.count-1].sequence&&!strcmp(latest->boot,j.events[j.count-1].boot)&&(latest!=&ram||!strcmp(error,"ready"));
 size_t used=0,last_used=0;if(latest){if(lm_event_json(last,last_cap,&last_used,latest,persisted,0,boot))return -1;}else snprintf(last,last_cap,"null");
 int available=!strcmp(j.status,"ready")||!strcmp(j.status,"empty")||j.count>0;
 if(lm_add(out,cap,&used,"{\"status\":\"%s\",\"available\":%s,\"limit\":%u,\"count\":%u,\"last_write_error\":\"%s\",\"events\":[",j.status,available?"true":"false",LM_JOURNAL_LIMIT,j.count,error))return -1;
 for(unsigned i=j.count;i>0;i--){if(i<j.count&&lm_add(out,cap,&used,","))return -1;if(lm_event_json(out,cap,&used,&j.events[i-1],1,lm_event_closed(&j,i-1),boot))return -1;}
 if(lm_add(out,cap,&used,"]}"))return -1;return (int)used;
}
#endif
