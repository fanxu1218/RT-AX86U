/* SPDX-License-Identifier: MIT; test-only kernel ABI boundary.
 * Execute the unchanged candidate restore adapter, then apply its output with
 * Alpine's legacy xtables engine. The vendor 4.1 ABI is a separate gate.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int execv(const char *path, char *const argv[]) {
    static int (*next)(const char *, char *const []);
    if (!next) next = dlsym(RTLD_NEXT,"execv");
    if (!next) { errno=ENOSYS; return -1; }
    if (strcmp(path,"/usr/sbin/xtables-multi")) return next(path,argv);
    unsigned count=0;
    while (argv[count] && count<128) count++;
    if (!count || count==128) { errno=E2BIG; return -1; }
    const char *name=strrchr(argv[0],'/'); name=name?name+1:argv[0];
    if (strcmp(name,"iptables-restore") && strcmp(name,"iptables-save")) {
        errno=EPROTO; return -1;
    }
    FILE *log=fopen("/tmp/owned-restore-kernel-boundary","a");
    if (!log) return -1;
    fprintf(log,"%s %s\n",path,name);fclose(log);
    char *mapped[134]={"/lib/ld-musl-aarch64.so.1","--library-path",
        "/fixture/lib","/fixture/xtables-legacy-multi",(char *)name};
    for (unsigned i=1;i<count;i++) mapped[4+i]=argv[i];
    mapped[4+count]=NULL;
    unsetenv("LD_PRELOAD");setenv("XTABLES_LIBDIR","/fixture/xtables",1);
    return next(mapped[0],mapped);
}
