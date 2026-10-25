/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

static int copy_vendor(void) {
 const char *dir="/tmp/localmod", *target="/tmp/localmod/httpd";
 struct stat st;
 if(mkdir(dir,0700)<0 && errno!=EEXIST)return -1;
 if(lstat(dir,&st) || !S_ISDIR(st.st_mode) || st.st_uid!=0 || (st.st_mode&0077))return -1;
 if(lstat(target,&st)==0 && S_ISREG(st.st_mode) && st.st_uid==0 && st.st_mode==0100500)return 0;
 int source=open("/usr/libexec/localmod/httpd.vendor",O_RDONLY|O_NOFOLLOW);
 if(source<0)return -1;
 char temp[128];snprintf(temp,sizeof(temp),"%s/.httpd.%ld",dir,(long)getpid());
 int output=open(temp,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0500);
 if(output<0){close(source);return -1;}
 char buffer[16384];ssize_t n;int ok=1;
 while((n=read(source,buffer,sizeof(buffer)))>0){
  ssize_t at=0;while(at<n){ssize_t wrote=write(output,buffer+at,(size_t)(n-at));
   if(wrote<=0){ok=0;break;}at+=wrote;}if(!ok)break;
 }
 if(n<0)ok=0;
 if(fsync(output))ok=0;close(output);close(source);
 if(!ok || rename(temp,target)){unlink(temp);return -1;}return 0;
}
int main(int argc,char **argv) {
 (void)argc;
#ifdef INIT_LAUNCHER
 if(getpid()!=1){fputs("init launcher requires PID 1\n",stderr);return 1;}
 pid_t child=fork();
 if(child==0){setsid();execl("/bin/sh","sh","/usr/libexec/localmod/bootstrap.sh",(char *)NULL);_exit(127);}
 execv("/sbin/rc",argv);
#else
 if(copy_vendor()){perror("localmod vendor httpd");return 1;}
 if(access("/jffs/localmod-disabled",F_OK)==0)unsetenv("LD_PRELOAD");
 else setenv("LD_PRELOAD","/usr/lib/localmod/httpd_bridge.so",1);
 execv("/tmp/localmod/httpd",argv);
#endif
 perror("localmod exec");return 127;
}
