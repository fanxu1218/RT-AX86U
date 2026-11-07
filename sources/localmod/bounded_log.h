/* SPDX-License-Identifier: MIT */
#ifndef LOCALMOD_BOUNDED_LOG_H
#define LOCALMOD_BOUNDED_LOG_H
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <signal.h>
#ifndef LM_LOGGER
#define LM_LOGGER "/usr/libexec/localmod/log-limit"
#endif
#ifndef LM_BASE
#define LM_BASE "/tmp/.localmod"
#endif
#define LM_LOG_LIMIT (128*1024)
static int lm_log_write(const char *name,const void *data,size_t size){
 char path[256],old[256],lockpath[256];
 if(!strcmp(name,"install"))snprintf(path,sizeof(path),"/tmp/upload/soft_install_log.txt");
 else if(!strcmp(name,"offline"))snprintf(path,sizeof(path),"/tmp/upload/soft_log.txt");
 else if(!strcmp(name,"offline-backup"))snprintf(path,sizeof(path),"/tmp/upload/soft_log_backup.txt");
 else {if(strcmp(name,"bootstrap") && strcmp(name,"skipd") && strcmp(name,"events"))return -1;snprintf(path,sizeof(path),LM_BASE "/%s.log",name);}
 snprintf(old,sizeof(old),"%s.1",path);snprintf(lockpath,sizeof(lockpath),LM_BASE "/%s.log.lock",name);
 int lock=open(lockpath,O_CREAT|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600);struct stat st;
 if(lock<0)return -1;
 if(fstat(lock,&st) || !S_ISREG(st.st_mode) || st.st_uid!=geteuid() || st.st_nlink!=1 || flock(lock,LOCK_EX)){close(lock);return -1;}
 const char *p=data;if(size>LM_LOG_LIMIT){p+=size-LM_LOG_LIMIT;size=LM_LOG_LIMIT;}
 int fd=open(path,O_CREAT|O_APPEND|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600),result=-1;
 if(fd<0)goto done;
 if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_uid!=geteuid() || st.st_nlink!=1)goto done;
 fchmod(fd,0600);
 if(st.st_size>LM_LOG_LIMIT){
  char *tail=malloc(LM_LOG_LIMIT);if(!tail)goto done;
  ssize_t n=pread(fd,tail,LM_LOG_LIMIT,st.st_size-LM_LOG_LIMIT);
  if(n!=LM_LOG_LIMIT || ftruncate(fd,0) || write(fd,tail,LM_LOG_LIMIT)!=LM_LOG_LIMIT){free(tail);goto done;}
  free(tail);st.st_size=LM_LOG_LIMIT;
 }
 if((unsigned long long)st.st_size+size>LM_LOG_LIMIT){close(fd);fd=-1;
  if(rename(path,old))goto done;
  fd=open(path,O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0)goto done;
 }
 while(size){ssize_t n=write(fd,p,size);if(n<0 && errno==EINTR)continue;if(n<=0)goto done;p+=n;size-=(size_t)n;}
 result=0;
done:if(fd>=0)close(fd);close(lock);return result;
}
static int lm_capture_log(const char *name){
 int p[2];if(pipe(p))return -1;pid_t pid=fork();if(pid<0){close(p[0]);close(p[1]);return -1;}
 if(!pid){
  close(p[1]);for(int i=0;i<3;i++)if(i!=p[0])close(i);
  /* Exec closes CLOEXEC service/queue locks without touching QEMU's private
   * host descriptors exposed by its proc boundary. The pipe stays open. */
  signal(SIGTERM,SIG_DFL);signal(SIGINT,SIG_DFL);signal(SIGHUP,SIG_DFL);signal(SIGCHLD,SIG_DFL);
  sigset_t empty;sigemptyset(&empty);sigprocmask(SIG_SETMASK,&empty,NULL);
  char fd[24];snprintf(fd,sizeof(fd),"%d",p[0]);execl(LM_LOGGER,"log-limit","--sink",name,fd,(char *)NULL);_exit(127);
 }
 close(p[0]);if(dup2(p[1],1)<0 || dup2(p[1],2)<0){close(p[1]);return -1;}close(p[1]);return 0;
}
#endif
