/* SPDX-License-Identifier: MIT; measure at the native API return boundary. */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <dlfcn.h>
extern void run_custom_script(char *,int,char *,char *);
extern char *nvram_get(const char *);
int main(int argc,char **argv){
 if(argc!=3)return 2;
 struct timespec a,b;struct stat st;
 char *argument=nvram_get("owned_native_hook_arg");
 clock_gettime(CLOCK_MONOTONIC,&a);
 run_custom_script(argv[1],atoi(argv[2]),argument,"native-second");
 clock_gettime(CLOCK_MONOTONIC,&b);
 int done=stat("/tmp/owned-sync-finished",&st)==0;
 Dl_info owner={0};dladdr(dlsym(RTLD_DEFAULT,"run_custom_script"),&owner);
 printf("SYNC_NATIVE_RETURN {\"elapsed_ms\":%lld,\"helper_finished\":%s,\"loaded_bridge\":\"%s\"}\n",
  (long long)(b.tv_sec-a.tv_sec)*1000+(b.tv_nsec-a.tv_nsec)/1000000,
  done?"true":"false",owner.dli_fname?owner.dli_fname:"");
 fflush(stdout);
 // Keep the native caller alive after measuring its return, like PID1. This
 // avoids conflating API completion with emulator/parent-exit child cleanup.
 if(!strcmp(argv[1],"unmount") && strcmp(argv[2],"1")){
  const struct timespec delay={0,20000000};
  for(int i=0;i<300 && stat("/tmp/owned-sync-finished",&st);i++)nanosleep(&delay,NULL);
 }
 puts("NATIVE_HOOK_CALL_RETURNED");return 0;
}
