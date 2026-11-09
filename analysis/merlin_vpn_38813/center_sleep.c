/* SPDX-License-Identifier: MIT
 * Software-center PATH helper: native BusyBox lacks fractional sleep.
 * Keep the system applet and plugin-owned tools unchanged.
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

int main(int argc, char **argv) {
    long double total = 0;
    const long double limit = sizeof(time_t) == 4 ? INT32_MAX : INT64_MAX;
    if (argc < 2) goto invalid;
    for (int i = 1; i < argc; i++) {
        char *end;
        errno = 0;
        long double value = strtold(argv[i], &end);
        if (end == argv[i] || errno || !isfinite(value) || value < 0)
            goto invalid;
        long double scale = 1;
        if (*end) {
            if (end[1]) goto invalid;
            switch (*end) {
                case 's': break;
                case 'm': scale = 60; break;
                case 'h': scale = 3600; break;
                case 'd': scale = 86400; break;
                default: goto invalid;
            }
        }
        total += value * scale;
        if (!isfinite(total) || total > limit) goto invalid;
    }
    struct timespec delay;
    delay.tv_sec = (time_t)total;
    delay.tv_nsec = (long)((total - (long double)delay.tv_sec) * 1000000000L);
    if (delay.tv_nsec >= 1000000000L) delay.tv_nsec = 999999999L;
    while (nanosleep(&delay, &delay)) {
        if (errno == EINTR) continue;
        perror("sleep");
        return 1;
    }
    return 0;
invalid:
    fputs("sleep: expected nonnegative seconds or a duration with s/m/h/d suffix\n", stderr);
    return 1;
}
