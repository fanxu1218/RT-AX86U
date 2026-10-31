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
int nvram_set(const char *key,const char *value){
 if(!key)return -1;unsigned i;for(i=0;i<used;i++)if(!strcmp(entries[i].key,key))break;
 if(i==used){if(used==4096)return -1;entries[i].key=strdup(key);used++;}
 free(entries[i].value);entries[i].value=value?strdup(value):NULL;return 0;
}
char *nvram_get(const char *key){if(key && getenv("NATIVE_UU_CASE") && !strcmp(key,"ntp_ready") && access("/tmp/native-ntp-synced",F_OK)==0)return "1";if(!key)return NULL;for(unsigned i=0;i<used;i++)if(!strcmp(entries[i].key,key))return entries[i].value;return NULL;}
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
 if(getenv("NATIVE_UU_CASE")){
  nvram_set("link_internet","2");nvram_set("no_ntp","0");nvram_set("ntp_server0","fixture.invalid");
  nvram_set("territory_code",getenv("NATIVE_UU_TERRITORY")?getenv("NATIVE_UU_TERRITORY"):"CN/01");
  nvram_set("sw_mode",getenv("NATIVE_UU_MODE")?getenv("NATIVE_UU_MODE"):"1");
  nvram_set("et0macaddr","02:00:00:00:00:01");nvram_set("lan_hwaddr","02:00:00:00:00:01");
 }

}
