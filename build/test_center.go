package main
import("bytes";"context";"fmt";"io";"net/http";"mime/multipart";"os";"os/exec";"strings";"time")
func post(client *http.Client,payload string)(*http.Response,error){
 request,_:=http.NewRequest("POST","http://127.0.0.1:34000/_api/",strings.NewReader(payload));request.Header.Set("Content-Type","application/json");request.Host="router.test";request.Header.Set("Cookie","asus_token=valid");request.Header.Set("Origin","http://router.test");request.Close=true;return client.Do(request)
}
func main(){
 ctx,cancel:=context.WithTimeout(context.Background(),35*time.Second);defer cancel()
 backend:=exec.CommandContext(ctx,"/tmp/process-tools/httpdb","/work/build/casefs/rootfs/rom/etc/koolshare/bin/httpdb","-p","127.0.0.1:3032","-r","127.0.0.1:80");backend.Env=append(os.Environ(),"PATH=/koolshare/bin:/koolshare/scripts:/usr/sbin:/usr/bin:/sbin:/bin");backend.Stdout=os.Stdout;backend.Stderr=os.Stderr
 if e:=backend.Start();e!=nil{panic(e)};defer backend.Process.Kill();time.Sleep(500*time.Millisecond)
 fixture:=exec.CommandContext(ctx,"/usr/bin/qemu-arm","-L","/work/build/casefs/official_rootfs","-E","LD_PRELOAD=/work/build/httpd_bridge.so","/work/build/bridge-fixture")
 fixture.Env=append(os.Environ(),"FIXTURE_COUNT=4");fixture.Stdout=os.Stdout;fixture.Stderr=os.Stderr
 if e:=fixture.Start();e!=nil{panic(e)};defer fixture.Process.Kill();time.Sleep(300*time.Millisecond)
 client:=&http.Client{Timeout:5*time.Second}
 archive,e:=os.ReadFile("/tmp/package-fixtures/localmod_probe.tar.gz");if e!=nil{panic(e)}
 var upload bytes.Buffer;writer:=multipart.NewWriter(&upload);part,e:=writer.CreateFormFile("localmod_probe.tar.gz","localmod_probe.tar.gz");if e!=nil{panic(e)}
 part.Write(archive);writer.Close()
 request,_:=http.NewRequest("POST","http://127.0.0.1:34000/_upload?nonce=12000",&upload)
 request.Host="router.test";request.Header.Set("Cookie","asus_token=valid");request.Header.Set("Origin","http://router.test");request.Header.Set("Content-Type",writer.FormDataContentType());request.Close=true
 response,e:=client.Do(request);if e!=nil{panic(e)};body,e:=io.ReadAll(response.Body);response.Body.Close();if e!=nil || response.StatusCode!=200{panic(fmt.Sprintf("upload: %d %s %v",response.StatusCode,body,e))}
 stored,e:=os.ReadFile("/tmp/upload/localmod_probe.tar.gz");if e!=nil || !bytes.Equal(stored,archive){panic(fmt.Sprintf("real upload did not preserve archive: %s %v",body,e))}
 fmt.Println("PASS multipart archive uploaded byte-for-byte through authenticated adapter and actual httpdb")
 payload:=`{"id":12001,"method":"ks_tar_install.sh","params":[],"fields":{"soft_name":"localmod_probe.tar.gz"}}`
 response,e=post(client,payload);if e!=nil{panic(e)};body,readErr:=io.ReadAll(response.Body);if readErr!=nil{panic(readErr)};response.Body.Close();fmt.Println("INSTALL RPC",response.StatusCode,string(body))
 ready:=false;for i:=0;i<100;i++{b,_:=exec.Command("/usr/bin/dbus","get","softcenter_module_localmod_probe_install").Output();log,_:=os.ReadFile("/tmp/upload/soft_log.txt");if strings.TrimSpace(string(b))=="1" && strings.Contains(string(log),"XU6J03M6"){ready=true;break};time.Sleep(100*time.Millisecond)}
 if !ready{log,_:=os.ReadFile("/tmp/upload/soft_log.txt");panic("offline install failed: "+string(log))}
 if b,e:=os.ReadFile("/koolshare/webs/Module_localmod_probe.asp");e!=nil || !strings.Contains(string(b),"localmod-probe"){panic("plugin page not installed")}
 if _,e:=os.Stat("/koolshare/scripts/localmod_probe_uninstall.sh");e!=nil{panic("custom uninstall fixture not installed")}
 fmt.Println("PASS actual software-center API invokes offline installer and registers fixture plugin")
 payload=`{"id":12002,"method":"localmod_probe.sh","params":[],"fields":{"localmod_probe_input":"roundtrip"}}`
 response,e=post(client,payload);if e!=nil{panic(e)};body,_=io.ReadAll(response.Body);response.Body.Close()
 if response.StatusCode!=200{panic(string(body))}
 b,_:=exec.Command("/usr/bin/dbus","get","localmod_probe_runtime").Output();if strings.TrimSpace(string(b))!="roundtrip-ok"{panic("installed plugin script did not receive database fields")}
 fmt.Println("PASS installed plugin script reads fields and returns via actual curl callback",string(body))
 fmt.Println("PASS upload, install RPC and script callback traverse the authenticated adapter")
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
 payload=`{"id":12004,"method":"ks_app_remove.sh","params":["ks_app_remove"],"fields":{"softcenter_installing_todo":"localmod_probe","softcenter_installing_title":"localmod probe"}}`
 response,e=post(client,payload);if e!=nil{panic(e)};body,_=io.ReadAll(response.Body);response.Body.Close();if response.StatusCode!=200{panic(string(body))}
 uninstalled:=false;for i:=0;i<50;i++{
  if _,err:=os.Stat("/tmp/localmod-custom-uninstall-ran");err==nil{
   value,_:=exec.Command("/usr/bin/dbus","get","softcenter_module_localmod_probe_install").Output()
   if strings.TrimSpace(string(value))==""{uninstalled=true;break}
  };time.Sleep(100*time.Millisecond)
 }
 if !uninstalled{log,_:=os.ReadFile("/tmp/upload/soft_install_log.txt");panic("custom uninstall hook was not executed/cleaned: "+string(log))}
 if _,e:=os.Stat("/koolshare/webs/Module_localmod_probe.asp");!os.IsNotExist(e){panic("uninstall retained module page")}
 fmt.Println("PASS actual uninstall RPC executes module_uninstall hook and removes registration and page")
 if e=fixture.Wait();e!=nil{panic(e)}
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
