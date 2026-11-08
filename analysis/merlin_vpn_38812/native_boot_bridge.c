/* SPDX-License-Identifier: MIT
 * Augment the native Merlin hook framework; never synthesize its user events,
 * postconf processing, VPN dispatch or UU NTP callback. Not staged until its
 * native-library integration and recovery tests pass.
 */
#define _GNU_SOURCE
#include "../../sources/localmod/runtime.h"
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <time.h>
#include <stdint.h>
#include <unistd.h>
#include "../../sources/localmod/bounded_log.h"

#define PREFIX "event.native."
#define MAX_CONTEXTS 256
static void (*next_hook)(char *,int,char *,char *);
static int (*next_eval)(char *const[],const char *,int,int *);
static char *(*next_get)(const char *);
static int (*next_set)(const char *,const char *);
static int guard;
static pid_t context_owner, children[8];
static unsigned child_count;
static char active[512];
static const char *helpers[]={"ks-services-start.sh","ks-services-stop.sh",
 "ks-wan-start.sh","ks-nat-start.sh","ks-mount-start.sh","ks-unmount.sh",NULL};
static void resolve(void){
 if(!next_hook)next_hook=dlsym(RTLD_NEXT,"run_custom_script");
 if(!next_eval)next_eval=dlsym(RTLD_NEXT,"_eval");
 if(!next_get)next_get=dlsym(RTLD_NEXT,"nvram_get");
 if(!next_set)next_set=dlsym(RTLD_NEXT,"nvram_set");
}
static void notice(const char *s){lm_log_write("native-hooks",s,strlen(s));}
static unsigned long long process_time(pid_t pid,char *state){
 char path[80],buf[4096];snprintf(path,sizeof(path),"/proc/%ld/stat",(long)pid);
 FILE *f=fopen(path,"r");if(!f)return 0;
 char *s=fgets(buf,sizeof(buf),f);fclose(f);if(!s)return 0;
 s=strrchr(buf,')');if(!s || s[1]!=' ')return 0;s+=2;
 if(state)*state=*s;
 char *save=NULL,*word=strtok_r(s," ",&save);
 for(unsigned field=3;word;field++,word=strtok_r(NULL," ",&save))
  if(field==22)return strtoull(word,NULL,10);
 return 0;
}
static unsigned long long start_time(pid_t pid){return process_time(pid,NULL);}
static int live(pid_t pid,unsigned long long born){
 if(pid<=0)return 1;
 if(kill(pid,0) && errno==ESRCH)return 0;
 char state=0;unsigned long long now=process_time(pid,&state);
 if(state=='Z' || state=='X')return 0;
 return !now || !born || now==born;
}
static int refs(const char *path,int constructing){
 char tmp[600],final[600];snprintf(tmp,sizeof(tmp),"%s/owner.next",path);
 snprintf(final,sizeof(final),"%s/owner",path);
 int fd=open(tmp,O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC|O_NOFOLLOW,0600);
 if(fd<0)return -1;
 if(constructing)dprintf(fd,"%ld %llu\n",(long)getpid(),start_time(getpid()));
 else for(unsigned i=0;i<child_count;i++)
  dprintf(fd,"%ld %llu\n",(long)children[i],start_time(children[i]));
 int result=close(fd);if(!result)result=rename(tmp,final);
 if(result)unlink(tmp);return result;
}
static unsigned collect(void){
 DIR *d=opendir(LM_BASE);if(!d)return MAX_CONTEXTS;
 struct dirent *entry;unsigned count=0;
 while((entry=readdir(d))){
  if(strncmp(entry->d_name,PREFIX,strlen(PREFIX)))continue;
  count++;char path[512],owner[600];struct stat st;
  int n=snprintf(path,sizeof(path),LM_BASE "/%s",entry->d_name);
  if(n<0 || n>=(int)sizeof(path) || lstat(path,&st) || !S_ISDIR(st.st_mode) || st.st_uid!=geteuid() || (st.st_mode&0077))continue;
  snprintf(owner,sizeof(owner),"%s/owner",path);
  int fd=open(owner,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
  if(fd<0 || fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_uid!=geteuid() || (st.st_mode&0077) || st.st_size>512){if(fd>=0)close(fd);continue;}
  FILE *f=fdopen(fd,"r");if(!f){close(fd);continue;}
  long pid;unsigned long long born;int used=0,alive=0,got;
  while((got=fscanf(f,"%ld %llu",&pid,&born))==2){used++;if(pid<=0 || pid>2147483647L || live((pid_t)pid,born))alive=1;}
  int bad=got!=EOF || ferror(f);fclose(f);
  if(alive || bad || used>8)continue;
  // Remove only our known ownership file and helper guard directories.
  for(unsigned i=0;helpers[i];i++){char p[600];snprintf(p,sizeof(p),"%s/%s",path,helpers[i]);rmdir(p);}
  unlink(owner);
  if(!rmdir(path))count--;
 }
 closedir(d);return count;
}
static int managed(const char *s){
 return s && (!strcmp(s,"services-start") || !strcmp(s,"services-stop") ||
  !strcmp(s,"wan-start") || !strcmp(s,"nat-start") ||
  !strcmp(s,"post-mount") || !strcmp(s,"unmount"));
}
static void child(pid_t pid){
 if(pid<=0 || child_count>=8)return;
 for(unsigned i=0;i<child_count;i++)if(children[i]==pid)return;
 children[child_count++]=pid;
}
static void advertise_uu(void){
 // Restore only the native UU menu capability for the user's supported model,
 // territory and router mode; retain every existing Merlin capability word.
 if(!next_get || !next_set)return;
 const char *v=next_get("productid");if(!v || strcmp(v,"RT-AX86U"))return;
 v=next_get("territory_code");if(!v || strncmp(v,"CN/",3))return;
 v=next_get("sw_mode");if(!v || strcmp(v,"1"))return;
 v=next_get("rc_support");char flags[4096];
 if(!v || strlen(v)+10>=sizeof(flags))return;
 snprintf(flags,sizeof(flags)," %s ",v);
 if(strstr(flags," uu_accel "))return;
 snprintf(flags,sizeof(flags),"%s%suu_accel",v,*v?" ":"");
 if(next_set("rc_support",flags))notice("Could not advertise retained native UU capability\n");
}
static void center_dns_directory(const char *config){
 // HND center plugins write snippets here. Native Merlin already owns custom
 // replacement/additions and postconf; insert only this missing directory
 // before its real user postconf, so that the user remains the final editor.
 if(!config || strcmp(config,"/etc/dnsmasq.conf"))return;
 struct stat st;if(stat("/jffs/configs/dnsmasq.d",&st) || !S_ISDIR(st.st_mode))return;
 int fd=open(config,O_RDWR|O_CLOEXEC|O_NOFOLLOW);
 if(fd<0)return;
 if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_uid!=geteuid() || st.st_size>16*1024*1024){close(fd);return;}
 FILE *f=fdopen(fd,"r+");if(!f){close(fd);return;}
 const char *directive="conf-dir=/jffs/configs/dnsmasq.d";size_t size=strlen(directive);
 char *line=NULL;size_t capacity=0;int present=0;
 while(getline(&line,&capacity,f)>0){
  char *p=line;while(*p==' ' || *p=='\t')p++;
  if(!strncmp(p,directive,size) && (!p[size] || p[size]=='\n' || p[size]=='\r' || p[size]==',')){present=1;break;}
 }
 free(line);
 if(!present && !ferror(f) && !fseek(f,0,SEEK_END)){
  if(fprintf(f,"\n%s\n",directive)<0 || fflush(f))notice("Center DNS directory append failed; native postconf retained\n");
 }
 fclose(f);
}
__attribute__((constructor)) static void initialize(void){
 resolve();unsetenv("LD_PRELOAD");
 if(program_invocation_short_name)prctl(PR_SET_NAME,program_invocation_short_name,0,0,0);
}
int _eval(char *const argv[],const char *path,int timeout,int *pid){
 resolve();if(!next_eval){errno=ENOSYS;return -1;}
 const char *name=argv && argv[0]?strrchr(argv[0],'/'):NULL;
 name=name?name+1:(argv?argv[0]:NULL);
 if(lm_enabled() && name && !strcmp(name,"iptables") && argv[1] && argv[2] && argv[3] && !argv[4] &&
    !strcmp(argv[1],"-t") && !strcmp(argv[2],"filter") && !strcmp(argv[3],"-F") && !pid){
  char *a[]={"/usr/sbin/iptables-restore","--localmod-flush-filter",NULL};
  return next_eval(a,path,timeout,pid);
 }
 int result=next_eval(argv,path,timeout,pid),saved=errno;
 if(!result && pid && getpid()==context_owner && argv && argv[0] && !strncmp(argv[0],"/jffs/scripts/",14))child(*pid);
 errno=saved;return result;
}
void run_custom_script(char *name,int timeout,char *arg1,char *arg2){
 resolve();if(!next_hook)return;
 int init=name && !strcmp(name,"init-start");
 int dns=name && !strcmp(name,"dnsmasq.postconf");
 if(guard || !lm_enabled() || getenv("LOCALMOD_HOOK_DEPTH") || (!init && !dns && !managed(name))){next_hook(name,timeout,arg1,arg2);return;}
 // Native callers may pass pointers into nvram_get's reusable buffer. Copy
 // every argument before reading any additional key or invoking bootstrap.
 char *n=strdup(name),*a=arg1?strdup(arg1):NULL,*b=arg2?strdup(arg2):NULL;
 if(!n || (arg1&&!a) || (arg2&&!b)){free(n);free(a);free(b);next_hook(name,timeout,arg1,arg2);return;}
 int prepared=0;
 if(init || !strcmp(n,"services-start")){
  char *cmd[]={"/bin/sh",LM_BOOTSTRAP,init?"prepare":"start",NULL};
  guard=1;prepared=lm_run(cmd,120);guard=0;
  if(!prepared)advertise_uu();
  else notice("Center preparation failed; native hook retained without center augmentation\n");
 }
 const char *flag=next_get?next_get("jffs2_scripts"):NULL;
 if(dns){
  if(!flag || strcmp(flag,"0"))center_dns_directory(a);
  next_hook(n,timeout,a,b);free(n);free(a);free(b);return;
 }
 if(init || prepared || (flag && !strcmp(flag,"0")) || lm_directory(LM_BASE)){
  next_hook(n,timeout,a,b);free(n);free(a);free(b);return;
 }
 if(collect()>=MAX_CONTEXTS){
  notice("Native event contexts full; user hook retained, center helper not added\n");
  next_hook(n,timeout,a,b);free(n);free(a);free(b);return;
 }
 char context[]=LM_BASE "/" PREFIX "XXXXXX";
 const char *prior=getenv("LOCALMOD_EVENT_DIR");char *previous=prior?strdup(prior):NULL;
 if((prior&&!previous) || !mkdtemp(context) || refs(context,1)){
  free(previous);next_hook(n,timeout,a,b);free(n);free(a);free(b);return;
 }
 child_count=0;context_owner=getpid();snprintf(active,sizeof(active),"%s",context);
 setenv("LOCALMOD_EVENT_DIR",context,1);
 struct timespec started,finished;
 int measured=timeout>0 && !clock_gettime(CLOCK_MONOTONIC,&started);
 guard=1;next_hook(n,timeout,a,b);int saved=errno;
 char *cmd[]={"/usr/libexec/localmod/native-center-event.sh",n,a,b,NULL};
 int limit=timeout,allowed=1;
 if(timeout>0){
  if(!measured || clock_gettime(CLOCK_MONOTONIC,&finished))allowed=0;
  else {
   int64_t elapsed=(int64_t)(finished.tv_sec-started.tv_sec)*1000000000LL+finished.tv_nsec-started.tv_nsec;
   if(elapsed<0 || elapsed>=(int64_t)timeout*1000000000LL)allowed=0;
   else limit=timeout-(int)(elapsed/1000000000LL);
  }
 }
 // Preserve the native async/blocking contract. _eval's timeout unit is whole
 // seconds; consume elapsed whole seconds rather than granting a fresh budget.
 // An exhausted positive budget must never become timeout=0 (async).
 int pid=0;
 if(!allowed)notice("Native hook timeout budget exhausted; center helper not started\n");
 else if(next_eval && !next_eval(cmd,NULL,limit,timeout?NULL:&pid)){
  if(!timeout)child(pid);
 }else notice("Center event helper failed or timed out; native user hook was retained\n");
 if(refs(context,0))notice("Native event ownership retained after bookkeeping failure\n");
 context_owner=0;active[0]=0;guard=0;
 if(previous)setenv("LOCALMOD_EVENT_DIR",previous,1);else unsetenv("LOCALMOD_EVENT_DIR");
 free(previous);free(n);free(a);free(b);errno=saved;
}
