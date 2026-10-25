package main
import("context";"fmt";"io";"net/http";"os";"os/exec";"strings";"time")
func post(client *http.Client,payload string)(*http.Response,error){
 request,_:=http.NewRequest("POST","http://127.0.0.1:3032/_api/",strings.NewReader(payload));request.Header.Set("Content-Type","application/json");request.Close=true;return client.Do(request)
}
func main(){
 ctx,cancel:=context.WithTimeout(context.Background(),35*time.Second);defer cancel()
 backend:=exec.CommandContext(ctx,"/tmp/process-tools/httpdb","/work/build/casefs/rootfs/rom/etc/koolshare/bin/httpdb","-p","127.0.0.1:3032","-r","127.0.0.1:80");backend.Env=append(os.Environ(),"PATH=/koolshare/bin:/koolshare/scripts:/usr/sbin:/usr/bin:/sbin:/bin");backend.Stdout=os.Stdout;backend.Stderr=os.Stderr
 if e:=backend.Start();e!=nil{panic(e)};defer backend.Process.Kill();time.Sleep(500*time.Millisecond)
 client:=&http.Client{Timeout:5*time.Second}
 payload:=`{"id":12001,"method":"ks_tar_install.sh","params":[],"fields":{"soft_name":"localmod_probe.tar.gz"}}`
 response,e:=post(client,payload);if e!=nil{panic(e)};body,readErr:=io.ReadAll(response.Body);if readErr!=nil{panic(readErr)};response.Body.Close();fmt.Println("INSTALL RPC",response.StatusCode,string(body))
 ready:=false;for i:=0;i<100;i++{b,_:=exec.Command("/usr/bin/dbus","get","softcenter_module_localmod_probe_install").Output();log,_:=os.ReadFile("/tmp/upload/soft_log.txt");if strings.TrimSpace(string(b))=="1" && strings.Contains(string(log),"XU6J03M6"){ready=true;break};time.Sleep(100*time.Millisecond)}
 if !ready{log,_:=os.ReadFile("/tmp/upload/soft_log.txt");panic("offline install failed: "+string(log))}
 if b,e:=os.ReadFile("/koolshare/webs/Module_localmod_probe.asp");e!=nil || !strings.Contains(string(b),"localmod-probe"){panic("plugin page not installed")}
 fmt.Println("PASS actual software-center API invokes offline installer and registers fixture plugin")
 payload=`{"id":12002,"method":"localmod_probe.sh","params":[],"fields":{"localmod_probe_input":"roundtrip"}}`
 response,e=post(client,payload);if e!=nil{panic(e)};body,_=io.ReadAll(response.Body);response.Body.Close()
 if response.StatusCode!=200{panic(string(body))}
 b,_:=exec.Command("/usr/bin/dbus","get","localmod_probe_runtime").Output();if strings.TrimSpace(string(b))!="roundtrip-ok"{panic("installed plugin script did not receive database fields")}
 fmt.Println("PASS installed plugin script reads fields and returns via actual curl callback",string(body))
 for _,test:=range []struct{name,reason string}{{"wrong_platform","not installed"},{"softcenter","core overwrite blocked"}}{
  archive,_:=os.ReadFile("/tmp/package-fixtures/"+test.name+".tar.gz");if len(archive)==0{panic("missing test archive")};os.WriteFile("/tmp/upload/"+test.name+".tar.gz",archive,0600)
  if e:=exec.Command("/usr/bin/dbus","set","soft_name="+test.name+".tar.gz").Run();e!=nil{panic(e)}
  command:=exec.CommandContext(ctx,"/bin/sh","/koolshare/scripts/ks_tar_install.sh","12003")
  out,e:=command.CombinedOutput();if e==nil{panic(test.name+" invalid installation returned success: "+string(out))}
  if test.name=="wrong_platform" && !strings.Contains(string(out),"不是ASUS hnd平台"){panic("wrong platform failed for a different reason: "+string(out))}
  if test.name=="softcenter" && !strings.Contains(string(out),"不接受离线覆盖核心"){panic("core overwrite failed for a different reason: "+string(out))}
  if _,e=os.Stat("/tmp/"+test.name+"-installed");e==nil{panic(test.name+" installation script ran")}
  fmt.Println("PASS",test.name,test.reason,"and failure exit status preserved")
 }
 if _,e:=os.Stat("/tmp/.localmod");e!=nil{panic("offline package cleanup removed the runtime directory")}
 fmt.Println("PASS offline cleanup preserves private runtime directory")
 os.WriteFile("/jffs/localmod-disabled",nil,0600)
 stopped:=false;for i:=0;i<50;i++{
  response,e:=client.Get("http://127.0.0.1:3032/_api/soft");if e!=nil{stopped=true;break};response.Body.Close();time.Sleep(100*time.Millisecond)
 }
 if !stopped{
  for _,file:=range []string{"/tmp/.localmod/events.log","/tmp/.localmod/bootstrap.log","/tmp/.localmod/eventd.pid"}{b,_:=os.ReadFile(file);fmt.Println(file,string(b))}
  out,_:=exec.Command("/bin/sh","-c","ps -o pid,comm,args; pidof httpdb; pidof skipd").CombinedOutput();fmt.Println(string(out))
  panic("recovery marker left the private API running")
 }
 fmt.Println("PASS recovery marker stops the actual private API backend")
 fmt.Println("PASS software-center controlled fixture workflow; no third-party plugin or internet service was executed")
}
