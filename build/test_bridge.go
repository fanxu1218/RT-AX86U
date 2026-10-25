package main
import (
 "context"
 "fmt"
 "io"
 "net"
 "net/http"
 "os"
 "os/exec"
 "strings"
 "sync/atomic"
 "time"
)
func main(){
 var forwarded atomic.Int32
 listener,err:=net.Listen("tcp4","127.0.0.1:3032");if err!=nil{panic(err)}
 backend:=&http.Server{Handler:http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
  peer,err:=net.ResolveTCPAddr("tcp",r.RemoteAddr)
  if err!=nil || peer.Port>1023 || peer.Port<1{panic("relay did not use a privileged source port")}
  b,_:=io.ReadAll(r.Body)
  if r.Method=="POST" && string(b)!="payload"{panic("body changed")}
  forwarded.Add(1);w.Header().Set("Content-Type","application/json");io.WriteString(w,`{"ok":true}`)
 })}
 go backend.Serve(listener);defer backend.Close()
 ctx,cancel:=context.WithTimeout(context.Background(),25*time.Second);defer cancel()
 cmd:=exec.CommandContext(ctx,"/usr/bin/qemu-arm","-L","/work/build/casefs/official_rootfs","-E","LD_PRELOAD=/work/build/httpd_bridge.so","/work/build/bridge-fixture")
 cmd.Env=append(os.Environ(),"FIXTURE_COUNT=10");cmd.Stdout=os.Stdout;cmd.Stderr=os.Stderr
 if err=cmd.Start();err!=nil{panic(err)};defer cmd.Process.Kill()
 for i:=0;i<60;i++{f,e:=os.Open("/proc/net/tcp");if e==nil{b,_:=io.ReadAll(f);f.Close();if strings.Contains(string(b),":84D0"){break}};time.Sleep(100*time.Millisecond)}
 client:=&http.Client{Timeout:3*time.Second}
 cases:=[]struct{name,method,path,cookie,origin string;status int;body string}{
  {"missing-session","GET","/_api/test","","",401,`{"error":"rejected"}`},
  {"invalid-session","GET","/_api/test","asus_token=wrong","",401,`{"error":"rejected"}`},
  {"authenticated-read","GET","/_api/test","asus_token=valid","",200,`{"ok":true}`},
  {"authenticated-write","POST","/_api/","asus_token=valid","https://router.test",200,`{"ok":true}`},
  {"cross-site-write","POST","/_api/","asus_token=valid","https://evil.test",403,`{"error":"rejected"}`},
  {"missing-origin","POST","/_api/","asus_token=valid","",403,`{"error":"rejected"}`},
  {"encoded-traversal","GET","/_api/a%2f..","asus_token=valid","",400,`{"error":"rejected"}`},
  {"stock-page","GET","/index.asp","asus_token=valid","",200,"VENDORBODY"},
  {"encoded-query","GET","/_api/test?value=a%20b","asus_token=valid","",200,`{"ok":true}`},
  {"upload-query","POST","/_upload?nonce=123","asus_token=valid","https://router.test",200,`{"ok":true}`},
 }
 for _,test:=range cases{
  body:="";if test.method=="POST"{body="payload"}
  req,_:=http.NewRequest(test.method,"http://127.0.0.1:34000"+test.path,strings.NewReader(body));req.Host="router.test"
  if test.cookie!=""{req.Header.Set("Cookie",test.cookie)};if test.origin!=""{req.Header.Set("Origin",test.origin)}
  response,e:=client.Do(req);if e!=nil{panic(test.name+": "+e.Error())}
  b,e:=io.ReadAll(response.Body);response.Body.Close()
  if e!=nil || response.StatusCode!=test.status || string(b)!=test.body{panic(fmt.Sprintf("%s: status=%d body=%q error=%v",test.name,response.StatusCode,b,e))}
  fmt.Println("PASS",test.name)
 }
 if forwarded.Load()!=4{panic(fmt.Sprintf("unexpected forwarded requests: %d",forwarded.Load()))}
 if err=cmd.Wait();err!=nil{panic(err)}
 fmt.Println("PASS only authenticated allowed requests reached the private API")
}
