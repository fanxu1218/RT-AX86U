/* Test only: emulate PID 1 at the official config generator's guard and capture
 * external launches. The generator and its configuration text are unmodified. */
#include <stdio.h>
#include <sys/types.h>
#include <stdarg.h>
pid_t getpid(void) { return 1; }
int _eval(char *const argv[], const char *path, int timeout, int *pid) {
    (void)path; (void)timeout;
    if(pid) *pid = 4200;
    fputs("OFFICIAL_EVAL", stdout);
    for (unsigned i=0; argv && argv[i] && i<40; i++) printf(" [%s]", argv[i]);
    putchar('\n'); return 0;
}
int system(const char *command) { printf("OFFICIAL_SYSTEM [%s]\n", command); return 0; }
int notify_rc(const char *command) { printf("OFFICIAL_NOTIFY [%s]\n", command); return 0; }
