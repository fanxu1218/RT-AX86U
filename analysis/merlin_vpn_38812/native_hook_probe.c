/* SPDX-License-Identifier: MIT; test-only native libshared entry caller. */
#include <stdio.h>
#include <stdlib.h>
extern void run_custom_script(char *,int,char *,char *);
extern void run_postconf(char *,char *);
extern char *nvram_get(const char *);
#include <string.h>
int main(int argc,char **argv){
 if(argc!=3)return 2;
 char *argument=nvram_get("owned_native_hook_arg");
 if(!strcmp(argv[1],"__dnsmasq_postconf"))run_postconf("dnsmasq",argument);
 else run_custom_script(argv[1],atoi(argv[2]),argument,"native-second");
 puts("NATIVE_HOOK_CALL_RETURNED");return 0;
}
