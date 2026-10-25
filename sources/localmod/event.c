/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include "runtime.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
static void terminate(int signal){(void)signal;lm_stopping=1;}

static int event_file(const struct dirent *d){size_t n=strlen(d->d_name);return n>4 && !strcmp(d->d_name+n-4,".evt");}
int main(int argc,char **argv){
 if(argc<2)return 2;
 if(strcmp(argv[1],"--daemon") && strcmp(argv[1],"--drain")){
  int sync=!strcmp(argv[1],"--sync"),at=sync?2:1;
  if(argc<=at)return 2;
  return lm_emit(argv[at],argc>at+1?argv[at+1]:"",argc>at+2?argv[at+2]:"",sync)!=0;
 }
 if(lm_directory(LM_BASE) || lm_directory(LM_BASE "/queue"))return 1;
 int lock=open(LM_BASE "/events.lock",O_CREAT|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600);
 if(lock<0 || flock(lock,LOCK_EX|LOCK_NB))return 1;
 int daemon=!strcmp(argv[1],"--daemon");
 if(daemon){
  struct sigaction action={.sa_handler=terminate};sigemptyset(&action.sa_mask);sigaction(SIGTERM,&action,NULL);sigaction(SIGINT,&action,NULL);
  char temp[]=LM_BASE "/pid.XXXXXX";int fd=mkstemp(temp);if(fd<0)return 1;
  dprintf(fd,"%ld\n",(long)getpid());close(fd);
  if(rename(temp,LM_BASE "/eventd.pid")){unlink(temp);return 1;}
 }
 for(;;){
  struct dirent **entries=NULL;int n=scandir(LM_BASE "/queue",&entries,event_file,alphasort);
  for(int i=0;i<n;i++){
   if(lm_stopping){for(int j=i;j<n;j++)free(entries[j]);break;}
   char path[4352];snprintf(path,sizeof(path),LM_BASE "/queue/%s",entries[i]->d_name);free(entries[i]);
   int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);struct stat st;struct lm_event e;
   int valid=fd>=0 && !fstat(fd,&st) && S_ISREG(st.st_mode) && st.st_uid==geteuid() && !(st.st_mode&0022) && st.st_size==sizeof(e);
   if(valid){size_t left=sizeof(e);char *p=(char *)&e;while(left){ssize_t got=read(fd,p,left);if(got<0 && errno==EINTR)continue;if(got<=0){valid=0;break;}p+=got;left-=(size_t)got;}}
   if(fd>=0)close(fd);unlink(path);
   if(valid && e.magic==LM_MAGIC && memchr(e.name,0,sizeof(e.name)) && memchr(e.arg1,0,sizeof(e.arg1)) && memchr(e.arg2,0,sizeof(e.arg2))){
    int result=lm_dispatch(&e);printf("event %s result %d\n",e.name,result);fflush(stdout);
   }
  }
  free(entries);if(!strcmp(argv[1],"--drain") || lm_stopping)break;
  if(!lm_enabled()){
   char *args[]={"/bin/sh",LM_BOOTSTRAP,"stop-backend",NULL};lm_run(args,30);break;
  }
  usleep(100000);
 }
 if(daemon)unlink(LM_BASE "/eventd.pid");close(lock);return 0;
}
