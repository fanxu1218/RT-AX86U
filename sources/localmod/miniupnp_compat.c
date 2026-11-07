/* SPDX-License-Identifier: MIT
 * Adapt the stock UPnP launch contract to the selected Merlin application.
 * Input configuration and leases remain owned by ASUS/user code. This helper
 * writes only its protected /tmp copy and its dedicated postrouting chain.
 */
#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define PRIVATE "/tmp/.localmod-merlin"
#define CONFIG PRIVATE "/miniupnpd.conf"
#define CHAIN "LOCALMOD_UPNP"
#define PROGRAM "/usr/libexec/localmod/merlin/bin/miniupnpd"
#define FACTORY "/usr/libexec/localmod/merlin/vendor/miniupnpd"
#define MAX_CONFIG (256U*1024U)

static int disabled(void) {
 return access("/jffs/localmod-disabled",F_OK)==0 || access("/jffs/localmod-merlin-disabled",F_OK)==0;
}
static int directory(int create) {
 if(create && mkdir(PRIVATE,0700) && errno!=EEXIST)return -1;
 int fd=open(PRIVATE,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(fd<0)return -1;
 struct stat s;
 if(fstat(fd,&s) || s.st_uid!=0 || (s.st_mode&0777)!=0700){close(fd);errno=EPERM;return -1;}
 return fd;
}
static int lock_directory(int dir) {
 int fd=openat(dir,"lock",O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0)return -1;
 struct stat s;
 if(fstat(fd,&s) || !S_ISREG(s.st_mode) || s.st_uid!=0 || s.st_nlink!=1 || (s.st_mode&0777)!=0600 || flock(fd,LOCK_EX)){
  close(fd);errno=EPERM;return -1;
 }
 return fd;
}
static char *read_config(const char *path,size_t *length) {
 /* Follow a user-selected read-only config symlink, as the original daemon
  * does. Nonblocking open plus fstat prevents a FIFO/device from hanging us. */
 int fd=open(path,O_RDONLY|O_NONBLOCK|O_CLOEXEC);if(fd<0)return NULL;
 struct stat s;
 if(fstat(fd,&s) || !S_ISREG(s.st_mode) || s.st_size<0 || s.st_size>MAX_CONFIG){close(fd);errno=EINVAL;return NULL;}
 char *data=malloc(MAX_CONFIG+1);if(!data){close(fd);return NULL;}
 size_t used=0;
 while(used<MAX_CONFIG){ssize_t n=read(fd,data+used,MAX_CONFIG-used);if(n<0 && errno==EINTR)continue;if(n<0){free(data);close(fd);return NULL;}if(!n)break;used+=(size_t)n;}
 char extra;ssize_t more=read(fd,&extra,1);close(fd);
 if(more!=0 || memchr(data,0,used)){free(data);errno=EINVAL;return NULL;}
 data[used]=0;*length=used;return data;
}
static int value(const char *data,const char *key,char *out,size_t capacity) {
 int found=0;size_t keylen=strlen(key);
 for(const char *p=data;*p;){
  const char *end=strchr(p,'\n');if(!end)end=p+strlen(p);
  const char *start=p;while(start<end && isspace((unsigned char)*start))start++;
  if((size_t)(end-start)>=keylen && !strncmp(start,key,keylen)){
   const char *eq=start+keylen;while(eq<end && isspace((unsigned char)*eq))eq++;
   if(eq<end && *eq=='='){
    eq++;while(eq<end && isspace((unsigned char)*eq))eq++;
    const char *last=end;while(last>eq && isspace((unsigned char)last[-1]))last--;
    size_t n=(size_t)(last-eq);if(n>=capacity)return -1;
    memcpy(out,eq,n);out[n]=0;found=1;
   }
  }
  p=*end?end+1:end;
 }
 return found;
}
static int interface_valid(const char *name) {
 size_t n=strlen(name);return n>0 && n<16 && isalnum((unsigned char)name[0]) &&
  strspn(name,"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-")==n;
}
static int command(char *const args[]) {
 pid_t child=fork();if(child<0)return -1;
 if(!child){
  int fd=open("/dev/null",O_RDWR);if(fd>=0){dup2(fd,1);dup2(fd,2);if(fd>2)close(fd);}
  unsetenv("LD_PRELOAD");execv("/usr/sbin/iptables",args);_exit(127);
 }
 struct timespec begin,now;clock_gettime(CLOCK_MONOTONIC,&begin);int status;
 for(;;){
  pid_t result=waitpid(child,&status,WNOHANG);
  if(result==child)return WIFEXITED(status)?WEXITSTATUS(status):1;
  if(result<0 && errno!=EINTR)return -1;
  clock_gettime(CLOCK_MONOTONIC,&now);
  if(now.tv_sec-begin.tv_sec>=4){kill(child,SIGKILL);while(waitpid(child,&status,0)<0 && errno==EINTR){}return -1;}
  usleep(10000);
 }
}
static int rule(const char *op,const char *iface) {
 char *args[]={"iptables","-t","nat",(char *)op,"POSTROUTING","-o",(char *)iface,"-j",CHAIN,NULL};
 return command(args);
}
static int write_private(const char *name,const char *data,size_t len) {
 char temporary[]=PRIVATE "/write.XXXXXX";int fd=mkstemp(temporary);if(fd<0)return -1;
 fcntl(fd,F_SETFD,FD_CLOEXEC);size_t done=0;int bad=0;
 while(done<len){ssize_t n=write(fd,data+done,len-done);if(n<0 && errno==EINTR)continue;if(n<=0){bad=1;break;}done+=(size_t)n;}
 if(fsync(fd))bad=1;if(close(fd))bad=1;
 char target[256];int n=snprintf(target,sizeof(target),PRIVATE "/%s",name);
 if(n<0 || (size_t)n>=sizeof(target) || bad || rename(temporary,target)){unlink(temporary);return -1;}
 return 0;
}
static int delete_hook(const char *iface) {
 for(int n=0;n<8;n++){
  if(rule("-C",iface)!=0)return 0;
  if(rule("-D",iface)!=0)return -1;
 }
 return -1;
}
static int ensure_firewall(const char *iface) {
 if(!interface_valid(iface)){errno=EINVAL;return -1;}
 size_t bytes=0;char *old=read_config(PRIVATE "/upnp-iface",&bytes);
 if(old){
  if(interface_valid(old) && strcmp(old,iface) && delete_hook(old)){free(old);return -1;}
  free(old);
 }
 char *create[]={"iptables","-t","nat","-N",CHAIN,NULL};
 char *exists[]={"iptables","-t","nat","-S",CHAIN,NULL};
 if(command(create) && command(exists))return -1;
 if(rule("-C",iface)){
  /* As in Merlin's firewall, scope bidirectional mappings to their WAN and
   * run before general masquerading. The chain contains only UPnP mappings. */
  char *insert[]={"iptables","-t","nat","-I","POSTROUTING","1","-o",(char *)iface,"-j",CHAIN,NULL};
  if(command(insert))return -1;
 }
 return write_private("upnp-iface",iface,strlen(iface));
}
static int own_configuration(char **data,char *iface,size_t capacity) {
 size_t len=0;*data=read_config(CONFIG,&len);if(!*data)return 0;
 char chain[64];
 if(value(*data,"upnp_nat_postrouting_chain",chain,sizeof(chain))!=1 || strcmp(chain,CHAIN) ||
    value(*data,"ext_ifname",iface,capacity)!=1 || !interface_valid(iface)){free(*data);*data=NULL;return 0;}
 return 1;
}
static int running(void) {
 struct stat expected;if(stat(PROGRAM,&expected))return 0;
 DIR *dir=opendir("/proc");if(!dir)return 0;struct dirent *entry;int found=0;
 while((entry=readdir(dir))){
  if(!isdigit((unsigned char)entry->d_name[0]))continue;
  char path[128];int n=snprintf(path,sizeof(path),"/proc/%s/exe",entry->d_name);
  if(n<0 || (size_t)n>=sizeof(path))continue;
  struct stat executable;if(stat(path,&executable))continue;
  if(executable.st_dev==expected.st_dev && executable.st_ino==expected.st_ino){found=1;break;}
 }
 closedir(dir);return found;
}
static int cleanup(void) {
 char *data=NULL,iface[32];if(!own_configuration(&data,iface,sizeof(iface)))return 0;free(data);
 if(delete_hook(iface))return -1;
 char *flush[]={"iptables","-t","nat","-F",CHAIN,NULL};
 char *remove[]={"iptables","-t","nat","-X",CHAIN,NULL};
 (void)command(flush);(void)command(remove);return 0;
}
int main(int argc,char **argv) {
 if(argc==2 && (!strcmp(argv[1],"--firewall") || !strcmp(argv[1],"--disable"))){
  int dir=directory(0);if(dir<0)return errno==ENOENT?0:1;
  int lock=lock_directory(dir);if(lock<0){close(dir);return 1;}
  int result=0;
  if(!strcmp(argv[1],"--disable"))result=cleanup();
  else if(!disabled()){
   char *data=NULL,iface[32];
   if(own_configuration(&data,iface,sizeof(iface))){free(data);if(running())result=ensure_firewall(iface);}
  }
  close(lock);close(dir);if(result)fputs("localmod: UPnP postrouting recovery failed\n",stderr);return result?1:0;
 }
 if(disabled()){
  int dir=directory(0);if(dir>=0){int lock=lock_directory(dir);if(lock>=0){(void)cleanup();close(lock);}close(dir);}
  execv(FACTORY,argv);perror("localmod factory UPnP exec");return 127;
 }
 int index=-1,joined=0;const char *input=NULL,*override_iface=NULL;
 for(int i=1;i<argc;i++){
  if(!strcmp(argv[i],"-f") && i+1<argc){index=++i;joined=0;input=argv[i];}
  else if(!strncmp(argv[i],"-f",2) && argv[i][2]){index=i;joined=1;input=argv[i]+2;}
  else if(!strcmp(argv[i],"-i") && i+1<argc)override_iface=argv[++i];
  else if(!strncmp(argv[i],"-i",2) && argv[i][2])override_iface=argv[i]+2;
 }
 if(input){
  size_t len=0;char *data=read_config(input,&len);if(!data){perror("localmod UPnP config read");return 1;}
  char setting[256]={0},iface[32]={0},chain[64]={0},secure[32]={0},thirdparty[32]={0};
  int declared=value(data,"ext_allow_private_ipv4",setting,sizeof(setting));
  int postrouting=value(data,"upnp_nat_postrouting_chain",chain,sizeof(chain));
  int secure_set=value(data,"secure_mode",secure,sizeof(secure));
  int thirdparty_set=value(data,"pcp_allow_thirdparty",thirdparty,sizeof(thirdparty));
  if(declared<0 || postrouting<0 || secure_set<0 || thirdparty_set<0 || value(data,"ext_ifname",iface,sizeof(iface))<0){free(data);return 1;}
  if(override_iface){if(!interface_valid(override_iface)){free(data);return 1;}snprintf(iface,sizeof(iface),"%s",override_iface);}
  int ours=!postrouting || !strcmp(chain,CHAIN);
  if(ours && !interface_valid(iface)){free(data);fputs("localmod: UPnP WAN interface unavailable\n",stderr);return 1;}
  char *adapted=malloc(len+512);if(!adapted){free(data);return 1;}
  memcpy(adapted,data,len);size_t used=len;adapted[used++]='\n';
  /* Preserve stock operation behind an upstream router. Explicit user policy
   * takes precedence; never replace ext_allow_private_ipv4=no. */
  if(!declared){const char *line="ext_allow_private_ipv4=yes\n";memcpy(adapted+used,line,strlen(line));used+=strlen(line);}
  if(!postrouting){const char *line="upnp_nat_postrouting_chain=" CHAIN "\n";memcpy(adapted+used,line,strlen(line));used+=strlen(line);}
  if(!thirdparty_set && secure_set && (!strcmp(secure,"yes") || !strcmp(secure,"no"))){
   const char *line=!strcmp(secure,"yes")?"pcp_allow_thirdparty=no\n":"pcp_allow_thirdparty=yes\n";
   memcpy(adapted+used,line,strlen(line));used+=strlen(line);
  }
  if(override_iface){int n=snprintf(adapted+used,len+512-used,"ext_ifname=%s\n",iface);if(n<0 || (size_t)n>=len+512-used){free(data);free(adapted);return 1;}used+=(size_t)n;}
  int dir=directory(1);int lock=dir<0?-1:lock_directory(dir);
  if(lock<0){if(dir>=0)close(dir);free(data);free(adapted);perror("localmod UPnP private directory");return 1;}
  int bad=0;
  if(!ours && cleanup())bad=1;
  if(!bad && write_private("miniupnpd.conf",adapted,used))bad=1;
  if(!bad && ours && ensure_firewall(iface))bad=1;
  close(lock);close(dir);free(data);free(adapted);
  if(bad){fputs("localmod: UPnP compatibility preparation failed\n",stderr);return 1;}
  argv[index]=joined?"-f" CONFIG:CONFIG;
 }
 execv(PROGRAM,argv);perror("localmod UPnP exec");return 127;
}
