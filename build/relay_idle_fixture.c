/* Same production receive helper, shorter idle argument for bounded testing. */
#include "../sources/localmod/httpd_bridge.c"
#include <signal.h>
#include <sys/wait.h>
static volatile sig_atomic_t signals;
static void on_signal(int sig){(void)sig;signals++;}
int main(void){
 int pair[2];if(socketpair(AF_UNIX,SOCK_STREAM,0,pair))return 1;
 struct sigaction a={.sa_handler=on_signal,.sa_flags=SA_RESTART};sigemptyset(&a.sa_mask);sigaction(SIGALRM,&a,NULL);
 pid_t parent=getpid(),child=fork();if(child<0)return 2;
 if(!child){for(int i=0;i<80;i++){usleep(20000);kill(parent,SIGALRM);}_exit(0);}
 struct timespec begin,end;clock_gettime(CLOCK_MONOTONIC,&begin);char byte;
 ssize_t n=receive_response(pair[0],&byte,1,1);int saved=errno;clock_gettime(CLOCK_MONOTONIC,&end);
 kill(child,SIGKILL);waitpid(child,NULL,0);close(pair[0]);close(pair[1]);
 double elapsed=end.tv_sec-begin.tv_sec+(end.tv_nsec-begin.tv_nsec)/1e9;
 printf("RELAY_IDLE_RESULT result=%zd errno=%d signals=%d seconds=%.3f production_idle_seconds=120 test_idle_seconds=1\n",n,saved,(int)signals,elapsed);
 if(n!=-1||(saved!=ETIMEDOUT&&saved!=EAGAIN)||signals<3||elapsed<0.9||elapsed>4)return 3;
 puts("PASS repeated_signals_do_not_restart_the_receive_idle_deadline");return 0;
}
