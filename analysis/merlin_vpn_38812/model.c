/* SPDX-License-Identifier: MIT
 * Phase-one read-only adapter to the pinned Merlin libovpn configuration API.
 * This process never calls the PID-1 start/stop, policy-write or key APIs.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "vendor/openvpn_config.h"

#define PRIVATE "/usr/lib/localmod/vpn38812/"
static void quote(const char *p) {
 putchar('"');for(const unsigned char *s=(const unsigned char *)p;*s;s++){
  if(*s=='"'||*s=='\\')printf("\\%c",*s);
  else if(*s<32)printf("\\u%04x",*s);
  else putchar(*s);
 }putchar('"');
}
static int owner(void *p,const char *expected) {
 Dl_info i;return dladdr(p,&i) && i.dli_fname && !strcmp(i.dli_fname,expected);
}
int main(int argc,char **argv) {
 int client=argc==3 && !strcmp(argv[1],"client");
 int server=argc==3 && !strcmp(argv[1],"server");
 int capabilities=argc==2 && !strcmp(argv[1],"capabilities");
 if(!capabilities && ((!client&&!server)||strlen(argv[2])!=1||argv[2][0]<'1'||argv[2][0]>(client?'5':'2'))){
  fputs("Only capabilities, client 1..5 and server 1..2 are supported; writes and service control are not enabled.\n",stderr);return 64;
 }
 unsetenv("LD_PRELOAD");
 /* All four private objects and factory libnvram are direct DT_NEEDED
  * entries. The loader resolves their dependency cycle as one graph before
  * main, using this helper's RUNPATH only for this fresh process. */
 void *h=dlopen(PRIVATE "libovpn.so",RTLD_NOW|RTLD_GLOBAL);
 if(!h){fprintf(stderr,"Private Merlin library failed: %s\n",dlerror());return 70;}
 ovpn_cconf_t *(*get_client)(int)=dlsym(h,"ovpn_get_cconf");
 ovpn_sconf_t *(*get_server)(int)=dlsym(h,"ovpn_get_sconf");
 void *native_hook=dlsym(h,"run_custom_script");
 if(!get_client||!get_server||!owner(get_client,PRIVATE "libovpn.so")||!owner(native_hook,PRIVATE "libshared.so")){
  fputs("Unexpected library owner; refusing mixed configuration ABI.\n",stderr);return 70;
 }
 if(capabilities){
  if(!dlsym(h,"ovpn_start_client")||!dlsym(h,"ovpn_stop_client")||!dlsym(h,"ovpn_generate_client_key")||!dlsym(h,"amvpn_get_policy_rules"))return 70;
  puts("{\"upstream\":\"3004.388.12_2\",\"mode\":\"read_only_configuration\",\"private_libovpn\":true,\"private_libshared\":true,\"service_control_enabled\":false,\"whole_firmware_upgraded\":false}");return 0;
 }
 int unit=argv[2][0]-'0';
 printf("{\"kind\":\"%s\",\"unit\":%d,\"read_only\":true,",client?"client":"server",unit);
 if(client){
  ovpn_cconf_t *c=get_client(unit);if(!c)return 71;
  printf("\"port\":%d,\"interface\":",c->port);quote(c->if_name);
  printf(",\"protocol\":");quote(c->proto);
  printf(",\"tls_crypt\":%d,\"redirect_gateway\":%d,\"dns_mode\":%d,\"firewall_mode\":%d,\"nat\":%d,\"ncp_ciphers\":",c->tlscrypt,c->redirect_gateway,c->adns,c->fw,c->nat);quote(c->ncp_ciphers);
  memset(c,0,sizeof(*c));free(c);
 }else{
  ovpn_sconf_t *s=get_server(unit);if(!s)return 71;
  printf("\"port\":%d,\"interface\":",s->port);quote(s->if_name);
  printf(",\"protocol\":");quote(s->proto);
  printf(",\"tls_crypt\":%d,\"client_access\":%d,\"push_dns\":%d,\"ncp_ciphers\":",s->tlscrypt,s->push_lan,s->push_dns);quote(s->ncp_ciphers);
  memset(s,0,sizeof(*s));free(s);
 }
 puts("}");return 0;
}
