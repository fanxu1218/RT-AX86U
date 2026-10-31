package main

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"
)

var coReadyPort = 800

func coBackendReady() {
	// Rotate reserved ports: an earlier successful probe can leave its source
	// tuple in TIME_WAIT while the backend itself is already healthy.
	for i := 0; i < 100; i++ {
		coReadyPort++
		if coReadyPort > 1023 {
			coReadyPort = 800
		}
		d := net.Dialer{Timeout: 50 * time.Millisecond, LocalAddr: &net.TCPAddr{IP: net.ParseIP("127.0.0.1"), Port: coReadyPort}}
		c, e := d.Dial("tcp4", "127.0.0.1:3032")
		if e == nil {
			c.Close()
			return
		}
		time.Sleep(30 * time.Millisecond)
	}
	panic("software-center backend did not start")
}
func coPrivateDenied() {
	c, e := net.DialTimeout("tcp4", "127.0.0.1:3032", 100*time.Millisecond)
	if e == nil {
		c.Close()
		panic("unprivileged private API connection succeeded")
	}
}
func coRoundtrip(s *nrServer, id int) {
	payload := fmt.Sprintf(`{"id":%d,"method":"coexist_probe.sh","params":[],"fields":{"localmod_coexist_input":"coexist-%d"}}`, id, id)
	code, body := s.request("POST", "/_api/", payload)
	if code != 200 || !strings.Contains(body, fmt.Sprint(id)) {
		panic(fmt.Sprintf("coexist callback %d %s", code, body))
	}
	code, body = s.request("GET", "/_api/localmod_coexist_", "")
	if code != 200 || !strings.Contains(body, fmt.Sprintf("coexist-%d-ok", id)) {
		panic(fmt.Sprintf("coexist fields %d %s", code, body))
	}
}
func coUUPage(s *nrServer) {
	code, body := s.request("GET", "/UUAccelerator.asp", "")
	if code != 200 || !strings.Contains(body, "uuRegister") || !strings.Contains(body, "router.uu.163.com/asus/pc.html") {
		panic(fmt.Sprintf("native UU page %d %s", code, body))
	}
}
func coUUAlive(pid int) {
	initial, _ := os.ReadFile("/tmp/owned-uu-heartbeat")
	before := len(initial)
	for i := 0; i < 30; i++ {
		current, e := strconv.Atoi(strings.TrimSpace(string(nrRead("/tmp/owned-uu-worker.pid"))))
		nrMust(e)
		if current != pid || syscall.Kill(pid, 0) != nil {
			panic("owned UU worker was replaced/stopped")
		}
		if b, _ := os.ReadFile("/tmp/owned-uu-heartbeat"); len(b) > before {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	panic("owned UU worker heartbeat stopped")
}
func coSync(cmd *exec.Cmd) {
	os.Remove("/tmp/native-ntp-idle")
	nrMust(cmd.Process.Signal(syscall.SIGTSTP))
	limit := 3 * time.Second
	if raw := os.Getenv("LOCALMOD_NTP_WAIT_TIMEOUT"); raw != "" {
		var e error
		limit, e = time.ParseDuration(raw)
		nrMust(e)
		if limit <= 0 || limit > time.Minute {
			panic("invalid NTP fixture wait limit")
		}
	}
	started := time.Now()
	deadline := started.Add(limit)
	for time.Now().Before(deadline) {
		if _, e := os.Stat("/tmp/native-ntp-idle"); e == nil {
			if elapsed := time.Since(started); elapsed > 3*time.Second {
				fmt.Printf("NTP_HANDLER_COMPLETED elapsed=%s signals_sent=1\n", elapsed)
			}
			return
		}
		time.Sleep(30 * time.Millisecond)
	}
	if b, e := exec.Command("/bin/ps", "w").CombinedOutput(); e == nil {
		fmt.Printf("NTP_WAIT_PROCESSES\n%s\n", b)
	}
	for _, name := range []string{"status", "wchan", "task/" + strconv.Itoa(cmd.Process.Pid) + "/children"} {
		p := fmt.Sprintf("/proc/%d/%s", cmd.Process.Pid, name)
		if b, e := os.ReadFile(p); e == nil {
			fmt.Printf("NTP_WAIT_DIAGNOSTIC %s\n%s\n", p, b)
		}
	}
	if f, ok := cmd.Stdout.(*os.File); ok {
		if b, e := os.ReadFile(f.Name()); e == nil {
			fmt.Printf("NTP_WAIT_DIAGNOSTIC %s\n%s\n", f.Name(), b)
		}
	}
	panic("native NTP handler did not finish")
}
