#define _GNU_SOURCE
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/wait.h>
#include <unistd.h>
extern char *nvram_get(const char *);
extern int nvram_set(const char *,const char *),nvram_set_int(const char *,int);
extern int _eval(char *const[],const char *,int,int *);
static void step(const char *s){FILE *f=fopen("/tmp/hook_trace","a");fprintf(f,"WORK %s\n",s);fclose(f);}
int main(void){
 if(getenv("LD_PRELOAD"))return 1;
 nvram_set("jffs2_scripts","1");nvram_set("wan0_state_t","1");
 nvram_set("borrowed_source","vendor-buffer-preserved");
 nvram_set("unrelated_target",nvram_get("borrowed_source"));
 if(strcmp(nvram_get("unrelated_target"),"vendor-buffer-preserved"))return 5;
 step("nvram-buffer-preserved");
 if(mount("/dev/ubi0","/jffs","ubifs",0,NULL))return 2;
 nvram_set_int("wan0_state_t",2);nvram_set_int("wan0_state_t",2);
 if(fork()==0){nvram_set_int("wan1_state_t",2);exit(0);}wait(NULL);
 sigset_t set;siginfo_t info;sigemptyset(&set);sigwaitinfo(&set,&info);
 nvram_set("rc_service","restart_httpd;start_dnsmasq");char queue[256];strcpy(queue,nvram_get("rc_service"));char *cursor=queue,*part;
 while((part=strsep(&cursor,";"))){if(*part)step(part);if(!cursor)break;}
 nvram_set("rc_service","");nvram_set("rc_service_pid","");
 mount("/dev/sda1","/tmp/mnt/USB with space","ext4",0,NULL);umount("/tmp/mnt/USB with space");umount("/tmp/mnt/USB with space");
 char *dns[]={"dnsmasq","--log-async",NULL};if(_eval(dns,NULL,0,NULL)!=13)return 3;
 if(_eval(dns,NULL,0,NULL)!=13)return 4;
 nvram_set("jffs2_scripts","0");mount("/dev/sdb1","/tmp/mnt/disabled","ext4",0,NULL);nvram_set_int("wan2_state_t",2);
 nvram_set("jffs2_scripts","1");nvram_set_int("wan0_state_t_extra",2);
 for(int state=0;state<=6;state++)nvram_set_int("wan3_state_t",state);
 mount("/dev/sdc1","/tmp/mnt/remount","ext4",MS_REMOUNT,NULL);
 mount("/dev/sdc1","/tmp/mnt/bind","ext4",MS_BIND,NULL);
 sigwaitinfo(&set,&info);sigwaitinfo(&set,&info);
 sigwaitinfo(&set,&info);step("complete");return 0;
}
