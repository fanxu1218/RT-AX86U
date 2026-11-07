/* SPDX-License-Identifier: MIT
 * Dispatch selected Merlin applications without exporting private TLS libraries
 * into their children. The payload's ELF RPATH selects its own dependencies.
 */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#ifdef LOCALMOD_OPENVPN
const char *lm_openvpn_legacy(int argc,char *const argv[]);
#endif

int main(int argc, char **argv) {
    (void)argc;
#ifdef LOCALMOD_MINIUPNPD
    execv("/usr/libexec/localmod/miniupnp-compat",argv);
    perror("localmod UPnP adapter exec");return 127;
#endif
    const char *name = strrchr(argv[0], '/');
    name = name ? name + 1 : argv[0];
#ifndef LOCALMOD_COMPONENT
#define LOCALMOD_COMPONENT "openvpn"
#endif
    const char *payload = LOCALMOD_COMPONENT;
    /* Use known read-only aliases to retain the kernel's process name too.
     * Factory libvpn invokes vpnclientN/vpnserverN links; SSH is multicall. */
    const char *aliases[] = {"dropbear", "dropbearkey", "dbclient", "ssh", NULL};
    if (!strcmp(payload, "dropbearmulti"))
        for (unsigned i = 0; aliases[i]; i++)
            if (!strcmp(name, aliases[i])) payload = aliases[i];
    if (!strcmp(payload, "openvpn") && strlen(name) == 10 &&
        (!strncmp(name, "vpnclient", 9) || !strncmp(name, "vpnserver", 9)) &&
        name[9] >= '1' && name[9] <= '5') payload = name;
    int use_factory = access("/jffs/localmod-disabled", F_OK) == 0 ||
                      access("/jffs/localmod-merlin-disabled", F_OK) == 0;
#ifdef LOCALMOD_OPENVPN
    if(access("/jffs/localmod-merlin-openvpn-disabled",F_OK)==0)use_factory=1;
    if(!use_factory){
        const char *reason=lm_openvpn_legacy(argc,argv);
        if(reason){use_factory=1;fprintf(stderr,"localmod: retained factory OpenVPN for configured legacy option %s\n",reason);}
    }
#endif
    const char *family = use_factory ? "vendor" : "bin";
    char path[160];
    int n = snprintf(path, sizeof(path), "/usr/libexec/localmod/merlin/%s/%s", family, payload);
    if (n < 0 || (unsigned)n >= sizeof(path)) return 127;
    /* argv[0] must survive: Dropbear selects its applet from it, and the
     * original rc uses the normal names to find and stop running services. */
    execv(path, argv);
    perror("localmod component exec");
    return 127;
}
