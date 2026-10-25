#define _GNU_SOURCE
#define _LARGEFILE64_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
int auth_result=1,url_do_auth=0;
extern int check_if_file_exist(const char *);
int main(void){
 if(getenv("LD_PRELOAD"))return 1;
 if(chdir("/tmp/web-fixture"))return 2;
 struct stat64 info;
 if(stat64("Module_Softcenter.asp",&info) || info.st_size<100)return 3;
 puts("PASS software-center ASP stat fallback");
 FILE *f=fopen64("Module_Softcenter.asp","r");if(!f)return 4;
 char buf[128];size_t n=fread(buf,1,sizeof(buf),f);fclose(f);if(n<100)return 5;
 puts("PASS software-center ASP read fallback");
 if(!check_if_file_exist("res/softcenter.js"))return 6;
 puts("PASS software-center resource existence fallback");
 f=fopen64("Module_Builtin.asp","r");if(!f)return 7;
 n=fread(buf,1,sizeof(buf)-1,f);fclose(f);buf[n]=0;
 if(strcmp(buf,"VENDOR"))return 8;
 puts("PASS existing vendor file takes precedence");
 return 0;
}
