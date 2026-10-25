#define _GNU_SOURCE
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
static struct {char key[64],value[256];} values[32];static unsigned used;
static void logline(const char *a,const char *b){FILE *f=fopen("/tmp/hook_trace","a");fprintf(f,"VENDOR %s %s\n",a,b?b:"");fclose(f);}
char *nvram_get(const char *key){static char shared_buffer[256];for(unsigned i=0;i<used;i++)if(!strcmp(values[i].key,key)){strcpy(shared_buffer,values[i].value);return shared_buffer;}return NULL;}
int nvram_set(const char *key,const char *value){
 unsigned i;for(i=0;i<used;i++)if(!strcmp(values[i].key,key))break;
 if(i==used)used++;snprintf(values[i].key,sizeof(values[i].key),"%s",key);snprintf(values[i].value,sizeof(values[i].value),"%s",value);
 if(!strcmp(key,"jffs2_scripts")){FILE *f=fopen("/tmp/hook_script_flag","w");fputs(value,f);fclose(f);}return 0;
}
int nvram_set_int(const char *key,int number){char n[32];snprintf(n,sizeof(n),"%d",number);return nvram_set(key,n);}
int mount(const char *src,const char *dest,const char *type,unsigned long flags,const void *data){(void)src;(void)type;(void)flags;(void)data;logline("mount",dest);return 0;}
int umount(const char *path){static int attempt;logline("umount",path);if(attempt++==0){errno=EBUSY;return -1;}return 0;}
int umount2(const char *path,int flags){(void)flags;logline("umount2",path);return 0;}
int sigwaitinfo(const sigset_t *set,siginfo_t *info){(void)set;static int step;int signals[]={SIGUSR1,SIGHUP,SIGUSR1,SIGQUIT};int sig=signals[step<4?step++:3];if(info)info->si_signo=sig;logline("wait","");return sig;}
int _eval(char *const argv[],const char *path,int timeout,int *pid){(void)path;(void)timeout;(void)pid;logline("eval",argv[0]);return 13;}
