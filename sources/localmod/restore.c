/* SPDX-License-Identifier: MIT
 * Restore the stock tables with the private API guard in the same COMMIT.
 * The vendor xtables-multi executable and its exit status are preserved.
 */
#define _GNU_SOURCE
#include "runtime.h"
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#ifndef VENDOR_RESTORE
#define VENDOR_RESTORE "/usr/sbin/xtables-multi"
#endif
#define MAX_RULES (32U*1024U*1024U)
static FILE *filter_snapshot(void){
 FILE *file=tmpfile();if(!file)return NULL;pid_t child=fork();int status=0;
 if(child==0){dup2(fileno(file),STDOUT_FILENO);char *a[]={"iptables-save","-t","filter",NULL};execv(VENDOR_RESTORE,a);_exit(127);}
 if(child<0){fclose(file);return NULL;}
 while(waitpid(child,&status,0)<0){if(errno!=EINTR){fclose(file);return NULL;}}
 if(!WIFEXITED(status) || WEXITSTATUS(status)){fclose(file);return NULL;}
 rewind(file);return file;
}
static void policy(FILE *out,int noflush){
 fputs(":LOCALMOD_API - [0:0]\n",out);
 if(noflush)fputs("-F LOCALMOD_API\n",out);
 fputs(noflush?"-I INPUT 1 -d 127.0.0.1/32 -p tcp --dport 3032 -j LOCALMOD_API\n":"-A INPUT -d 127.0.0.1/32 -p tcp --dport 3032 -j LOCALMOD_API\n",out);
 fputs("-A LOCALMOD_API -i lo -s 127.0.0.1/32 -p tcp --sport 1:1023 -j RETURN\n-A LOCALMOD_API -j REJECT\n",out);
}
int main(int argc,char **argv){
 if(!lm_enabled()){execv(VENDOR_RESTORE,argv);return 127;}
 if(argc>128)return 2;
 char *args[130];int count=0,file_index=-1,test=0,noflush=0,flush_filter=0;args[count++]=argv[0];
 for(int i=1;i<argc;i++){
  const char *s=argv[i];
  if(!strcmp(s,"--localmod-flush-filter")){flush_filter=1;continue;}
  if(!strcmp(s,"--help") || !strcmp(s,"-h") || !strcmp(s,"--version") || !strcmp(s,"-V")){execv(VENDOR_RESTORE,argv);return 127;}
  if(!strcmp(s,"-M") || !strcmp(s,"--modprobe") || !strcmp(s,"-T") || !strcmp(s,"--table")){
   if(i+1>=argc)return 2;args[count++]=argv[i];args[count++]=argv[++i];continue;
  }
  if(!strcmp(s,"-w") || !strcmp(s,"--wait") || !strcmp(s,"-W") || !strcmp(s,"--wait-interval")){
   args[count++]=argv[i];if(i+1<argc && isdigit((unsigned char)argv[i+1][0]))args[count++]=argv[++i];continue;
  }
  if(!strcmp(s,"--test") || !strcmp(s,"-t"))test=1;
  if(!strcmp(s,"--noflush") || !strcmp(s,"-n"))noflush=1;
  if(s[0]=='-'){
   if(strcmp(s,"--test") && strcmp(s,"-t") && strcmp(s,"--noflush") && strcmp(s,"-n") && strcmp(s,"--counters") && strcmp(s,"-c") && strcmp(s,"--verbose") && strcmp(s,"-v")){
    fprintf(stderr,"localmod: unsupported restore option %s\n",s);return 2;
   }
   args[count++]=argv[i];continue;
  }
  if(file_index>=0)return 2;file_index=i;
 }
 if(flush_filter && (file_index>=0 || count!=1))return 2;
 if(flush_filter)args[count++]="-c";
 args[count]=NULL;
 FILE *input=flush_filter?filter_snapshot():(file_index<0?stdin:fopen(argv[file_index],"rb"));if(!input){perror("localmod restore input");return 1;}
 if(lm_directory(LM_BASE))return 1;
 char temp[]=LM_BASE "/restore.XXXXXX";int fd=mkstemp(temp);if(fd<0)return 1;
 FILE *out=fdopen(fd,"w+");if(!out){close(fd);unlink(temp);return 1;}
 char *line=NULL;size_t capacity=0,total=0;ssize_t len;int filter=0,nat=0,saw_filter=0,inserted=0,has_input=0,bad=0;
 while((len=getline(&line,&capacity,input))>=0){
  total+=(size_t)len;if(total>MAX_RULES || memchr(line,0,(size_t)len)){bad=1;break;}
  char *rule=line;while(*rule==' ' || *rule=='\t')rule++;
  if(flush_filter && !strncmp(rule,"-A ",3))continue;
  if(rule[0]=='*'){
   if(filter){bad=1;break;}
   filter=!strncmp(rule,"*filter",7) && (rule[7]=='\n' || rule[7]=='\r' || !rule[7]);
   if(filter){saw_filter=1;inserted=0;has_input=noflush;}
   if(!strncmp(rule,"*nat",4) && (rule[4]=='\n' || rule[4]=='\r' || !rule[4]))nat=1;
  }
  if(filter){
   if(!strncmp(rule,":INPUT ",7))has_input=1;
   if(!strncmp(rule,":LOCALMOD_API ",14) || !strncmp(rule,"-A LOCALMOD_API ",16) || !strncmp(rule,"-F LOCALMOD_API\n",16))continue;
   if(!strncmp(rule,"-A INPUT ",9) && strstr(rule,"-j LOCALMOD_API"))continue;
   if(!inserted && rule[0]!=':' && rule[0]!='#' && rule[0]!='*' && rule[0]!='\n' && rule[0]!='\r'){
    if(!has_input){bad=1;break;}policy(out,noflush);inserted=1;
   }
   if(!strncmp(rule,"COMMIT",6)){filter=0;}
  }
  size_t bytes=(size_t)len-(size_t)(rule-line);
  if(fwrite(rule,1,bytes,out)!=bytes){bad=1;break;}
 }
 free(line);if(ferror(input))bad=1;if(input!=stdin)fclose(input);
 if(filter || ferror(out))bad=1;
 if(bad || fflush(out) || fseek(out,0,SEEK_SET)){fprintf(stderr,"localmod: malformed or unsupported restore input\n");fclose(out);unlink(temp);return 2;}
 pid_t child=fork();int status=0;
 if(child==0){dup2(fd,STDIN_FILENO);fclose(out);unlink(temp);unsetenv("LD_PRELOAD");execv(VENDOR_RESTORE,args);_exit(127);}
 if(child<0){fclose(out);unlink(temp);return 1;}
 while(waitpid(child,&status,0)<0){if(errno!=EINTR){status=1<<8;break;}}
 fclose(out);unlink(temp);
 int result=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
 if(!result && !test){
  if(saw_filter && !flush_filter)lm_emit("firewall-start","","",0);
  if(nat)lm_emit("nat-start","","",0);
 }
 return result;
}
