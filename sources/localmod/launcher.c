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

int main(int argc,char **argv) {
 (void)argc;
#ifdef INIT_LAUNCHER
 if(getpid()!=1){fputs("init launcher requires PID 1\n",stderr);return 1;}
 execv("/sbin/rc",argv);
#elif defined(RC_LAUNCHER)
 const char *name=strrchr(argv[0],'/');name=name?name+1:argv[0];
 if(!strcmp(name,"service") && argc==2){
  const char *command=NULL;
  if(!strcmp(argv[1],"start_skipd"))command="skipd-start";
  else if(!strcmp(argv[1],"stop_skipd"))command="skipd-stop";
  else if(!strcmp(argv[1],"restart_skipd"))command="skipd-restart";
  else if(!strcmp(argv[1],"start_softcenter"))command="start";
  else if(!strcmp(argv[1],"stop_softcenter"))command="stop";
  else if(!strcmp(argv[1],"restart_softcenter"))command="restart";
  if(command){execl("/bin/sh","sh","/usr/libexec/localmod/bootstrap.sh",command,(char *)NULL);return 127;}
 }
 if(access("/jffs/localmod-disabled",F_OK)==0)unsetenv("LD_PRELOAD");
 else setenv("LD_PRELOAD","/usr/lib/localmod/rc_bridge.so",1);
 execv("/usr/libexec/localmod/rc.vendor",argv);
#else
 if(access("/jffs/localmod-disabled",F_OK)==0)unsetenv("LD_PRELOAD");
 else setenv("LD_PRELOAD","/usr/lib/localmod/httpd_bridge.so",1);
 /* The native program checks /proc/self/exe against /usr/, /bin/, /sbin/.
  * Keep its basename and execute the retained read-only file directly. */
 execv("/usr/libexec/localmod/httpd",argv);
#endif
 perror("localmod exec");return 127;
}
