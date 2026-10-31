package main
import("context";"crypto/md5";"encoding/hex";"fmt";"net";"net/http";"os";"os/exec";"strings";"sync/atomic";"syscall";"time")
func main(){
 ctx,cancel:=context.WithTimeout(context.Background(),40*time.Second);defer cancel()
 script:=[]byte("#!/bin/sh\n[ -z \"$LD_PRELOAD\" ] || exit 19\nprintf 'controlled-monitor\\n' >> /tmp/native-uu-executed\n")
 sum:=md5.Sum(script);checksum:=hex.EncodeToString(sum[:]);var scenario atomic.Int32;var apiCalls,downloads atomic.Int32
 listener,e:=net.Listen("tcp4","127.0.0.1:35000");if e!=nil{panic(e)}
 server:=&http.Server{Handler:http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
  switch r.URL.Path{
  case "/api":apiCalls.Add(1);if scenario.Load()==2{w.WriteHeader(503);return};if scenario.Load()==3{fmt.Fprintln(w,"malformed-response");return};hash:=checksum;if scenario.Load()==1{hash=strings.Repeat("0",32)};fmt.Fprintf(w,"http://127.0.0.1:35000/monitor,%s",hash)
  case "/monitor":downloads.Add(1);w.Write(script)
  default:w.WriteHeader(404)
  }
 })};go server.Serve(listener);defer server.Close()
 tests:=[]struct{name,territory,mode string;scenario int32;api,download,execute bool}{{"native_ntp_uu_start_once","CN/01","1",0,true,true,true},{"native_uu_bad_checksum_blocks_execution","CN/01","1",1,true,true,false},{"native_uu_api_failure_blocks_execution","CN/01","1",2,true,false,false},{"native_uu_malformed_response_blocks_execution","CN/01","1",3,true,false,false},{"native_uu_non_china_sku_skipped","US/01","1",0,false,false,false},{"native_uu_ap_mode_skipped","CN/01","3",0,false,false,false}}
 for _,test:=range tests{
  scenario.Store(test.scenario);apiCalls.Store(0);downloads.Store(0)
  for _,p:=range []string{"/tmp/native-ntp-synced","/tmp/native-uu-executed","/var/run/ntp.pid","/tmp/native-ntp-idle"}{os.Remove(p)};os.RemoveAll("/tmp/uu")
  log,e:=os.Create("/work/build/"+test.name+".log");if e!=nil{panic(e)}
  cmd:=exec.CommandContext(ctx,"/usr/bin/qemu-arm","-0","ntp","-L","/work/build/casefs/official_rootfs","-E","LD_PRELOAD=/work/build/rc_bridge.so:/work/build/native_hw_fixture.so:/work/build/native_uu_transport.so","/usr/libexec/localmod/rc.vendor")
  cmd.Env=append(os.Environ(),"NATIVE_UU_CASE=1","NATIVE_UU_TERRITORY="+test.territory,"NATIVE_UU_MODE="+test.mode);cmd.Stdout=log;cmd.Stderr=log
  if e=cmd.Start();e!=nil{panic(e)}
  ready:=false;for i:=0;i<200;i++{if _,e=os.Stat("/var/run/ntp.pid");e==nil{ready=true;break};time.Sleep(50*time.Millisecond)}
  if !ready{b,_:=os.ReadFile("/work/build/"+test.name+".log");panic("native ntp not ready: "+string(b))};time.Sleep(100*time.Millisecond)
  os.Remove("/tmp/native-ntp-idle");os.WriteFile("/tmp/native-ntp-synced",[]byte("1"),0600);cmd.Process.Signal(syscall.SIGTSTP)
  idle:=false;for i:=0;i<100;i++{if _,e=os.Stat("/tmp/native-ntp-idle");e==nil{idle=true;break};time.Sleep(50*time.Millisecond)}
  if !idle{panic("native NTP handler did not finish: "+test.name)}
  _,execution:=os.Stat("/tmp/native-uu-executed");executed:=execution==nil
  if (apiCalls.Load()>0)!=test.api || (downloads.Load()>0)!=test.download || executed!=test.execute{b,_:=os.ReadFile("/work/build/"+test.name+".log");panic(fmt.Sprintf("%s api=%d download=%d executed=%v %s",test.name,apiCalls.Load(),downloads.Load(),executed,b))}
  before:=apiCalls.Load();os.Remove("/tmp/native-ntp-idle");cmd.Process.Signal(syscall.SIGTSTP)
  idle=false;for i:=0;i<100;i++{if _,e=os.Stat("/tmp/native-ntp-idle");e==nil{idle=true;break};time.Sleep(50*time.Millisecond)}
  if !idle{panic("repeated native NTP handler did not finish")}
  if apiCalls.Load()!=before{panic("repeated NTP sync restarted UU")}
  cmd.Process.Signal(syscall.SIGTERM);cmd.Wait();log.Close()
  fmt.Println("PASS",test.name)
 }
 fmt.Println("PASS original rc ntp SIGTSTP -> exec_uu -> controlled download/checksum/launch; no real UU monitor/account or external network")
}
