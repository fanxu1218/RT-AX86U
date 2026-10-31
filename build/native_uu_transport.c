/* SPDX-License-Identifier: MIT
 * Test-only service notification / DNS boundary for native rc ntp execution.
 * The UU implementation, NTP signal handler and monitor launch remain native.
 */
#define _GNU_SOURCE
#include <stdarg.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <errno.h>
int notify_rc(const char *event){FILE *f=fopen("/tmp/native-uu-notify.log","a");if(f){fprintf(f,"%s\n",event);fclose(f);}return 0;}
int doSystem(const char *format,...){
 va_list args;va_start(args,format);char *command=NULL;vasprintf(&command,format,args);va_end(args);
 if(!command)return -1;
 int status=!strncmp(command,"nslookup ",9)?1:system(command);free(command);return status;
}

int pause(void){
 /* Publishing readiness before libc pause leaves a lost-wakeup window:
  * the test's one signal may arrive between the file and pause(). Block
  * signals while publishing, then atomically restore the caller's mask
  * and wait. The original rc handlers still receive the real signal. */
 sigset_t all,previous;
 sigfillset(&all);
 if(sigprocmask(SIG_BLOCK,&all,&previous))return -1;
 FILE *f=fopen("/tmp/native-ntp-idle","w");if(f){fputs("idle\n",f);fclose(f);}
 int result=sigsuspend(&previous),saved=errno;
 sigprocmask(SIG_SETMASK,&previous,NULL);errno=saved;return result;
}
