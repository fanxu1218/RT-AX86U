/* SPDX-License-Identifier: MIT
 * Persistent install checkpoints. Recovery runs only in a later boot, before
 * skipd/plugins start. Never traverse or clean the rest of JFFS (including UU).
 */
#define _GNU_SOURCE
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define BASE "/jffs/.localmod/plugin-txn"
#define ACTIVE BASE "/active"
static const char *targets[]={"/jffs/.koolshare","/jffs/.localmod/ksdb"};
static const char *names[]={"center","database"};
static char boot[80],owner[120];
static int fail(const char *message){fprintf(stderr,"plugin checkpoint: %s: %s\n",message,strerror(errno));return 1;}
static int exists(const char *p){struct stat st;return lstat(p,&st)==0;}
static int directory(const char *p){struct stat s;return !lstat(p,&s)&&S_ISDIR(s.st_mode)&&!S_ISLNK(s.st_mode);}
static int join(char *out,const char *a,const char *b){if(snprintf(out,PATH_MAX,"%s/%s",a,b)>=PATH_MAX){errno=ENAMETOOLONG;return -1;}return 0;}
static int flushdir(const char *p){int fd=open(p,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);if(fd<0)return -1;int r=fsync(fd);close(fd);return r;}
static int textread(const char *p,char *out,size_t cap){int fd=open(p,O_RDONLY|O_NOFOLLOW);if(fd<0)return -1;ssize_t n=read(fd,out,cap-1);close(fd);if(n<0)return -1;out[n]=0;return 0;}
static int readfield(const char *name,char *out,size_t cap){char p[PATH_MAX];if(join(p,ACTIVE,name))return -1;return textread(p,out,cap);}
static int put_at(const char *dir,const char *name,const char *value){
 char p[PATH_MAX],tmp[PATH_MAX];if(join(p,dir,name)||snprintf(tmp,sizeof(tmp),"%s.new",p)>=(int)sizeof(tmp))return -1;
 int fd=open(tmp,O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW,0600);if(fd<0)return -1;
 size_t left=strlen(value);const char *at=value;while(left){ssize_t n=write(fd,at,left);if(n<0&&errno==EINTR)continue;if(n<=0){close(fd);return -1;}at+=n;left-=n;}
 if(fsync(fd)){close(fd);return -1;}if(close(fd)||rename(tmp,p)||flushdir(dir))return -1;return 0;
}
static int put(const char *name,const char *value){return put_at(ACTIVE,name,value);}
static int flag(const char *name){char p[PATH_MAX];return !join(p,ACTIVE,name)&&exists(p);}
static int erase(const char *p){
 struct stat st;if(lstat(p,&st))return errno==ENOENT?0:-1;
 if(!S_ISDIR(st.st_mode)||S_ISLNK(st.st_mode))return unlink(p);
 DIR *d=opendir(p);if(!d)return -1;int r=0;struct dirent *e;
 while((e=readdir(d)))if(strcmp(e->d_name,".")&&strcmp(e->d_name,"..")){char q[PATH_MAX];if(join(q,p,e->d_name)||erase(q)){r=-1;break;}}
 closedir(d);return r?r:rmdir(p);
}
static int remove_active(void){
 /* Detach durably before deleting any marker/snapshot. A cut during garbage
  * collection must never turn an already committed operation into rollback. */
 if(!directory(ACTIVE)){errno=EINVAL;return -1;}
 char discard[PATH_MAX];int found=0;
 for(int i=0;i<100;i++){
  snprintf(discard,sizeof(discard),BASE "/discard-%s-%d-%d",boot,getpid(),i);
  if(!exists(discard)){found=1;break;}
 }
 if(!found){errno=EEXIST;return -1;}
 if(rename(ACTIVE,discard)||flushdir(BASE))return -1;
 if(erase(discard)||flushdir(BASE))fputs("checkpoint garbage retained; no active operation\n",stderr);
 return 0;
}
static int token(pid_t pid,char *out,size_t cap){
 char p[80],b[4096];snprintf(p,sizeof(p),"/proc/%d/stat",pid);if(textread(p,b,sizeof(b)))return -1;
 char *at=strrchr(b,')');if(!at||at[1]!=' '||at[2]=='Z')return -1;at+=2;
 char *save=NULL,*word=strtok_r(at," ",&save);for(int field=3;word&&field<22;field++)word=strtok_r(NULL," ",&save);
 if(!word)return -1;return snprintf(out,cap,"%d:%s",pid,word)>=(int)cap?-1:0;
}
static int own_live(void){char b[120],now[120];if(readfield("owner",b,sizeof(b)))return 0;char *end;long p=strtol(b,&end,10);return p>1&&*end==':'&&!token((pid_t)p,now,sizeof(now))&&!strcmp(b,now);}
static int same_owner(pid_t p){char expected[120];return !readfield("owner",expected,sizeof(expected))&&!token(p,owner,sizeof(owner))&&!strcmp(owner,expected);}
static int child(const char *a,const char *b,const char *c){
 pid_t p=fork();if(p<0)return -1;if(!p){execl(a,a,b,c,(char *)NULL);_exit(127);}int s;while(waitpid(p,&s,0)<0)if(errno!=EINTR)return -1;return WIFEXITED(s)&&WEXITSTATUS(s)==0?0:-1;
}
static int safe_name(const char *s){return *s&&strlen(s)<=64&&strspn(s,"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")==strlen(s);}
static int transfer(int fd,void *buf,size_t length,int writing){char *p=buf;while(length){ssize_t n=writing?write(fd,p,length):read(fd,p,length);if(n<0&&errno==EINTR)continue;if(n<=0){errno=EIO;return -1;}p+=n;length-=n;}return 0;}
static int db_connect(void){int fd=socket(AF_UNIX,SOCK_STREAM,0);if(fd<0)return -1;struct sockaddr_un a={.sun_family=AF_UNIX};strcpy(a.sun_path,"/tmp/.skipd_server_sock");struct timeval t={5,0};setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&t,sizeof(t));setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&t,sizeof(t));if(connect(fd,(void *)&a,sizeof(a))){close(fd);return -1;}return fd;}
static int db_send(int fd,const char *command,size_t n){if(n>8000000){errno=EFBIG;return -1;}char h[17];snprintf(h,sizeof(h),"magicv1 %07u ",(unsigned)n);return transfer(fd,h,16,1)||transfer(fd,(void *)command,n,1)?-1:0;}
static char *db_receive(int fd,size_t *length){char h[17];if(transfer(fd,h,16,0))return NULL;h[16]=0;if(memcmp(h,"magicv1 ",8)||h[15]!=' '){errno=EPROTO;return NULL;}for(int i=8;i<15;i++)if(h[i]<'0'||h[i]>'9'){errno=EPROTO;return NULL;}unsigned n=(unsigned)strtoul(h+8,NULL,10);if(!n||n>8000000){errno=EFBIG;return NULL;}char *b=malloc(n+1);if(!b)return NULL;if(transfer(fd,b,n,0)){free(b);return NULL;}b[n]=0;*length=n;return b;}
static int db_snapshot(const char *dir){
 if(mkdir(dir,0700))return -1;char path[PATH_MAX];join(path,dir,"values.bin");int out=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);if(out<0)return -1;
 int fd=db_connect(),r=-1;uint64_t bytes=0;const char cmd[]="list __all__\n";
 if(fd<0||transfer(out,"LMDB1\0",6,1)||db_send(fd,cmd,sizeof(cmd)-1))goto done;
 for(;;){size_t n;char *b=db_receive(fd,&n);if(!b)goto done;
  if(n<6||memcmp(b,"list ",5)){free(b);errno=EPROTO;goto done;}char *split=memchr(b+5,' ',n-5);if(!split){free(b);errno=EPROTO;goto done;}
  size_t key=(size_t)(split-(b+5)),value=n-(size_t)(split+1-b);
  if(key==7&&!memcmp(b+5,"__all__",7)&&value==8&&!memcmp(split+1,"__end__\n",8)){free(b);uint32_t end[2]={0,0};if(transfer(out,end,sizeof(end),1))goto done;r=0;break;}
  bytes+=key+value+8;if(!key||key>2048||bytes>32*1024*1024||memchr(b,0,n)){free(b);errno=EFBIG;goto done;}
  uint32_t sizes[2]={(uint32_t)key,(uint32_t)value};int bad=transfer(out,sizes,sizeof(sizes),1)||transfer(out,b+5,key,1)||transfer(out,split+1,value,1);free(b);if(bad)goto done;
 }
 if(fsync(out)||flushdir(dir))r=-1;
done:if(fd>=0)close(fd);if(close(out))r=-1;return r;
}
static int restore_values(void){
 char path[PATH_MAX];join(path,ACTIVE,"database/values.bin");int in=open(path,O_RDONLY|O_NOFOLLOW);if(in<0)return -1;int fd=db_connect(),r=-1;char magic[6];uint64_t bytes=0;
 if(fd<0||transfer(in,magic,6,0)||memcmp(magic,"LMDB1\0",6))goto done;
 for(;;){uint32_t sizes[2];if(transfer(in,sizes,sizeof(sizes),0))goto done;if(!sizes[0]&&!sizes[1])break;bytes+=sizes[0]+(uint64_t)sizes[1]+8;
  if(!sizes[0]||sizes[0]>2048||sizes[1]>7900000||bytes>32*1024*1024){errno=EINVAL;goto done;}
  size_t length=4+sizes[0]+1+sizes[1]+1;char *b=malloc(length);if(!b)goto done;memcpy(b,"set ",4);
  if(transfer(in,b+4,sizes[0],0)||transfer(in,b+5+sizes[0],sizes[1],0)){free(b);goto done;}b[4+sizes[0]]=' ';b[length-1]='\n';
  if(memchr(b+4,' ',sizes[0])||memchr(b+4,'\n',sizes[0])||memchr(b,0,length)||db_send(fd,b,length)){free(b);goto done;}free(b);
  size_t n;char *response=db_receive(fd,&n);if(!response)goto done;int ok=n>=4&&!memcmp(response,"set ",4)&&!strcmp(response+n-4," ok\n");free(response);if(!ok){errno=EPROTO;goto done;}
 }
 /* A native read is the packaged skipd commit barrier, including empty data. */
 {const char barrier[]="list __localmod_recovery_barrier__\n";if(db_send(fd,barrier,sizeof(barrier)-1))goto done;size_t n;char *b=db_receive(fd,&n);if(!b)goto done;int ok=n>=8&&!memcmp(b+n-8,"__end__\n",8);free(b);if(!ok){errno=EPROTO;goto done;}}
 r=0;
done:if(fd>=0)close(fd);close(in);return r;
}
static int size_tree(const char *p,uint64_t *bytes,int depth){
 if(depth>64){errno=ELOOP;return -1;}struct stat st;if(lstat(p,&st))return -1;
 *bytes+=8192;if(S_ISREG(st.st_mode))*bytes+=(uint64_t)st.st_size;
 if(S_ISDIR(st.st_mode)){DIR *d=opendir(p);if(!d)return -1;struct dirent *e;int r=0;while((e=readdir(d)))if(strcmp(e->d_name,".")&&strcmp(e->d_name,"..")){char q[PATH_MAX];if(join(q,p,e->d_name)||size_tree(q,bytes,depth+1)){r=-1;break;}}closedir(d);return r;}return 0;
}
static int copy_tree(const char *src,const char *dst,const char *relative,dev_t device,int depth){
 if(depth>64){errno=ELOOP;return -1;}
 if(!strcmp(relative,"perp/.control")||!strncmp(relative,"perp/.control/",14))return 0;
 struct stat st;if(lstat(src,&st))return -1;if(st.st_dev!=device){errno=EXDEV;return -1;}
 if(S_ISDIR(st.st_mode)){
  if(mkdir(dst,0700))return -1;DIR *d=opendir(src);if(!d)return -1;struct dirent *e;int r=0;
  while((e=readdir(d)))if(strcmp(e->d_name,".")&&strcmp(e->d_name,"..")){char a[PATH_MAX],b[PATH_MAX],rel[PATH_MAX];
   if(join(a,src,e->d_name)||join(b,dst,e->d_name)||snprintf(rel,sizeof(rel),"%s%s%s",relative,*relative?"/":"",e->d_name)>=(int)sizeof(rel)||copy_tree(a,b,rel,device,depth+1)){r=-1;break;}}
  closedir(d);if(r||chown(dst,st.st_uid,st.st_gid)||chmod(dst,st.st_mode&07777)||flushdir(dst))return -1;return 0;
 }
 if(S_ISLNK(st.st_mode)){char link[PATH_MAX];ssize_t n=readlink(src,link,sizeof(link)-1);if(n<0||n>=(ssize_t)sizeof(link)-1)return -1;link[n]=0;return symlink(link,dst)||lchown(dst,st.st_uid,st.st_gid)?-1:0;}
 if(!S_ISREG(st.st_mode))return 0; /* ephemeral FIFO/socket, never user file contents */
 int in=open(src,O_RDONLY|O_NOFOLLOW);if(in<0)return -1;struct stat before,after;if(fstat(in,&before)){close(in);return -1;}
 int out=open(dst,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);if(out<0){close(in);return -1;}
 char b[32768];ssize_t n;int r=0;while((n=read(in,b,sizeof(b)))>0){ssize_t at=0;while(at<n){ssize_t w=write(out,b+at,(size_t)(n-at));if(w<0&&errno==EINTR)continue;if(w<=0){r=-1;break;}at+=w;}if(r)break;}
 if(n<0||fstat(in,&after)||before.st_ino!=after.st_ino||before.st_size!=after.st_size||before.st_mtim.tv_sec!=after.st_mtim.tv_sec||before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec){errno=EBUSY;r=-1;}
 if(!r&&(fchown(out,st.st_uid,st.st_gid)||fchmod(out,st.st_mode&07777)))r=-1;
 struct timespec times[]={st.st_atim,st.st_mtim};if(!r&&(futimens(out,times)||fsync(out)))r=-1;
 close(in);if(close(out))r=-1;return r;
}
static int begin(pid_t pid,const char *log){
 if(strcmp(log,"soft_install_log.txt")&&strcmp(log,"soft_log.txt")){errno=EINVAL;return fail("invalid log name");}
 if(mkdir(BASE,0700)&&errno!=EEXIST)return fail("create store");if(!directory(BASE)||chmod(BASE,0700))return fail("invalid store");
 if(exists(ACTIVE)){
  if(!directory(ACTIVE))return fail("invalid active record");
  if(flag("committed")){if(remove_active())return fail("remove committed record");}
  else {fputs(own_live()?"plugin operation already active\n":"interrupted operation requires reboot recovery\n",stderr);return own_live()?10:11;}
 }
 if(token(pid,owner,sizeof(owner))||mkdir(ACTIVE,0700))return fail("create intent");
 if(put("version","1")||put("boot",boot)||put("owner",owner)||put("log",log)||put("state","preparing")||flushdir(BASE))return fail("persist intent");return 0;
}
static int checkpoint(pid_t pid,const char *module){
 if(!same_owner(pid)||!safe_name(module)){errno=EINVAL;return fail("checkpoint owner/module");}
 if(put("module",module))return fail("record module");
 uint64_t need=2*1024*1024;for(int i=0;i<2;i++)if(!directory(targets[i])||size_tree(targets[i],&need,0))return fail("inspect checkpoint tree");
 struct statvfs fs;if(statvfs("/jffs",&fs)||need>(uint64_t)fs.f_bavail*fs.f_frsize){errno=ENOSPC;return fail("insufficient checkpoint space; installer not run");}
 char dst[PATH_MAX];struct stat st;
 if(join(dst,ACTIVE,"database")||db_snapshot(dst))return fail("snapshot database; installer not run");
 if(lstat(targets[0],&st)||join(dst,ACTIVE,"center")||copy_tree(targets[0],dst,"",st.st_dev,0))return fail("checkpoint copy; installer not run");
 if(!same_owner(pid)){errno=ECANCELED;return fail("owner interrupted during checkpoint");}
 if(put("ready","1")||put("state","mutating"))return fail("seal checkpoint");return 0;
}
static int finish(pid_t pid,int code){
 if(!directory(ACTIVE))return 0;
 char recorded[120];if(readfield("owner",recorded,sizeof(recorded))||strtol(recorded,NULL,10)!=pid){errno=EINVAL;return fail("finish identity mismatch");}
 if(!same_owner(pid)){put("state","interrupted");return 1;}
 if(!flag("ready")){if(remove_active())return fail("discard preparation");return 0;}
 if(code){if(put("state","interrupted"))return fail("mark failed mutation");return 0;}
 /* Caller has read skipd's commit barrier. Persist data before the commit point. */
 sync();if(put("committed","1"))return fail("persist commit point");
 if(remove_active())fputs("plugin checkpoint committed; cleanup deferred\n",stderr);
 return 0;
}
static int recover(void){
 if(!exists(ACTIVE))return 0;if(!directory(ACTIVE))return fail("invalid recovery record");
 char previous[80]="";readfield("boot",previous,sizeof(previous));
 if(flag("committed"))return remove_active()?fail("committed cleanup"):0;
 if(!strcmp(previous,boot)){errno=EBUSY;return fail("same-boot transaction; reboot before recovery");}
 if(!flag("ready")){if(put_at(BASE,"notice","preparation-interrupted")||remove_active())return fail("incomplete checkpoint cleanup");return 0;}
 /* prepare and start can both invoke bootstrap. After a partial replay the
  * database may already be live: never move it again in this recovery boot. */
 char attempted[80]="";readfield("recovery-boot",attempted,sizeof(attempted));
 if(!strcmp(attempted,boot)){errno=EBUSY;return fail("recovery already attempted in this boot; reboot before retry");}
 if(put("recovery-boot",boot))return fail("persist recovery boot identity");
 /* Every rename is restartable. Never overwrite a quarantined interrupted tree. */
 for(int i=0;i<1;i++){
  char saved[PATH_MAX],failed[PATH_MAX],label[80];join(saved,ACTIVE,names[i]);snprintf(label,sizeof(label),"failed-%s",names[i]);join(failed,ACTIVE,label);
  if(exists(saved)){
   if(!directory(saved)||(exists(targets[i])&&!directory(targets[i]))){errno=EINVAL;return fail("invalid recovery tree; retained all copies");}
   if(exists(targets[i])){if(exists(failed)){errno=EEXIST;return fail("unexpected recovery target; retained all copies");}if(rename(targets[i],failed)||flushdir("/jffs")||flushdir(ACTIVE))return fail("quarantine interrupted state");}
   if(rename(saved,targets[i])||flushdir(ACTIVE)||flushdir("/jffs"))return fail("restore checkpoint");
  }else if(!directory(targets[i])||!exists(failed)){errno=EINVAL;return fail("missing recovery tree; retained evidence");}
 }
 char database[PATH_MAX],failed[PATH_MAX];join(database,ACTIVE,"database");join(failed,ACTIVE,"failed-database");
 if(!directory(database)){errno=EINVAL;return fail("missing logical database snapshot");}
 if(exists(targets[1])){
  if(!directory(targets[1])){errno=EINVAL;return fail("invalid database target");}
  if(exists(failed)){char replay[PATH_MAX];snprintf(replay,sizeof(replay),ACTIVE "/replay-database-%s",boot);if(exists(replay)||rename(targets[1],replay))return fail("retain interrupted replay");}
  else if(rename(targets[1],failed))return fail("retain interrupted database");
 }
 if(mkdir(targets[1],0700)||flushdir(ACTIVE)||flushdir("/jffs/.localmod")||put("state","restoring-database"))return fail("prepare empty recovery database");
 return 0;
}
static int restore_database(void){
 if(!exists(ACTIVE))return 0;char previous[80]="",state[80]="",attempted[80]="";readfield("boot",previous,sizeof(previous));readfield("state",state,sizeof(state));readfield("recovery-boot",attempted,sizeof(attempted));
 if(!strcmp(previous,boot)||strcmp(state,"restoring-database")||strcmp(attempted,boot)){errno=EBUSY;return fail("database replay requires this boot's recovery preparation");}
 if(restore_values())return fail("restore logical database; retained all copies");
 sync();if(put("state","recovered")||put_at(BASE,"notice","rolled-back"))return fail("finish recovery");
 char path[PATH_MAX];if(snprintf(path,sizeof(path),BASE "/recovered-%s",boot)>=(int)sizeof(path)||exists(path)){errno=EEXIST;return fail("recovery history collision");}
 if(rename(ACTIVE,path)||flushdir(BASE))return fail("retain recovery history");
 puts("Interrupted plugin operation rolled back; interrupted center/database retained in private recovery history");return 0;
}
static int watch(pid_t pid){
 if(!same_owner(pid))return 1;char expected[120];strcpy(expected,owner);
 pid_t childpid=fork();if(childpid<0)return 1;if(childpid)return 0;if(setsid()<0)_exit(1);
 childpid=fork();if(childpid<0)_exit(1);if(childpid)_exit(0);
 int null=open("/dev/null",O_RDWR);if(null>=0){dup2(null,0);dup2(null,1);dup2(null,2);if(null>2)close(null);}
 for(;;){char value[120];if(readfield("owner",value,sizeof(value))||strcmp(value,expected)||flag("committed"))_exit(0);
  if(!own_live()){
   put("state","interrupted");
   char log[80]="",path[PATH_MAX];readfield("log",log,sizeof(log));
   if(strcmp(log,"soft_log.txt"))strcpy(log,"soft_install_log.txt");
   snprintf(path,sizeof(path),"/tmp/upload/%s",log);
   int fd=open(path,O_WRONLY|O_APPEND|O_CREAT|O_NOFOLLOW,0600);
   const char msg[]="\n安装进程已中断。请重启路由器，启动时将恢复安装前的检查点；可读取的中断现场会保留供检查。\nXU6J03M6\n";
   if(fd>=0){write(fd,msg,sizeof(msg)-1);close(fd);}child("/usr/bin/dbus","set","softcenter_installing_result=1");child("/usr/bin/dbus","set","softcenter_recovery_required=1");_exit(0);
  }sleep(1);
 }
}
int main(int argc,char **argv){
 signal(SIGPIPE,SIG_IGN);
 if(getuid()!=0){errno=EPERM;return fail("root required");}
 if(textread("/proc/sys/kernel/random/boot_id",boot,sizeof(boot)))return fail("read boot identity");boot[strcspn(boot,"\r\n")]=0;
 if(argc==2&&!strcmp(argv[1],"recover"))return recover();
 if(argc==2&&!strcmp(argv[1],"restore-database"))return restore_database();
 if(argc<3)return 2;char *end;long value=strtol(argv[2],&end,10);if(value<=1||*end||value>INT_MAX)return 2;pid_t pid=(pid_t)value;
 if(argc==4&&!strcmp(argv[1],"begin"))return begin(pid,argv[3]);
 if(argc==3&&!strcmp(argv[1],"watch"))return watch(pid);
 if(argc==3&&!strcmp(argv[1],"abandon")){if(!same_owner(pid))return 1;return put("state","interrupted")?1:0;}
 if(argc==4&&!strcmp(argv[1],"checkpoint"))return checkpoint(pid,argv[3]);
 if(argc==4&&!strcmp(argv[1],"finish"))return finish(pid,atoi(argv[3]));
 return 2;
}
