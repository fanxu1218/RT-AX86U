package main
import("fmt";"net";"os";"os/exec";"strings";"sync/atomic";"time";"path/filepath")
const filter="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\n-A INPUT -i lo -j ACCEPT\nCOMMIT\n"
func restore(text string,args ...string)(string,error){
 command:=[]string{"-0","iptables-restore","-L","/work/build/casefs/official_rootfs","/work/build/restore-fixture"};command=append(command,args...)
 cmd:=exec.Command("/usr/bin/qemu-arm",command...);cmd.Stdin=strings.NewReader(text);out,e:=cmd.CombinedOutput();return string(out),e
}
func rules()string{out,e:=exec.Command("iptables-legacy-save","-t","filter").CombinedOutput();if e!=nil{panic(string(out))};return string(out)}
func guarded(){s:=rules();first:="";for _,line:=range strings.Split(s,"\n"){if strings.HasPrefix(line,"-A INPUT "){first=line;break}};if !strings.Contains(first,"-j LOCALMOD_API"){panic("guard is not first: "+s)}}
func queued()int{f,_:=filepath.Glob("/tmp/.localmod/queue/*.evt");return len(f)}
func main(){
 listener,e:=net.Listen("tcp4","127.0.0.1:3032");if e!=nil{panic(e)};defer listener.Close()
 go func(){for {c,e:=listener.Accept();if e!=nil{return};c.Close()}}()
 if out,e:=restore(filter);e!=nil{panic(out)};guarded()
 dial:=net.Dialer{Timeout:time.Second,LocalAddr:&net.TCPAddr{IP:net.ParseIP("127.0.0.1"),Port:700}}
 conn,e:=dial.Dial("tcp4","127.0.0.1:3032");if e!=nil{panic("privileged client rejected: "+e.Error())};conn.Close()
 fmt.Println("PASS privileged source port reaches private API")
 var open,attempts atomic.Int32;done:=make(chan struct{});finished:=make(chan struct{})
 go func(){defer close(finished);for {select{case <-done:return;default:};c,e:=net.DialTimeout("tcp4","127.0.0.1:3032",20*time.Millisecond);attempts.Add(1);if e==nil{open.Add(1);c.Close()}}}()
 for i:=0;i<24;i++{if out,e:=restore(filter);e!=nil{panic(out)}}
 for i:=0;i<4;i++{if out,e:=restore("","--localmod-flush-filter");e!=nil{panic(out)}}
 close(done);<-finished
 if open.Load()!=0 || attempts.Load()==0{panic(fmt.Sprintf("API exposed during restore: open=%d attempts=%d",open.Load(),attempts.Load()))}
 guarded();fmt.Println("PASS 24 live table replacements reject all unprivileged probes; attempts",attempts.Load())
 if out,e:=restore("*filter\n:CUSTOM - [0:0]\n-A CUSTOM -j RETURN\nCOMMIT\n","--noflush");e!=nil{panic(out)};guarded();fmt.Println("PASS noflush rules keep private API guard first")
 beforeFlush:=queued();if out,e:=restore("","--localmod-flush-filter");e!=nil{panic(out)};guarded()
 snapshot:=rules();if !strings.Contains(snapshot,":CUSTOM - ") || strings.Contains(snapshot,"-A CUSTOM ") || queued()!=beforeFlush{panic("non-routing flush changed chain definitions or emitted a premature event")}
 fmt.Println("PASS non-routing flush preserves custom chains and private API isolation")
 before:=queued();if out,e:=restore(filter,"--test");e!=nil{panic(out)};if queued()!=before{panic("test-only restore emitted a hook")};fmt.Println("PASS test-only restore does not emit events")
 if _,e:=restore("*filter\n:INPUT ACCEPT [0:0]\n");e==nil{panic("truncated filter accepted")};guarded()
 if _,e:=restore("*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\n-A INPUT -j MISSING_LOCALMOD_TEST\nCOMMIT\n");e==nil{panic("vendor restore failure hidden")};guarded()
 if queued()!=before{panic("failed restore emitted events")};fmt.Println("PASS malformed input and vendor failures preserve guard and emit no hooks")
 nat:="*nat\n:PREROUTING ACCEPT [0:0]\n:INPUT ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\n:POSTROUTING ACCEPT [0:0]\nCOMMIT\n"
 if out,e:=restore(nat);e!=nil{panic(out)};guarded();fmt.Println("PASS NAT restore preserves filter isolation and emits a NAT event")
 input:="/tmp/.localmod/original.rules";os.WriteFile(input,[]byte(filter),0600)
 if out,e:=restore("",input);e!=nil{panic(out)};b,_:=os.ReadFile(input);if string(b)!=filter{panic("vendor input file modified")};fmt.Println("PASS filename input and original rules retained")
 os.WriteFile("/jffs/localmod-disabled",nil,0600);before=queued();if out,e:=restore(filter);e!=nil{panic(out)};if queued()!=before{panic("disabled adapter emitted an event")};os.Remove("/jffs/localmod-disabled")
 if out,e:=restore(filter);e!=nil{panic(out)};guarded();fmt.Println("PASS recovery marker delegates original behavior")
}
