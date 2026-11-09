package main
import("context";"encoding/json";"fmt";"os";"os/exec";"strconv";"strings";"time")
func main(){
 ctx,cancel:=context.WithTimeout(context.Background(),180*time.Second);defer cancel()
 s:=nrStart(ctx,"native-vpn-generation",true);defer s.stop();s.login();coBackendReady()
 u:=previewUUStart(ctx);defer u.close()
 for _,kind:=range []string{"client","server"}{
  max:=5;if kind=="server"{max=2}
  for unit:=1;unit<=max;unit++{
   n:=kind+strconv.Itoa(unit);body:="#!/bin/sh\nprintf '\\n# owned-native-postconf-"+n+"\\n' >> \"$1\"\n"
   nrMust(os.WriteFile("/jffs/scripts/openvpn"+n+".postconf",[]byte(body),0755))
  }
 }
 args:=[]string{"-L","/","-E","LD_PRELOAD=/usr/lib/localmod/native_boot_bridge.so:/work/build/native_hw_fixture.so:/work/build/merlin38813-native-vpn-generation/vpn_notify_fixture.so","/work/build/merlin38813-native-vpn-generation/hook-probe"}
 b,e:=exec.CommandContext(ctx,"/usr/bin/qemu-arm",args...).CombinedOutput()
 if e!=nil || !strings.Contains(string(b),"NATIVE_VPN_WRITERS_RETURNED"){panic(fmt.Sprintf("native VPN generation: %v %s",e,b))}
 checks:=[]string{};expected:=[]string{}
 for _,kind:=range []string{"client","server"}{
  max:=5;port:=35320;if kind=="server"{max=2;port=35420}
  for unit:=1;unit<=max;unit++{
   n:=kind+strconv.Itoa(unit);config:=string(nrRead("/etc/openvpn/"+n+"/config.ovpn"));iface:="tun";base:=10;if kind=="server"{base=20};if unit%2==0{iface="tap"}
   for _,token:=range []string{iface+strconv.Itoa(base+unit),"proto udp",strconv.Itoa(port+unit),"AES-256-GCM","LOCALMOD_OWNED_"+n,"# owned-native-postconf-"+n}{if !strings.Contains(config,token){panic("native config "+n+" missing "+token+": "+config)}}
   if strings.Count(config,"# owned-native-postconf-"+n)!=1{panic("postconf duplicated")}
   name:="native_"+n+"_configuration_and_user_postconf";checks=append(checks,name);fmt.Println("PASS",name)
   expected=append(expected,"start_vpn"+n,"stop_vpn"+n)
  }
 }
 actual:=strings.Split(strings.TrimSpace(string(nrRead("/tmp/owned-vpn-notifications"))),"\n")
 if strings.Join(actual,"\n")!=strings.Join(expected,"\n"){panic(fmt.Sprintf("native notification dispatch: %v expected %v",actual,expected))}
 coPrivateDenied();coUUAlive(u.pid);coUUPage(s)
 checks=append(checks,"native_five_client_two_server_start_stop_notifications_and_uu_private_api_preserved");fmt.Println("PASS",checks[len(checks)-1])
 result:=map[string]any{"checks":checks,"online":map[string]any{"checks":[]string{}},"configurations":7,"service_notifications":len(actual),"actual_tunnel_started":false,"target_pid1_boot_tested":false,"full_upgrade_complete":false}
 b,e=json.Marshal(result);nrMust(e);fmt.Println("VPN_GENERATE_RESULT",string(b))
}
