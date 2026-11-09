/* SPDX-License-Identifier: MIT; test-only board boundary for the real launcher.
 * Let the production launcher select its real rc/vendor and preload path, then
 * add only the owned board/notification fixtures to that one child. Never ship.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int execv(const char *path,char *const argv[]){
 static int (*next)(const char *,char *const[]);
 if(!next)next=dlsym(RTLD_NEXT,"execv");
 if(!next){errno=ENOSYS;return -1;}
 if(!strcmp(path,"/usr/libexec/localmod/rc.vendor")){
  const char *selected=getenv("LD_PRELOAD");
  if(!selected || strcmp(selected,"/usr/lib/localmod/native_boot_bridge.so")){errno=EPROTO;return -1;}
  FILE *f=fopen("/tmp/native-launcher-forwarded","a");
  if(!f)return -1;fputs(path,f);fputc('\n',f);fclose(f);
  f=fopen("/tmp/native-launcher-argv0","a");
  if(!f)return -1;fputs(argv[0],f);fputc('\n',f);fclose(f);
  // binfmt's QEMU-user re-entry replaces argv[0] with the executable path.
  // Preserve exactly what the production launcher supplied via explicit -0;
  // this adaptation belongs only to the emulator boundary, never firmware.
  unsigned count=0;while(argv[count] && count<128)count++;
  if(count==128){errno=E2BIG;return -1;}
  char *mapped[138]={"/usr/bin/qemu-arm","-0",argv[0],"-L","/","-E",
   "LD_PRELOAD=/usr/lib/localmod/native_boot_bridge.so:/work/build/native_hw_fixture.so:/work/build/native_uu_transport.so",(char *)path};
  for(unsigned i=1;i<count;i++)mapped[7+i]=argv[i];mapped[7+count]=NULL;
  unsetenv("LD_PRELOAD");
  return next("/usr/bin/qemu-arm",mapped);
 }
 return next(path,argv);
}
