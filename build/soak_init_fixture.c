/* Test-only orphan reaper for a minimal VM whose PID 1 is a shell.
 * It reaps only children orphaned to this subreaper, never active descendants. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>
int main(int argc,char **argv){
 if(argc<2||prctl(PR_SET_CHILD_SUBREAPER,1))return 2;
 pid_t main=fork();if(main<0)return 3;
 if(!main){execv(argv[1],argv+1);perror("soak exec");_exit(127);}
 unsigned reaped=0;int status;
 for(;;){pid_t pid=waitpid(-1,&status,0);if(pid<0){if(errno==EINTR)continue;return 4;}
  if(pid==main){printf("SOAK_REAPER orphans_reaped=%u\n",reaped);return WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);}
  reaped++;
 }
}
