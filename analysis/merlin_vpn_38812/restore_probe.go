package main

import (
    "context"
    "encoding/json"
    "fmt"
    "os/exec"
    "strings"
    "time"
)

func main() {
    ctx,cancel:=context.WithTimeout(context.Background(),180*time.Second);defer cancel()
    s:=nrStart(ctx,"native-restore-probe",true);defer s.stop();s.login();coBackendReady()
    u:=previewUUStart(ctx);defer u.close()
    rules:="*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\n-A INPUT -p tcp --dport 65000 -j ACCEPT\nCOMMIT\n"
    counts:=[]int{}
    for i:=0;i<3;i++ {
        if i==1 {
            for j:=0;j<2;j++ {nrCommand("/usr/sbin/iptables","-I","INPUT","1","-d","127.0.0.1/32","-p","tcp","--dport","3032","-j","LOCALMOD_API")}
            if strings.Count(nrCommand("/usr/sbin/iptables","-S","INPUT"),"-j LOCALMOD_API")!=3 {panic("legacy duplicate fixture was not established")}
        }
        args:=[]string{"-0","iptables-restore","-L","/","-E","LD_PRELOAD=/work/build/native-restore-probe/restore_kernel_fixture.so","/usr/sbin/iptables-restore"}
        if i>0 {args=append(args,"--noflush")}
        payload:=rules
        if i>0 {payload=strings.ReplaceAll(payload,"-A INPUT -p tcp --dport 65000 -j ACCEPT\n","")}
        cmd:=exec.CommandContext(ctx,"/usr/bin/qemu-arm",args...);cmd.Stdin=strings.NewReader(payload)
        b,e:=cmd.CombinedOutput();if e!=nil {panic(fmt.Sprintf("actual candidate restore %d: %v %s",i,e,b))}
        input:=nrCommand("/usr/sbin/iptables","-S","INPUT")
        counts=append(counts,strings.Count(input,"-j LOCALMOD_API"))
        if strings.Count(input,"--dport 65000 -j ACCEPT")!=1 {panic("unrelated INPUT rule lost or duplicated: "+input)}
        guard:=nrCommand("/usr/sbin/iptables","-S","LOCALMOD_API")
        if strings.Count(guard,"-A LOCALMOD_API")!=2 {panic("guard chain rules changed: "+guard)}
        coPrivateDenied();coUUAlive(u.pid)
        fmt.Printf("RESTORE_PROBE_ROUND index=%d input_guard_jumps=%d\n",i,counts[i])
    }
    boundary:=string(nrRead("/tmp/owned-restore-kernel-boundary"))
    if strings.Count(boundary,"/usr/sbin/xtables-multi iptables-restore\n")!=3 {panic("restore did not traverse declared kernel boundary")}
    if counts[0]!=1 {panic("baseline full restore guard differs")}
    result:=map[string]any{"checks":[]string{"actual_candidate_restore_applies_guard_and_preserves_private_api_uu"},"online":map[string]any{"checks":[]string{}},"input_guard_jump_counts":counts,"contract_matches":counts[1]==1 && counts[2]==1,"kernel_boundary_fixture":true,"target_4_1_kernel_tested":false,"full_upgrade_complete":false}
    b,e:=json.Marshal(result);nrMust(e);fmt.Println("RESTORE_PROBE_RESULT",string(b))
}
