/* SPDX-License-Identifier: MIT; test native writers and notification APIs.
 * Fresh synthetic profiles only, in the RAM-only router of a no-NIC VM.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "vendor/openvpn_config.h"
static int (*set)(const char *,const char *);
static void field(const char *kind,int unit,const char *key,const char *value){
 char name[160];snprintf(name,sizeof(name),"vpn_%s%d_%s",kind,unit,key);
 if(set(name,value))exit(3);
}
#define GET(name,type) type name=dlsym(lib,#name);if(!name){fprintf(stderr,"missing %s\n",#name);return 2;}
typedef void (*setup_fn)(ovpn_type_t,int);
typedef void (*write_c_fn)(ovpn_cconf_t *,int);
typedef void (*write_s_fn)(ovpn_sconf_t *,int);
typedef void (*control_fn)(int);
typedef int (*custom_fn)(ovpn_type_t,int,char *);
typedef ovpn_cconf_t *(*get_c_fn)(int);
typedef ovpn_sconf_t *(*get_s_fn)(int);
int main(void){
 void *lib=dlopen("/usr/lib/libovpn.so",RTLD_NOW|RTLD_GLOBAL);
 if(!lib){fprintf(stderr,"native VPN loader: %s\n",dlerror());return 1;}
 set=dlsym(RTLD_DEFAULT,"nvram_set");if(!set)return 2;
 GET(ovpn_setup_dirs,setup_fn);GET(ovpn_write_client_config,write_c_fn);GET(ovpn_write_server_config,write_s_fn);
 GET(ovpn_get_cconf,get_c_fn);GET(ovpn_get_sconf,get_s_fn);GET(set_ovpn_custom,custom_fn);
 GET(ovpn_start_client,control_fn);GET(ovpn_stop_client,control_fn);GET(ovpn_start_server,control_fn);GET(ovpn_stop_server,control_fn);
 void (*postconf)(char *,char *)=dlsym(RTLD_DEFAULT,"run_postconf");if(!postconf)return 2;
 Dl_info owner;if(!dladdr(ovpn_get_cconf,&owner) || strcmp(owner.dli_fname,"/usr/lib/libovpn.so"))return 4;
 mkdir("/jffs/openvpn",0700);mkdir("/etc/openvpn",0700);
 for(int server=0;server<2;server++){
  const char *kind=server?"server":"client";int max=server?2:5;
  for(int unit=1;unit<=max;unit++){
   const char *pairs[]={"if",unit%2?"tun":"tap","proto","udp","addr","127.0.0.1","nm","255.255.255.0","sn","10.8.0.0","r1","192.168.77.100","r2","192.168.77.110","comp","-1","ncp_ciphers","AES-256-GCM:AES-128-GCM","digest","SHA256","verb","3","connretry","1","fw","2","nat","1","adns","3","rgw","3","client_access","2","pdns","1",NULL};
   for(unsigned i=0;pairs[i];i+=2)field(kind,unit,pairs[i],pairs[i+1]);
   char port[32],custom[128],name[64],config[160];
   snprintf(port,sizeof(port),"%d",(server?35420:35320)+unit);field(kind,unit,"port",port);
   snprintf(custom,sizeof(custom),"setenv LOCALMOD_OWNED_%s%d 1\n",kind,unit);
   set_ovpn_custom(server?OVPN_TYPE_SERVER:OVPN_TYPE_CLIENT,unit,custom);
   ovpn_setup_dirs(server?OVPN_TYPE_SERVER:OVPN_TYPE_CLIENT,unit);
   if(server){ovpn_sconf_t *c=ovpn_get_sconf(unit);if(!c)return 5;ovpn_write_server_config(c,unit);free(c);}
   else{ovpn_cconf_t *c=ovpn_get_cconf(unit);if(!c)return 5;ovpn_write_client_config(c,unit);free(c);}
   snprintf(name,sizeof(name),"openvpn%s%d",kind,unit);
   snprintf(config,sizeof(config),"/etc/openvpn/%s%d/config.ovpn",kind,unit);postconf(name,config);
   if(server){ovpn_start_server(unit);ovpn_stop_server(unit);}else{ovpn_start_client(unit);ovpn_stop_client(unit);}
   printf("NATIVE_VPN_GENERATED %s%d\n",kind,unit);
  }
 }
 puts("NATIVE_VPN_WRITERS_RETURNED");return 0;
}
