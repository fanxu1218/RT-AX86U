/* SPDX-License-Identifier: MIT; owned notification boundary, not PID 1. */
#include <stdio.h>
int notify_rc(const char *command) {
 FILE *f=fopen("/tmp/owned-vpn-notifications","a");if(!f)return -1;
 fprintf(f,"%s\n",command);return fclose(f);
}
