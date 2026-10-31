/* SPDX-License-Identifier: MIT
 * Synthetic NVRAM and absent board I/O for executing pinned vendor programs.
 * Login/session/password verification and TLS are deliberately NOT interposed.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static struct {char *key,*value;} entries[4096];static unsigned used;
static int initializing=1;
static int state_path(const char *key,char *path,size_t size){
 const char *base=getenv("NATIVE_STATE_DIRECTORY");
 if(!base || !key || !*key || strspn(key,"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.")!=strlen(key))return 0;
 return snprintf(path,size,"%s/%s",base,key)<(int)size;
}
static int memory_set(const char *key,const char *value){
 if(!key)return -1;unsigned i;for(i=0;i<used;i++)if(!strcmp(entries[i].key,key))break;
 if(i==used){if(used==4096)return -1;entries[i].key=strdup(key);used++;}
 if(entries[i].value && value && !strcmp(entries[i].value,value))return 0;
 free(entries[i].value);entries[i].value=value?strdup(value):NULL;return 0;
}
int nvram_set(const char *key,const char *value){
 int result=memory_set(key,value);char path[512];
 if(!result && !initializing && state_path(key,path,sizeof(path))){
  FILE *f=fopen(path,"w");if(!f)return -1;
  if(value){fputc('1',f);fputs(value,f);}else fputc('0',f);
  if(fclose(f))return -1;
 }
 return result;
}
char *nvram_get(const char *key){
 if(key && getenv("NATIVE_UU_CASE") && !strcmp(key,"ntp_ready") && access("/tmp/native-ntp-synced",F_OK)==0)return "1";
 if(!key)return NULL;char path[512];
 if(!initializing && state_path(key,path,sizeof(path))){
  FILE *f=fopen(path,"r");if(f){char b[8192];size_t n=fread(b,1,sizeof(b)-1,f);fclose(f);b[n]=0;
   memory_set(key,n && b[0]=='1'?b+1:NULL);
  }
 }
 for(unsigned i=0;i<used;i++)if(!strcmp(entries[i].key,key))return entries[i].value;
 return NULL;
}
int nvram_unset(const char *key){return nvram_set(key,NULL);}
int nvram_set_int(const char *key,int value){char s[32];snprintf(s,sizeof(s),"%d",value);return nvram_set(key,s);}
int nvram_get_int(const char *key){char *v=nvram_get(key);return v?atoi(v):0;}
int nvram_commit(void){return 0;}
int nvram_commit_x(void){return 0;}
int httpd_nvram_commit(void){return 0;}
char *nvram_pf_get(const char *prefix,const char *key){char k[256];snprintf(k,sizeof(k),"%s%s",prefix,key);return nvram_get(k);}
int nvram_pf_set(const char *prefix,const char *key,const char *value){char k[256];snprintf(k,sizeof(k),"%s%s",prefix,key);return nvram_set(k,value);}
int nvram_pf_get_int(const char *prefix,const char *key){char *v=nvram_pf_get(prefix,key);return v?atoi(v):0;}
int nvram_getall(char *out,int count){int at=0;for(unsigned i=0;i<used;i++)if(entries[i].value){int n=snprintf(out+at,(size_t)(count-at),"%s=%s",entries[i].key,entries[i].value);if(n<0 || n>=count-at)return -1;at+=n+1;}if(at<count)out[at]=0;return 0;}
int wl_ioctl(const char *ifname,int cmd,void *buf,int len){(void)ifname;(void)cmd;(void)buf;(void)len;errno=ENODEV;return -1;}
__attribute__((constructor)) static void load(void){
 FILE *f=fopen("/work/build/native_defaults.bin","rb");if(!f){perror("native defaults");abort();}
 char *k=NULL,*v=NULL;size_t kc=0,vc=0;while(getdelim(&k,&kc,0,f)>0 && getdelim(&v,&vc,0,f)>0)nvram_set(k,v);free(k);free(v);fclose(f);
 if(getenv("LD_PRELOAD"))fputs("PASS early stdio before adapter constructor\n",stderr);
 const char *values[]={"productid","RT-AX86U","odmpid","RT-AX86U","lan_ipaddr","192.168.77.1","lan_netmask","255.255.255.0","lan_ifname","lo","http_lanport","34080","https_lanport","34443","http_enable","2","http_username","admin","http_passwd","local-test-password","x_Setting","1","w_Setting","1","p_Setting","1","territory_code","CN/01","preferred_lang","EN","time_zone_x","UTC0","captcha_enable","0","wl_ifnames","","wl0_ifname","","wl1_ifname","","rc_support","https jffs2 uu_accel","https_crt_save","0","https_crt_gen","0","HTTPD_DBG","1","force_chgpass","0",NULL};
 for(unsigned i=0;values[i];i+=2)nvram_set(values[i],values[i+1]);
 if(getenv("NATIVE_CERT_CASE")){
  nvram_set("https_crt_save","1");nvram_set("le_enable","0");nvram_set("ntp_ready","1");
  nvram_set("sw_mode","1");nvram_set("jffs2_scripts","1");nvram_set("sc_skin","ASUSWRT");
  nvram_set("lan_hostname","local-fixture");nvram_set("wan0_ipaddr","0.0.0.0");nvram_set("wan1_ipaddr","0.0.0.0");
 }
 if(getenv("NATIVE_UU_CASE")){
  nvram_set("link_internet","2");nvram_set("no_ntp","0");nvram_set("ntp_ready","0");nvram_set("ntp_server0","fixture.invalid");
  nvram_set("territory_code",getenv("NATIVE_UU_TERRITORY")?getenv("NATIVE_UU_TERRITORY"):"CN/01");
  nvram_set("sw_mode",getenv("NATIVE_UU_MODE")?getenv("NATIVE_UU_MODE"):"1");
  nvram_set("et0macaddr","02:00:00:00:00:01");nvram_set("lan_hwaddr","02:00:00:00:00:01");
 }
 initializing=0;
}
#ifdef NATIVE_NVRAM_CLI
int main(int argc,char **argv){
 if(argc==3 && !strcmp(argv[1],"get")){char *v=nvram_get(argv[2]);puts(v?v:"");return 0;}
 if(argc==3 && !strcmp(argv[1],"set")){char *v=strchr(argv[2],'=');if(!v)return 2;*v++=0;return nvram_set(argv[2],v)?1:0;}
 if(argc==3 && !strcmp(argv[1],"unset"))return nvram_unset(argv[2])?1:0;
 if(argc==2 && !strcmp(argv[1],"commit"))return 0;
 return 2;
}
#endif
