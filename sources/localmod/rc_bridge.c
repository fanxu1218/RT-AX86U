/* SPDX-License-Identifier: MIT
 * Instrument imported APIs of the exact vendor rc; its machine code is retained.
 * WAN notifications flush at the init wait boundary or at helper process exit.
 */
#define _GNU_SOURCE
#include "runtime.h"
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static char *(*real_get)(const char *);
static int (*real_set)(const char *,const char *);
static char *(*real_strsep)(char **,const char *);
static int (*real_mount)(const char *,const char *,const char *,unsigned long,const void *);
static int (*real_umount)(const char *),(*real_umount2)(const char *,int);
static int (*real_wait)(const sigset_t *,siginfo_t *);
static int (*real_eval)(char *const[],const char *,int,int *);
static int ready,guard,started,start_pending=1;
static char candidate[256],action[32],target[128];static char **service_cursor;
static struct {int unit,state;} wan[64];static unsigned wan_count;
static char unmounts[16][4096];static unsigned unmount_count;
static void resolve(void){
#define R(x,n) if(!x)x=dlsym(RTLD_NEXT,n)
 R(real_get,"nvram_get");R(real_set,"nvram_set");R(real_strsep,"strsep");
 R(real_mount,"mount");R(real_umount,"umount");R(real_umount2,"umount2");
 R(real_wait,"sigwaitinfo");R(real_eval,"_eval");
}
static int init_process(void){
#ifdef LOCALMOD_RC_FIXTURE
 return 1;
#else
 return getpid()==1;
#endif
}
static int runtime_active(void){
 int active=ready && !guard && !getenv("LOCALMOD_HOOK_DEPTH");
 if(active && !lm_enabled()){candidate[0]=action[0]=target[0]=0;service_cursor=NULL;wan_count=0;return 0;}
 return active;
}
static int enabled(void){return runtime_active();}
/* Never call nvram_get for a second key while a vendor argument or return
 * value might point into its shared buffer. Read the script flag in a fresh
 * utility process; the dispatcher checks it again before running user code. */
static int scripts_enabled(void){
 if(!runtime_active())return 0;
 int descriptors[2];if(pipe2(descriptors,O_CLOEXEC))return 0;
 sigset_t block,oldmask;struct sigaction oldchild,def={.sa_handler=SIG_DFL};
 sigemptyset(&block);sigaddset(&block,SIGCHLD);sigprocmask(SIG_BLOCK,&block,&oldmask);
 sigemptyset(&def.sa_mask);sigaction(SIGCHLD,&def,&oldchild);
 pid_t child=fork();char value[16]={0};int status=0,ok=0;
 if(child==0){
  close(descriptors[0]);dup2(descriptors[1],STDOUT_FILENO);close(descriptors[1]);
  sigemptyset(&block);sigprocmask(SIG_SETMASK,&block,NULL);
  execl("/bin/nvram","nvram","get","jffs2_scripts",(char *)NULL);_exit(127);
 }
 close(descriptors[1]);struct pollfd descriptor={.fd=descriptors[0],.events=POLLIN};
 if(child>0 && poll(&descriptor,1,2000)>0){
  ssize_t n=read(descriptors[0],value,sizeof(value)-1);if(n>=0)ok=1;
 }else if(child>0)kill(child,SIGKILL);
 close(descriptors[0]);if(child>0)while(waitpid(child,&status,0)<0 && errno==EINTR){}
 sigaction(SIGCHLD,&oldchild,NULL);sigprocmask(SIG_SETMASK,&oldmask,NULL);
 return ok && WIFEXITED(status) && WEXITSTATUS(status)==0 && value[0]!='0';
}
static void emit(const char *event,const char *a,const char *b,int sync){if(scripts_enabled()){guard++;lm_emit(event,a,b,sync);guard--;}}
static void flush_wan(void){
 static const char *states[]={"init","connecting","connected","disconnected","stopped","disabled","stopping"};
 unsigned n=wan_count;wan_count=0;
 for(unsigned i=0;i<n;i++){char unit[16];snprintf(unit,sizeof(unit),"%d",wan[i].unit);emit("wan-event",unit,states[wan[i].state],0);}
}
static void service_end(void){
 if(*action){emit("service-event-end",action,target,0);action[0]=target[0]=0;}
}
static void child_reset(void){wan_count=unmount_count=0;candidate[0]=action[0]=target[0]=0;service_cursor=NULL;}
__attribute__((constructor)) static void initialize(void){
 resolve();unsetenv("LD_PRELOAD");
 if(program_invocation_short_name)prctl(PR_SET_NAME,program_invocation_short_name,0,0,0);
 pthread_atfork(NULL,NULL,child_reset);atexit(flush_wan);ready=1;
}
char *nvram_get(const char *key){
 resolve();int capture=runtime_active() && init_process() && !service_cursor && key && !strcmp(key,"rc_service");
 char *value=real_get?real_get(key):NULL;
 if(capture && value && *value)
  snprintf(candidate,sizeof(candidate),"%s",value);
 return value;
}
int nvram_set(const char *key,const char *value){
 resolve();int unit=-1,at=0,old=-1;
 int clear_service=key && value && !strcmp(key,"rc_service") && !*value;
 char saved_key[64],saved_value[2];
 if(runtime_active() && key && value && strlen(value)==1 && *value>='0' && *value<='6' && sscanf(key,"wan%d_state_t%n",&unit,&at)==1 && at && !key[at] && unit>=0 && unit<32 && strlen(key)<sizeof(saved_key)){
  strcpy(saved_key,key);saved_value[0]=*value;saved_value[1]=0;
  const char *previous=real_get?real_get(saved_key):NULL;if(previous && *previous)old=atoi(previous);
  key=saved_key;value=saved_value;
 }else unit=-1;
 int state=unit>=0?saved_value[0]-'0':-1;
 int result=real_set?real_set(key,value):-1;
 if(!result && runtime_active()){
  if(unit>=0 && old!=state && wan_count<64 && scripts_enabled()){wan[wan_count].unit=unit;wan[wan_count++].state=state;}
  if(clear_service && service_cursor){service_end();service_cursor=NULL;candidate[0]=0;flush_wan();}
 }
 return result;
}
char *strsep(char **cursor,const char *delimiter){
 resolve();int ours=enabled() && init_process() && *cursor && !strcmp(delimiter,";") &&
  (service_cursor==cursor || (!service_cursor && *candidate && !strcmp(*cursor,candidate)));
 if(ours)service_end();
 char *part=real_strsep(cursor,delimiter);
 if(ours && part){
  service_cursor=cursor;char word[192];if(sscanf(part,"%191s",word)==1){
   const char *suffix=NULL;
   if(!strncmp(word,"restart_",8)){strcpy(action,"restart");suffix=word+8;}
   else if(!strncmp(word,"start_",6)){strcpy(action,"start");suffix=word+6;}
   else if(!strncmp(word,"stop_",5)){strcpy(action,"stop");suffix=word+5;}
   if(suffix && *suffix && strlen(suffix)<sizeof(target)){strcpy(target,suffix);emit("service-event",action,target,1);}else action[0]=target[0]=0;
  }
 }
 return part;
}
static int storage(const char *path){return path && (!strncmp(path,"/tmp/mnt/",9) || !strncmp(path,"/mnt/",5));}
int mount(const char *source,const char *dest,const char *type,unsigned long flags,const void *data){
 resolve();int disk=storage(dest) && !(flags&(MS_BIND|MS_REMOUNT));
 if(disk)emit("pre-mount",source,type,1);
 int result=real_mount(source,dest,type,flags,data),saved=errno;
 if(!result && dest && !strcmp(dest,"/jffs") && runtime_active()){
  char *args[]={"/bin/sh",LM_BOOTSTRAP,"prepare",NULL};guard++;lm_run(args,120);guard--;
  emit("init-start","","",1);
 }else if(!result && disk){
  for(unsigned i=0;i<unmount_count;i++)if(!strcmp(unmounts[i],dest))unmounts[i][0]=0;
  emit("post-mount",dest,"",0);
 }
 errno=saved;return result;
}
static void before_unmount(const char *path){
 if(!storage(path) || !enabled())return;
 for(unsigned i=0;i<unmount_count;i++)if(!strcmp(unmounts[i],path))return;
 unsigned slot=0;while(slot<unmount_count && unmounts[slot][0])slot++;
 if(slot==unmount_count){if(unmount_count<16)unmount_count++;else slot=0;}
 snprintf(unmounts[slot],sizeof(unmounts[0]),"%s",path);
 guard++;lm_barrier(120);guard--;emit("unmount",path,"",1);
}
int umount(const char *path){resolve();before_unmount(path);return real_umount(path);}
int umount2(const char *path,int flags){resolve();before_unmount(path);return real_umount2(path,flags);}
int sigwaitinfo(const sigset_t *set,siginfo_t *info){
 resolve();
 if(init_process() && runtime_active()){
  if(start_pending){
   char *args[]={"/bin/sh",LM_BOOTSTRAP,"start",NULL};guard++;int status=lm_run(args,120);guard--;
   if(!status){emit("services-start","","",0);started=1;start_pending=0;}
  }
  flush_wan();
 }
 int result=real_wait(set,info),saved=errno;
 if(result>0 && init_process() && runtime_active() && (result==SIGHUP || result==SIGINT || result==SIGTERM || result==SIGQUIT)){
  if(started){guard++;lm_barrier(120);guard--;emit("services-stop","","",1);}
  char *args[]={"/bin/sh",LM_BOOTSTRAP,"stop",NULL};guard++;lm_run(args,30);guard--;
  started=0;start_pending=result==SIGHUP;
 }
 errno=saved;return result;
}
/* Apply generated DNS settings before the daemon starts, never after it. */
static uint64_t hash_file(const char *path){
 FILE *f=fopen(path,"rb");if(!f)return 0;uint64_t h=1469598103934665603ULL;int c;
 while((c=fgetc(f))!=EOF){h^=(unsigned char)c;h*=1099511628211ULL;}fclose(f);return h;
}
static int copy_file(const char *from,const char *to,int append){
 FILE *src=fopen(from,"rb");if(!src)return -1;FILE *dest=fopen(to,append?"ab":"wb");if(!dest){fclose(src);return -1;}
 char b[4096];size_t n;int bad=0;if(append)fputc('\n',dest);
 while((n=fread(b,1,sizeof(b),src)))if(fwrite(b,1,n,dest)!=n){bad=1;break;}
 if(ferror(src))bad=1;if(fclose(dest))bad=1;fclose(src);return bad?-1:0;
}
int _eval(char *const argv[],const char *path,int timeout,int *pid){
 resolve();const char *name=argv && argv[0]?strrchr(argv[0],'/'):NULL;name=name?name+1:(argv?argv[0]:NULL);
 /* HND's non-routing start_wan uses this exact flush. Keep policies and user
  * chain definitions, but clear their rules with the API guard atomically. */
 if(lm_enabled() && name && !strcmp(name,"iptables") && argv[1] && argv[2] && argv[3] && !argv[4] &&
    !strcmp(argv[1],"-t") && !strcmp(argv[2],"filter") && !strcmp(argv[3],"-F") && !pid){
  char *a[]={"/usr/sbin/iptables-restore","--localmod-flush-filter",NULL};return real_eval?real_eval(a,path,timeout,pid):-1;
 }
 if(runtime_active() && name && !strcmp(name,"dnsmasq") && scripts_enabled()){
  const char *conf="/etc/dnsmasq.conf";for(int i=1;argv[i];i++)if(!strcmp(argv[i],"-C") && argv[i+1])conf=argv[i+1];
  static uint64_t previous;static char previous_path[4096];uint64_t before=hash_file(conf);
  guard++;
  char backup[128];uint64_t path_hash=1469598103934665603ULL;
  for(const char *p=conf;*p;p++){path_hash^=(unsigned char)*p;path_hash*=1099511628211ULL;}
  snprintf(backup,sizeof(backup),LM_BASE "/dnsmasq.%016llx.base",(unsigned long long)path_hash);
  if(before && !lm_directory(LM_BASE)){
   if(before!=previous || strcmp(previous_path,conf))copy_file(conf,backup,0);
   else copy_file(backup,conf,0);
   if(access("/jffs/configs/dnsmasq.conf",R_OK)==0)copy_file("/jffs/configs/dnsmasq.conf",conf,0);
   copy_file("/jffs/configs/dnsmasq.conf.add",conf,1);
   struct stat directory;
   if(!stat("/jffs/configs/dnsmasq.d",&directory) && S_ISDIR(directory.st_mode)){
    FILE *f=fopen(conf,"rb");char line[1024];int present=0;
    const char *directive="conf-dir=/jffs/configs/dnsmasq.d";size_t len=strlen(directive);
    if(f){while(fgets(line,sizeof(line),f))if(!strncmp(line,directive,len) && (!line[len] || line[len]=='\n' || line[len]=='\r' || line[len]==',')){present=1;break;}fclose(f);}
    if(!present){f=fopen(conf,"ab");if(f){fputs("\nconf-dir=/jffs/configs/dnsmasq.d\n",f);fclose(f);}}
   }
  }
  if(access("/jffs/scripts/dnsmasq.postconf",X_OK)==0){char *a[]={"/jffs/scripts/dnsmasq.postconf",(char *)conf,NULL};lm_run(a,120);}
  previous=hash_file(conf);snprintf(previous_path,sizeof(previous_path),"%s",conf);guard--;
 }
 return real_eval?real_eval(argv,path,timeout,pid):-1;
}
