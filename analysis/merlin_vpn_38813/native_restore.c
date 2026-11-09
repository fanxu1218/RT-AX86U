/* SPDX-License-Identifier: MIT
 * The native rc owns firewall/nat hooks; the restore adapter only protects
 * the software-center API rule. Never synthesize duplicate native events.
 */
#define lm_emit lm_native_restore_event_unused
#include "../../sources/localmod/restore.c"
int lm_native_restore_event_unused(const char *name,const char *a,const char *b,int sync){
 (void)name;(void)a;(void)b;(void)sync;return 0;
}
