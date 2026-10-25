/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include "runtime.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
volatile sig_atomic_t lm_stopping;

int lm_directory(const char *path) {
 struct stat s;
 if(mkdir(path,0700) && errno!=EEXIST)return -1;
 return lstat(path,&s) || !S_ISDIR(s.st_mode) || s.st_uid!=geteuid() || (s.st_mode&0077) ? -1:0;
}
int lm_enabled(void){return access("/jffs/localmod-disabled",F_OK)!=0;}
static double monotonic(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
int lm_run(char *const argv[],unsigned seconds){
 sigset_t mask,oldmask;struct sigaction oldchild,def={.sa_handler=SIG_DFL};
 sigemptyset(&mask);sigaddset(&mask,SIGCHLD);sigprocmask(SIG_BLOCK,&mask,&oldmask);
 sigemptyset(&def.sa_mask);sigaction(SIGCHLD,&def,&oldchild);
 pid_t pid=fork();int status=0,answer=127;
 if(pid==0){
  setsid();sigemptyset(&mask);sigprocmask(SIG_SETMASK,&mask,NULL);
  for(int i=1;i<NSIG;i++)if(i!=SIGKILL && i!=SIGSTOP)signal(i,SIG_DFL);
  unsetenv("LD_PRELOAD");setenv("LOCALMOD_HOOK_DEPTH","1",1);
  execv(argv[0],argv);_exit(127);
 }
 if(pid>0){
  double end=monotonic()+seconds;
  for(;;){
   pid_t got=waitpid(pid,&status,WNOHANG);
   if(got==pid){answer=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);break;}
   if(got<0 && errno!=EINTR)break;
   int cancelled=!strcmp(argv[0],LM_DISPATCH) && (!lm_enabled() || lm_stopping);
   if(monotonic()>=end || cancelled){kill(-pid,SIGTERM);usleep(100000);kill(-pid,SIGKILL);
    while(waitpid(pid,&status,0)<0 && errno==EINTR){}answer=124;break;}
   usleep(10000);
  }
 }
 sigaction(SIGCHLD,&oldchild,NULL);sigprocmask(SIG_SETMASK,&oldmask,NULL);return answer;
}
static int valid_event(const char *name){
 static const char *names[]={"init-start","services-start","services-stop","service-event","service-event-end",
  "wan-event","wan-start","nat-start","firewall-start","pre-mount","post-mount","unmount","dhcpc-event","__barrier",NULL};
 for(int i=0;names[i];i++)if(!strcmp(name,names[i]))return 1;return 0;
}
int lm_dispatch(const struct lm_event *event){
 if(!lm_enabled() || !valid_event(event->name) || !strcmp(event->name,"__barrier"))return 0;
 if(lm_directory(LM_BASE))return -1;
 char context[]=LM_BASE "/event.XXXXXX";if(!mkdtemp(context))return -1;
 const char *previous=getenv("LOCALMOD_EVENT_DIR");char saved[4096]="";
 if(previous)snprintf(saved,sizeof(saved),"%s",previous);
 setenv("LOCALMOD_EVENT_DIR",context,1);
 char *args[]={LM_DISPATCH,(char *)event->name,(char *)event->arg1,(char *)event->arg2,NULL};
 int result=lm_run(args,120);
 if(previous)setenv("LOCALMOD_EVENT_DIR",saved,1);else unsetenv("LOCALMOD_EVENT_DIR");
 DIR *d=opendir(context);struct dirent *entry;
 if(d){while((entry=readdir(d))){if(entry->d_name[0]=='.')continue;
  char p[4352];snprintf(p,sizeof(p),"%s/%s",context,entry->d_name);rmdir(p);}closedir(d);}
 rmdir(context);return result;
}
static int enqueue(const struct lm_event *event,char *queued,size_t capacity){
 if(lm_directory(LM_BASE) || lm_directory(LM_BASE "/queue"))return -1;
 char temp[]=LM_BASE "/queue/.tmp.XXXXXX";int fd=mkstemp(temp);if(fd<0)return -1;
 const char *p=(const char *)event;size_t left=sizeof(*event);int ok=1;
 while(left){ssize_t n=write(fd,p,left);if(n<0 && errno==EINTR)continue;if(n<=0){ok=0;break;}p+=n;left-=(size_t)n;}
 if(fsync(fd))ok=0;close(fd);
 struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
 static unsigned sequence;char final[256];snprintf(final,sizeof(final),LM_BASE "/queue/%020lld.%09ld.%010ld.%08u.evt",(long long)t.tv_sec,t.tv_nsec,(long)getpid(),sequence++);
 if(!ok || rename(temp,final)){unlink(temp);return -1;}
 if(queued)snprintf(queued,capacity,"%s",final);return 0;
}
int lm_emit(const char *name,const char *a,const char *b,int synchronous){
 if(!lm_enabled() || getenv("LOCALMOD_HOOK_DEPTH"))return 0;
 struct lm_event e={.magic=LM_MAGIC};
 if(!valid_event(name) || strlen(name)>=sizeof(e.name) || (a && strlen(a)>=sizeof(e.arg1)) || (b && strlen(b)>=sizeof(e.arg2)))return -1;
 strcpy(e.name,name);if(a)strcpy(e.arg1,a);if(b)strcpy(e.arg2,b);
 return synchronous?lm_dispatch(&e):enqueue(&e,NULL,0);
}
int lm_barrier(unsigned seconds){
 if(!lm_enabled() || getenv("LOCALMOD_HOOK_DEPTH"))return 0;
 if(lm_directory(LM_BASE))return -1;
 int fd=open(LM_BASE "/events.lock",O_CREAT|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600);
 if(fd<0)return -1;
 int daemon=flock(fd,LOCK_EX|LOCK_NB)!=0;close(fd);
 if(!daemon){char *args[]={"/usr/libexec/localmod/localmod-event","--drain",NULL};return lm_run(args,seconds);}
 struct lm_event event={.magic=LM_MAGIC,.name="__barrier"};char queued[256];
 if(enqueue(&event,queued,sizeof(queued)))return -1;
 double end=monotonic()+seconds;
 while(access(queued,F_OK)==0){if(monotonic()>=end)return 124;usleep(10000);}return 0;
}
