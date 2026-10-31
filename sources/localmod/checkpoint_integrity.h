/* SPDX-License-Identifier: MIT
 * Sealed checkpoint inventory. Included only by plugin_txn.c.
 * All names/types/ownership/modes and regular/symlink bytes enter the digest.
 */
typedef struct { uint32_t h[8]; uint64_t length; unsigned used; unsigned char block[64]; } lm_sha;
static uint32_t rr(uint32_t a,unsigned n){return (a>>n)|(a<<(32-n));}
static void sha_block(lm_sha *s,const unsigned char *b){
 static const uint32_t k[64]={
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
 uint32_t w[64];for(int i=0;i<16;i++)w[i]=((uint32_t)b[4*i]<<24)|((uint32_t)b[4*i+1]<<16)|((uint32_t)b[4*i+2]<<8)|b[4*i+3];
 for(int i=16;i<64;i++)w[i]=w[i-16]+(rr(w[i-15],7)^rr(w[i-15],18)^(w[i-15]>>3))+w[i-7]+(rr(w[i-2],17)^rr(w[i-2],19)^(w[i-2]>>10));
 uint32_t a=s->h[0],c=s->h[2],b0=s->h[1],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];
 for(int i=0;i<64;i++){uint32_t t=h+(rr(e,6)^rr(e,11)^rr(e,25))+((e&f)^(~e&g))+k[i]+w[i];uint32_t u=(rr(a,2)^rr(a,13)^rr(a,22))+((a&b0)^(a&c)^(b0&c));h=g;g=f;f=e;e=d+t;d=c;c=b0;b0=a;a=t+u;}
 s->h[0]+=a;s->h[1]+=b0;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void sha_init(lm_sha *s){memset(s,0,sizeof(*s));uint32_t h[]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};memcpy(s->h,h,sizeof(h));}
static void sha_add(lm_sha *s,const void *data,size_t n){const unsigned char *p=data;s->length+=n;while(n){size_t take=64-s->used;if(take>n)take=n;memcpy(s->block+s->used,p,take);s->used+=take;p+=take;n-=take;if(s->used==64){sha_block(s,s->block);s->used=0;}}}
static void sha_end(lm_sha *s,unsigned char out[32]){uint64_t bits=s->length*8;unsigned char b=0x80;sha_add(s,&b,1);b=0;while(s->used!=56)sha_add(s,&b,1);unsigned char tail[8];for(int i=0;i<8;i++)tail[7-i]=(unsigned char)(bits>>(i*8));sha_add(s,tail,8);for(int i=0;i<8;i++)for(int j=0;j<4;j++)out[i*4+j]=(unsigned char)(s->h[i]>>(24-j*8));}
static void hex_digest(const unsigned char digest[32],char out[65]){static const char h[]="0123456789abcdef";for(int i=0;i<32;i++){out[i*2]=h[digest[i]>>4];out[i*2+1]=h[digest[i]&15];}out[64]=0;}
static int hash_file(const char *p,unsigned char digest[32],uint64_t cap){
 int fd=open(p,O_RDONLY|O_NOFOLLOW);if(fd<0)return -1;struct stat a,b;int r=-1;lm_sha h;sha_init(&h);
 if(fstat(fd,&a)||!S_ISREG(a.st_mode)||(uint64_t)a.st_size>cap){errno=EINVAL;goto done;}
 unsigned char block[32768];ssize_t n;while((n=read(fd,block,sizeof(block)))>0)sha_add(&h,block,(size_t)n);
 if(n<0||fstat(fd,&b)||a.st_size!=b.st_size||a.st_ino!=b.st_ino||a.st_mtim.tv_sec!=b.st_mtim.tv_sec||a.st_mtim.tv_nsec!=b.st_mtim.tv_nsec){errno=EBUSY;goto done;}
 sha_end(&h,digest);r=0;
done:close(fd);return r;
}
typedef struct { lm_sha hash; int fd; unsigned count; dev_t device; } lm_inventory;
static int exact_field(const char *name,char *value,size_t cap){char p[PATH_MAX];struct stat st;if(join(p,ACTIVE,name)||lstat(p,&st)||!S_ISREG(st.st_mode)||st.st_size<1||(uint64_t)st.st_size>=cap||readfield(name,value,cap)||st.st_size!=(off_t)strlen(value)){errno=EINVAL;return -1;}return 0;}
static int uuid_valid(const char *s){if(strlen(s)!=36)return 0;for(int i=0;i<36;i++){if(i==8||i==13||i==18||i==23){if(s[i]!='-')return 0;}else if(!strchr("0123456789abcdef",s[i]))return 0;}return 1;}
static int intent_valid(void){
 char value[128];if(exact_field("version",value,sizeof(value))||strcmp(value,"2")){errno=EINVAL;return -1;}
 if(exact_field("boot",value,sizeof(value))||!uuid_valid(value)){errno=EINVAL;return -1;}
 if(exact_field("owner",value,sizeof(value)))return -1;char *colon=strchr(value,':');if(!colon||colon==value||!colon[1]){errno=EINVAL;return -1;}
 for(char *p=value;*p;p++)if(p!=colon&&(*p<'0'||*p>'9')){errno=EINVAL;return -1;}
 if(exact_field("log",value,sizeof(value))||(strcmp(value,"soft_install_log.txt")&&strcmp(value,"soft_log.txt"))){errno=EINVAL;return -1;}
 if(flag("module")&&(exact_field("module",value,sizeof(value))||!safe_name(value))){errno=EINVAL;return -1;}
 if(flag("recovery-boot")&&(exact_field("recovery-boot",value,sizeof(value))||!uuid_valid(value))){errno=EINVAL;return -1;}
 return 0;
}
static int inventory_bytes(lm_inventory *m,const void *data,size_t n){sha_add(&m->hash,data,n);return m->fd<0?0:transfer(m->fd,(void *)data,n,1);}
static int inventory_number(lm_inventory *m,uint64_t n,unsigned size){unsigned char b[8];for(unsigned i=0;i<size;i++)b[i]=(unsigned char)(n>>(i*8));return inventory_bytes(m,b,size);}
static int inventory_tree(lm_inventory *m,const char *p,const char *label,int depth){
 if(depth>64||++m->count>100000){errno=EFBIG;return -1;}
 struct stat st;if(lstat(p,&st)||st.st_dev!=m->device)return -1;
 unsigned type=S_ISREG(st.st_mode)?1:S_ISDIR(st.st_mode)?2:S_ISLNK(st.st_mode)?3:0;
 if(!type){errno=EINVAL;return -1;}
 uint64_t size=0;unsigned char digest[32]={0};
 if(type==1){size=(uint64_t)st.st_size;if(hash_file(p,digest,512*1024*1024ULL))return -1;}
 if(type==3){char link[PATH_MAX];ssize_t n=readlink(p,link,sizeof(link));if(n<0||n>=(ssize_t)sizeof(link))return -1;size=(uint64_t)n;lm_sha h;sha_init(&h);sha_add(&h,link,(size_t)n);sha_end(&h,digest);}
 size_t name=strlen(label);if(name>=PATH_MAX||inventory_number(m,name,4)||inventory_bytes(m,label,name)||inventory_number(m,type,4)||inventory_number(m,st.st_mode&07777,4)||inventory_number(m,st.st_uid,4)||inventory_number(m,st.st_gid,4)||inventory_number(m,size,8)||inventory_bytes(m,digest,sizeof(digest)))return -1;
 if(type!=2)return 0;
 struct dirent **list=NULL;int count=scandir(p,&list,NULL,alphasort);if(count<0)return -1;int r=0;
 for(int i=0;i<count;i++){
  const char *name0=list[i]->d_name;char path[PATH_MAX],next[PATH_MAX];
  if(strcmp(name0,".")&&strcmp(name0,"..")&&!r){
   if(join(path,p,name0)||join(next,label,name0))r=-1;
   else if(strcmp(next,"center/perp/.control"))r=inventory_tree(m,path,next,depth+1);
  }free(list[i]);
 }free(list);return r;
}
static int inventory(int fd,unsigned char digest[32]){
 lm_inventory m={.fd=fd};sha_init(&m.hash);struct stat st;if(lstat(ACTIVE,&st)||!S_ISDIR(st.st_mode))return -1;m.device=st.st_dev;
 const char header[]="LM-CHECKPOINT-2\n";if(inventory_bytes(&m,header,sizeof(header)-1))return -1;
 const char *meta[]={"version","boot","owner","log","module"};
 for(unsigned i=0;i<sizeof(meta)/sizeof(meta[0]);i++){char p[PATH_MAX];if(join(p,ACTIVE,meta[i])||inventory_tree(&m,p,meta[i],0))return -1;}
 const char *center=ACTIVE "/center";
 if(!exists(center)){
  if(!directory(ACTIVE "/failed-center")||!directory("/jffs/.koolshare")){errno=EINVAL;return -1;}
  center="/jffs/.koolshare";
 }
 if(!directory(center)||!directory(ACTIVE "/database")||inventory_tree(&m,center,"center",0)||inventory_tree(&m,ACTIVE "/database","database",0))return -1;
 sha_end(&m.hash,digest);return 0;
}
static int marker(const char *name,const char *prefix,const unsigned char digest[32]){
 char hex[65],expected[100],actual[128],p[PATH_MAX];hex_digest(digest,hex);snprintf(expected,sizeof(expected),"%s%s\n",prefix,hex);struct stat st;
 if(join(p,ACTIVE,name)||lstat(p,&st)||!S_ISREG(st.st_mode)||st.st_size!=(off_t)strlen(expected)||textread(p,actual,sizeof(actual))||strcmp(actual,expected)){errno=EINVAL;return -1;}return 0;
}
static int seal_checkpoint(void){
 const char *tmp=ACTIVE "/manifest.bin.new";int fd=open(tmp,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);if(fd<0)return -1;
 unsigned char digest[32];int r=inventory(fd,digest);if(!r)r=fsync(fd);if(close(fd))r=-1;if(r)return -1;
 if(rename(tmp,ACTIVE "/manifest.bin")||flushdir(ACTIVE))return -1;
 char hex[65],ready[100];hex_digest(digest,hex);snprintf(ready,sizeof(ready),"LMREADY2 %s\n",hex);return put("ready",ready);
}
static int verify_checkpoint(unsigned char digest[32]){
 if(intent_valid())return -1;
 unsigned char file[32];if(hash_file(ACTIVE "/manifest.bin",file,8*1024*1024)||marker("ready","LMREADY2 ",file)||inventory(-1,digest)||memcmp(file,digest,32)){errno=EINVAL;return -1;}return 0;
}
typedef struct {char *key;uint32_t size;} lm_key;
static int values_validate(uint64_t *bytes,unsigned *count){
 int fd=open(ACTIVE "/database/values.bin",O_RDONLY|O_NOFOLLOW);if(fd<0)return -1;struct stat st;int r=-1;lm_key *keys=NULL;size_t used=0,cap=0;char header[6];*bytes=0;*count=0;
 if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<14||st.st_size>32*1024*1024||transfer(fd,header,6,0)||memcmp(header,"LMDB1\0",6)){errno=EINVAL;goto done;}
 for(;;){uint32_t sizes[2];if(transfer(fd,sizes,sizeof(sizes),0))goto done;if(!sizes[0]&&!sizes[1]){char end;if(read(fd,&end,1)!=0){errno=EINVAL;goto done;}r=0;break;}
  *bytes+=sizes[0]+(uint64_t)sizes[1]+8;
  if(!sizes[0]||sizes[0]>2048||sizes[1]>7900000||*bytes>32*1024*1024||used>=10000){errno=EINVAL;goto done;}
  char *key=malloc(sizes[0]);if(!key)goto done;if(transfer(fd,key,sizes[0],0)){free(key);goto done;}
  for(uint32_t i=0;i<sizes[0];i++)if((unsigned char)key[i]<=32){free(key);errno=EINVAL;goto done;}
  for(size_t i=0;i<used;i++)if(keys[i].size==sizes[0]&&!memcmp(keys[i].key,key,sizes[0])){free(key);errno=EINVAL;goto done;}
  if(used==cap){size_t next=cap?cap*2:128;lm_key *newkeys=realloc(keys,next*sizeof(*keys));if(!newkeys){free(key);goto done;}keys=newkeys;cap=next;}
  keys[used++]=(lm_key){key,sizes[0]};
  char block[32768];uint32_t left=sizes[1];while(left){size_t take=left>sizeof(block)?sizeof(block):left;if(transfer(fd,block,take,0))goto done;if(memchr(block,0,take)){errno=EINVAL;goto done;}left-=(uint32_t)take;}
 }
 *count=(unsigned)used;
done:for(size_t i=0;i<used;i++)free(keys[i].key);free(keys);close(fd);return r;
}
static int recovery_space(uint64_t bytes){
 struct statvfs fs;if(statvfs("/jffs",&fs))return -1;
 /* Reserve native DB pages/commit overhead and metadata without deleting history. */
 uint64_t need=2*1024*1024+3*bytes;if((uint64_t)fs.f_bavail*fs.f_frsize<need){errno=ENOSPC;return -1;}return 0;
}
typedef struct {char *key,*value;uint32_t key_size,value_size;int seen;} lm_record;
static int record_order(const void *a,const void *b){return strcmp(((const lm_record *)a)->key,((const lm_record *)b)->key);}
static int verify_values(void){
 uint64_t bytes;unsigned count;if(values_validate(&bytes,&count))return -1;
 int in=open(ACTIVE "/database/values.bin",O_RDONLY|O_NOFOLLOW),fd=-1,r=-1;lm_record *records=calloc(count?count:1,sizeof(*records));unsigned loaded=0;if(in<0||!records)goto done;
 char header[6];if(transfer(in,header,6,0))goto done;
 for(unsigned i=0;i<count;i++){
  uint32_t size[2];if(transfer(in,size,sizeof(size),0))goto done;
  char *data=malloc(size[0]+1+size[1]);if(!data)goto done;records[i]=(lm_record){data,data+size[0]+1,size[0],size[1],0};loaded++;
  if(transfer(in,data,size[0],0)||transfer(in,data+size[0]+1,size[1],0))goto done;data[size[0]]=0;
 }
 qsort(records,count,sizeof(*records),record_order);fd=db_connect();if(fd<0)goto done;
 const char all[]="list __all__\n";if(db_send(fd,all,sizeof(all)-1))goto done;unsigned got=0;
 for(;;){
  size_t n;char *reply=db_receive(fd,&n);if(!reply)goto done;
  int end=n==sizeof("list __all__ __end__\n")-1&&!memcmp(reply,"list __all__ __end__\n",n);if(end){free(reply);break;}
  if(n<6||memcmp(reply,"list ",5)){free(reply);errno=EPROTO;goto done;}
  char *split=memchr(reply+5,' ',n-5);if(!split){free(reply);errno=EPROTO;goto done;}size_t key=(size_t)(split-reply-5),value=n-(size_t)(split-reply)-1;
  *split=0;lm_record needle={.key=reply+5};lm_record *found=bsearch(&needle,records,count,sizeof(*records),record_order);
  int ok=found&&!found->seen&&key==found->key_size&&value==found->value_size&&!memcmp(split+1,found->value,value);if(ok)found->seen=1;free(reply);
  if(!ok||++got>count){errno=EIO;goto done;}
 }
 if(got!=count){errno=EIO;goto done;}r=0;
done:if(records){for(unsigned i=0;i<loaded;i++)free(records[i].key);free(records);}if(in>=0)close(in);if(fd>=0)close(fd);return r;
}
