/* SPDX-License-Identifier: MIT
 * Read-only, bounded, allowlisted diagnostics. No DB, logs, argv or keys export. */
#ifndef LOCALMOD_HEALTH_H
#define LOCALMOD_HEALTH_H
#include <dirent.h>
#include <fcntl.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <ctype.h>
#define LM_OPERATION "/tmp/.localmod/last-operation"
static int lm_module_safe(const char *s) {
 size_t n=strlen(s);if(!n || n>64)return 0;
 for(;*s;s++)if(!isalnum((unsigned char)*s)&&*s!='_'&&*s!='-')return 0;
 return 1;
}
static int lm_private_read(const char *path,char *out,size_t capacity) {
 int fd=open(path,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);if(fd<0)return -1;
 struct stat st;int n=-1;
 if(!fstat(fd,&st)&&S_ISREG(st.st_mode)&&st.st_uid==0&&st.st_nlink==1&&st.st_size<(off_t)capacity){n=(int)read(fd,out,capacity-1);if(n>=0)out[n]=0;}
 close(fd);return n;
}
static void lm_process_counts(unsigned counts[4]) {
 static const char *names[]={"httpdb","skipd","localmod-event","uuplugin"};
 DIR *d=opendir("/proc");if(!d)return;struct dirent *e;unsigned scanned=0;
 while((e=readdir(d)) && scanned<4096){
  if(!isdigit((unsigned char)e->d_name[0]))continue;scanned++;
  char path[96],comm[64];snprintf(path,sizeof(path),"/proc/%.16s/comm",e->d_name);
  int fd=open(path,O_RDONLY|O_CLOEXEC);if(fd<0)continue;ssize_t n=read(fd,comm,sizeof(comm)-1);close(fd);if(n<=0)continue;
  comm[n]=0;comm[strcspn(comm,"\n")]=0;
  for(unsigned i=0;i<4;i++)if(!strcmp(comm,names[i]))counts[i]++;
 }
 closedir(d);
}
static int lm_health_json(char *out,size_t capacity) {
 struct stat st;const char *checkpoint="none";
 if(lstat("/jffs/.localmod/plugin-txn",&st)==0){
  if(!S_ISDIR(st.st_mode))checkpoint="store-invalid";
  else if(lstat("/jffs/.localmod/plugin-txn/active",&st)==0)checkpoint="pending";
  else if(errno!=ENOENT)checkpoint="unavailable";
 }else if(errno!=ENOENT)checkpoint="unavailable";
 struct statvfs fs;int space_ok=statvfs("/jffs",&fs)==0;
 unsigned long long free_bytes=space_ok?(unsigned long long)fs.f_bavail*fs.f_frsize:0;
 unsigned long long total_bytes=space_ok?(unsigned long long)fs.f_blocks*fs.f_frsize:0;
 unsigned counts[4]={0};lm_process_counts(counts);
 char raw[160],module[65],state[16],extra;long long when;int code;
 char operation[256]="null";
 if(lm_private_read(LM_OPERATION,raw,sizeof(raw))>0 &&
    sscanf(raw,"%lld %64s %15s %d %c",&when,module,state,&code,&extra)==4 && when>=0 && lm_module_safe(module) &&
    (!strcmp(state,"running")||!strcmp(state,"finished")||!strcmp(state,"interrupted")) && code>=0 && code<=255)
  snprintf(operation,sizeof(operation),"{\"module\":\"%s\",\"state\":\"%s\",\"code\":%d,\"epoch\":%lld}",module,state,code,when);
 int n=snprintf(out,capacity,"{\"schema\":1,\"scope\":\"local-readonly-summary\",\"services\":{\"httpdb\":%u,\"skipd\":%u,\"events\":%u,\"uuplugin\":%u},\"jffs\":{\"available\":%s,\"free_bytes\":%llu,\"total_bytes\":%llu},\"checkpoint\":\"%s\",\"last_operation\":%s,\"limits\":[\"Process counts do not prove service health or UU acceleration\",\"Checkpoint presence is not seal verification\",\"Operation record is temporary and resets after reboot\",\"No logs, configuration, tokens, certificates or account data exported\"]}\n",counts[0],counts[1],counts[2],counts[3],space_ok?"true":"false",free_bytes,total_bytes,checkpoint,operation);
 return n>0 && (size_t)n<capacity?n:-1;
}
#endif
