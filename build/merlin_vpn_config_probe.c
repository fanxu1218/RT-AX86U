/* Test only: ask the retained official libvpn to produce its client config.
 * The companion fixture captures launches; no WAN or live router is involved. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    void *h = dlopen("/usr/lib/libvpn.so", RTLD_NOW | RTLD_GLOBAL);
    if (!h) { puts(dlerror()); return 1; }
    int (*set)(const char *, const char *) = dlsym(RTLD_DEFAULT, "nvram_set");
    void (*start)(int) = dlsym(h, "start_ovpn_client");
    if (!set || !start) return 2;
    const char *values[] = {"ntp_ready", "1", "vpn_clientx_eas", "1,", "vpn_client1_if", "tun",
      "vpn_client1_addr", "127.0.0.1", "vpn_client1_port", "35325",
      "vpn_client1_crypt", "tls", "vpn_client1_proto", "udp",
      "vpn_client1_comp", "-1", "vpn_client1_cipher", "AES-256-CBC",
      "vpn_client1_digest", "SHA256", "vpn_client1_firewall", "custom",
      "vpn_client1_nat", "0", "vpn_client1_bridge", "0",
      "vpn_client1_verb", "3", "vpn_client1_retry", "1",
      "vpn_client1_poll", "0", "vpn_client1_adns", "0", NULL};
    for (unsigned i=0; values[i]; i+=2) set(values[i], values[i+1]);
    set("vpn_client1_ncp_enable", argc > 1 ? argv[1] : "1");
    start(1);
    puts("OFFICIAL_LIBVPN_CLIENT_CONFIG_RETURNED");
    return 0;
}
