package main

import (
 "context"
 "fmt"
 "io"
 "net/http"
 "os"
 "os/exec"
 "strings"
 "time"
)

func main(){
 ctx,cancel:=context.WithTimeout(context.Background(),24*time.Second);defer cancel()
 start:=func(args ...string)*exec.Cmd{cmd:=exec.CommandContext(ctx,"/usr/bin/qemu-arm",args...);cmd.Stdout=os.Stdout;cmd.Stderr=os.Stderr;if e:=cmd.Start();e!=nil{panic(e)};return cmd}
 os.MkdirAll("/tmp/.localmod-testdb",0700)
 skipd:=start("/work/build/casefs/rootfs/usr/bin/skipd","-d","/tmp/.localmod-testdb");defer skipd.Process.Kill()
 time.Sleep(600*time.Millisecond)
 out,e:=exec.CommandContext(ctx,"/usr/bin/qemu-arm","/work/build/casefs/rootfs/usr/bin/dbus","set","localmod_probe=roundtrip-pass").CombinedOutput()
 if e!=nil{panic(fmt.Sprintf("dbus: %s %v",out,e))}
 packed,e:=os.ReadFile("/work/build/casefs/rootfs/rom/etc/koolshare/bin/httpdb");if e!=nil{panic(e)}
 if e=os.WriteFile("/tmp/httpdb",packed,0700);e!=nil{panic(e)}
 backend:=start("/tmp/httpdb","-p","127.0.0.1:3032","-r","127.0.0.1:80");defer backend.Process.Kill()
 time.Sleep(500*time.Millisecond)
 fixture:=exec.CommandContext(ctx,"/usr/bin/qemu-arm","-L","/work/build/casefs/official_rootfs","-E","LD_PRELOAD=/work/build/httpd_bridge.so","/work/build/bridge-fixture")
 fixture.Env=append(os.Environ(),"FIXTURE_COUNT=4");fixture.Stdout=os.Stdout;fixture.Stderr=os.Stderr
 if e=fixture.Start();e!=nil{panic(e)};defer fixture.Process.Kill()
 time.Sleep(500*time.Millisecond)
 client:=&http.Client{Timeout:4*time.Second}
 cases:=[]struct{name,path,cookie string;status int;contains string}{
  {"real-backend-unauthenticated","/_api/localmod_","",401,"rejected"},
  {"real-skipd-value-through-adapter","/_api/localmod_","asus_token=valid",200,"roundtrip-pass"},
  {"real-backend-invalid-session","/_api/localmod_","asus_token=wrong",401,"rejected"},
  {"vendor-page-with-real-backend","/index.asp","asus_token=valid",200,"VENDORBODY"},
 }
 for _,test:=range cases{
  req,_:=http.NewRequest("GET","http://127.0.0.1:34000"+test.path,nil);req.Host="router.test"
  if test.cookie!=""{req.Header.Set("Cookie",test.cookie)}
  resp,err:=client.Do(req);if err!=nil{panic(test.name+": "+err.Error())}
  b,err:=io.ReadAll(resp.Body);resp.Body.Close()
  if err!=nil || resp.StatusCode!=test.status || !strings.Contains(string(b),test.contains){panic(fmt.Sprintf("%s: %d %q %v",test.name,resp.StatusCode,b,err))}
  fmt.Println("PASS",test.name)
 }
 if e=fixture.Wait();e!=nil{panic(e)}
 fmt.Println("PASS actual packaged httpdb and skipd/dbus; vendor authentication remains a fixture")
}
