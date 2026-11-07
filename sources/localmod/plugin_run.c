/* SPDX-License-Identifier: MIT
 * Bound owned installer/download execution. Do not kill preexisting services.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static volatile sig_atomic_t cancelled;
static void stop(int signal){cancelled=signal;}
int main(int argc,char **argv){
 if(argc<5)return 2;char *end=NULL;long seconds=strtol(argv[1],&end,10);
 if(*end || seconds<1 || seconds>600)return 2;
 unsigned long long limit=strtoull(argv[3],&end,10);if(*end || limit>64ULL*1024*1024)return 2;
 struct sigaction sa={.sa_handler=stop};sigemptyset(&sa.sa_mask);sigaction(SIGINT,&sa,NULL);sigaction(SIGTERM,&sa,NULL);sigaction(SIGHUP,&sa,NULL);
 pid_t pid=fork();if(pid<0)return 1;
 if(!pid){setpgid(0,0);signal(SIGINT,SIG_DFL);signal(SIGTERM,SIG_DFL);signal(SIGHUP,SIG_DFL);execvp(argv[4],argv+4);_exit(127);}
 setpgid(pid,pid);int status;double deadline=now()+seconds;int reason=0;
 for(;;){
  pid_t got=waitpid(pid,&status,WNOHANG);
  if(got==pid){
   struct stat s;
   if(limit && strcmp(argv[2],"-") && lstat(argv[2],&s)==0 && (!S_ISREG(s.st_mode) || (unsigned long long)s.st_size>limit)){reason=125;break;}
   return WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
  }
  if(got<0 && errno!=EINTR){reason=1;break;}
  if(cancelled){reason=128+cancelled;break;}
  if(now()>=deadline){reason=124;break;}
  if(limit && strcmp(argv[2],"-")){
   struct stat s;if(lstat(argv[2],&s)==0){if(!S_ISREG(s.st_mode) || (unsigned long long)s.st_size>limit){reason=125;break;}}
   else if(errno!=ENOENT){reason=125;break;}
  }
  usleep(20000);
 }
 kill(-pid,SIGTERM);usleep(200000);kill(-pid,SIGKILL);
 while(waitpid(pid,&status,0)<0 && errno==EINTR){}
 fprintf(stderr,"Owned plugin task stopped, result=%d (124 timeout, 125 download limit).\n",reason);return reason;
}
