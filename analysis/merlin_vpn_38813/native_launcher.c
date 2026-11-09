/* SPDX-License-Identifier: MIT
 * Keep the complete Merlin rc. Only software-center service aliases are ours.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc,char **argv){
 const char *name=strrchr(argv[0],'/');name=name?name+1:argv[0];
 if(!strcmp(name,"service") && argc==2){
  const char *command=NULL;
  if(!strcmp(argv[1],"start_skipd"))command="skipd-start";
  else if(!strcmp(argv[1],"stop_skipd"))command="skipd-stop";
  else if(!strcmp(argv[1],"restart_skipd"))command="skipd-restart";
  else if(!strcmp(argv[1],"start_softcenter"))command="start";
  else if(!strcmp(argv[1],"stop_softcenter"))command="stop";
  else if(!strcmp(argv[1],"restart_softcenter"))command="restart";
  if(command){unsetenv("LD_PRELOAD");execl("/bin/sh","sh","/usr/libexec/localmod/bootstrap.sh",command,(char *)NULL);return 127;}
 }
 if(access("/jffs/localmod-disabled",F_OK)==0)unsetenv("LD_PRELOAD");
 else setenv("LD_PRELOAD","/usr/lib/localmod/native_boot_bridge.so",1);
 execv("/usr/libexec/localmod/rc.vendor",argv);perror("native Merlin rc");return 127;
}
