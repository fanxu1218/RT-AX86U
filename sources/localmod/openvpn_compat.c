/* SPDX-License-Identifier: MIT
 * Keep the factory UI's explicit legacy modes working without changing user
 * keys or configuration. Modern profiles continue to use the selected Merlin
 * application. This is deliberately not a replacement OpenVPN config parser.
 */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <ctype.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static const char *legacy(const char *word,size_t length) {
 static const char *options[]={"ncp-disable","secret",NULL};
 for(unsigned i=0;options[i];i++)
  if(strlen(options[i])==length && !memcmp(word,options[i],length))return options[i];
 return NULL;
}
static int factory_configuration(int fd) {
 struct stat actual;if(fstat(fd,&actual) || !S_ISREG(actual.st_mode) || actual.st_size<0 || actual.st_size>1024*1024)return 0;
 const char *kinds[]={"client","server"};
 for(unsigned kind=0;kind<2;kind++)for(int unit=1;unit<=(kind?2:5);unit++){
  char path[128];struct stat expected;
  snprintf(path,sizeof(path),"/etc/openvpn/%s%d/config.ovpn",kinds[kind],unit);
  if(!stat(path,&expected) && expected.st_dev==actual.st_dev && expected.st_ino==actual.st_ino)return 1;
 }
 return 0;
}
static const char *scan(int fd) {
 if(!factory_configuration(fd)){close(fd);return NULL;}
 FILE *file=fdopen(fd,"r");if(!file){close(fd);return NULL;}
 char line[2048];size_t consumed=0;int inline_block=0;const char *reason=NULL;
 while(fgets(line,sizeof(line),file)){
  consumed+=strlen(line);if(consumed>1024*1024)break;
  /* Read only the directive token. Inline credentials/certificates are not
   * interpreted or logged, and long values are drained without allocation. */
  if(!strchr(line,'\n')){int c;while((c=fgetc(file))!=EOF && c!='\n'){if(++consumed>1024*1024)break;}}
  if(consumed>1024*1024)break;
  char *p=line;while(isspace((unsigned char)*p))p++;
  if(*p=='<'){inline_block=p[1]!='/'?1:0;continue;}
  if(inline_block || !*p || *p=='#' || *p==';')continue;
  if(p[0]=='-' && p[1]=='-')p+=2;
  size_t length=0;while(p[length] && !isspace((unsigned char)p[length]) && p[length]!='#' && p[length]!=';')length++;
  reason=legacy(p,length);if(reason)break;
 }
 fclose(file);return reason;
}
const char *lm_openvpn_legacy(int argc,char *const argv[]) {
 int cwd=open(".",O_RDONLY|O_DIRECTORY|O_CLOEXEC);if(cwd<0)return NULL;
 const char *reason=NULL;
 for(int i=1;i<argc;i++){
  if(!strncmp(argv[i],"--",2))reason=legacy(argv[i]+2,strlen(argv[i]+2));
  if(reason)break;
  if(!strcmp(argv[i],"--cd") && i+1<argc){
   int next=openat(cwd,argv[++i],O_RDONLY|O_DIRECTORY|O_CLOEXEC);
   if(next<0)break;close(cwd);cwd=next;
  }else if(!strcmp(argv[i],"--config") && i+1<argc){
   int fd=openat(cwd,argv[++i],O_RDONLY|O_NONBLOCK|O_CLOEXEC);
   if(fd>=0)reason=scan(fd);
   if(reason)break;
  }
 }
 close(cwd);return reason;
}
