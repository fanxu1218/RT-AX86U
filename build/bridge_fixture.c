/* Deliberately small model of the vendor's authenticated MIME-handler boundary. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
int auth_result=1,url_do_auth=0;
int main(void){
 if(getenv("LD_PRELOAD")){fputs("adapter leaked into child environment\n",stderr);return 4;}
 int s=socket(AF_INET,SOCK_STREAM,0),yes=1;setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
 struct sockaddr_in addr={.sin_family=AF_INET,.sin_port=htons(34000),.sin_addr.s_addr=htonl(INADDR_LOOPBACK)};
 if(bind(s,(struct sockaddr *)&addr,sizeof(addr)) || listen(s,8))return 1;
 const char *limit=getenv("FIXTURE_COUNT");int count=limit?atoi(limit):8;
 for(int i=0;i<count;i++){
  int fd=accept(s,NULL,NULL);if(fd<0)return 2;FILE *f=fdopen(fd,"r+");
  char line[10000];int valid=0;auth_result=1;url_do_auth=0;
  if(!fgets(line,sizeof(line),f))return 3;
  int uu=strstr(line," /UUAccelerator.asp ")!=NULL || strstr(line," /UUAccelerator.asp?probe=test%20only ")!=NULL;
  while(fgets(line,sizeof(line),f) && strcmp(line,"\r\n") && strcmp(line,"\n"))
   if(strstr(line,"asus_token=valid"))valid=1;
  url_do_auth=1;auth_result=valid?0:1;
  const char *protocol="HTTP/1.0";
  fprintf(f,"%s %d %s\r\n",protocol,200,"OK");
  fputs(uu?"Content-Length: 13\r\n\r\nUU_VENDORBODY":"Content-Length: 10\r\n\r\nVENDORBODY",f);
  fclose(f);
 }
 close(s);return 0;
}
