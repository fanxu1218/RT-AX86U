/* SPDX-License-Identifier: MIT */
#ifndef LOCALMOD_RUNTIME_H
#define LOCALMOD_RUNTIME_H
#include <stddef.h>
#include <signal.h>
extern volatile sig_atomic_t lm_stopping;
#define LM_BASE "/tmp/.localmod"
#define LM_DISPATCH "/usr/libexec/localmod/dispatch.sh"
#define LM_BOOTSTRAP "/usr/libexec/localmod/bootstrap.sh"
#define LM_MAGIC 0x4c4d4532U
struct lm_event { unsigned magic; char name[32], arg1[4096], arg2[256]; };
int lm_directory(const char *path);
int lm_enabled(void);
int lm_run(char *const argv[], unsigned seconds);
int lm_dispatch(const struct lm_event *event);
int lm_emit(const char *name, const char *arg1, const char *arg2, int synchronous);
int lm_barrier(unsigned seconds);
#endif
