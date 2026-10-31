package main

import (
	"bytes"
	"context"
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
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
	for i := 0; i < 100; i++ {
		if _, e := os.Stat("/tmp/native-ntp-idle"); e == nil {
			return
		}
		time.Sleep(30 * time.Millisecond)
	}
	panic("native NTP handler did not finish")
}
func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 48*time.Second)
	defer cancel()
	checks := []string{}
	s := nrStart(ctx, "coexist", true)
	defer s.stop()
	s.login()
	fingerprint := s.fingerprint
	savedArchive := nrRead("/jffs/cert.tgz")
	coUUPage(s)
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "start")
	coBackendReady()
	coPrivateDenied()
	coRoundtrip(s, 62001)
	nrCommand("/usr/bin/dbus", "set", "localmod_coexist_persist=retained-with-uu")
	checks = append(checks, "native_restored_tls_login_and_real_center_callback", "original_uu_page_and_private_api_routes_remain_distinct")
	worker := []byte("#!/bin/sh\ntrap 'exit 0' TERM INT\nprintf '%s\\n' \"$$\" > /tmp/owned-uu-worker.pid\nwhile :; do printf tick >> /tmp/owned-uu-heartbeat; sleep 0.1; done\n")
	nrMust(os.WriteFile("/tmp/owned-uu-worker.sh", worker, 0700))
	monitor := []byte("#!/bin/sh\n[ -z \"$LD_PRELOAD\" ] || exit 19\nprintf 'start\\n' >> /tmp/owned-uu-launches\n/bin/sh /tmp/owned-uu-worker.sh </dev/null >/tmp/owned-uu-worker.log 2>&1 &\n")
	sum := md5.Sum(monitor)
	checksum := hex.EncodeToString(sum[:])
	var calls, downloads atomic.Int32
	listener, e := net.Listen("tcp4", "127.0.0.1:35000")
	nrMust(e)
	server := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api":
			calls.Add(1)
			fmt.Fprintf(w, "http://127.0.0.1:35000/monitor,%s", checksum)
		case "/monitor":
			downloads.Add(1)
			w.Write(monitor)
		default:
			w.WriteHeader(404)
		}
	})}
	go server.Serve(listener)
	defer server.Close()
	log, e := os.Create("/work/build/coexist-ntp.log")
	nrMust(e)
	defer log.Close()
	ntp := exec.CommandContext(ctx, "/usr/bin/qemu-arm", "-0", "ntp", "-L", "/work/build/casefs/official_rootfs", "-E", "LD_PRELOAD=/work/build/rc_bridge.so:/work/build/native_hw_fixture.so:/work/build/native_uu_transport.so", "/usr/libexec/localmod/rc.vendor")
	ntp.Env = append(os.Environ(), "NATIVE_UU_CASE=1", "NATIVE_UU_TERRITORY=CN/01", "NATIVE_UU_MODE=1")
	ntp.Stdout = log
	ntp.Stderr = log
	nrMust(ntp.Start())
	defer ntp.Process.Kill()
	ready := false
	for i := 0; i < 200; i++ {
		if _, e := os.Stat("/tmp/native-ntp-idle"); e == nil {
			ready = true
			break
		}
		time.Sleep(30 * time.Millisecond)
	}
	if !ready {
		panic("native NTP not ready")
	}
	nrMust(os.WriteFile("/tmp/native-ntp-synced", []byte("1"), 0600))
	coSync(ntp)
	pid := 0
	for i := 0; i < 100; i++ {
		if b, e := os.ReadFile("/tmp/owned-uu-worker.pid"); e == nil {
			pid, e = strconv.Atoi(strings.TrimSpace(string(b)))
			nrMust(e)
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if pid == 0 {
		panic("owned monitor worker did not start: " + string(nrRead("/work/build/coexist-ntp.log")))
	}
	defer syscall.Kill(pid, syscall.SIGTERM)
	coUUAlive(pid)
	if calls.Load() != 1 || downloads.Load() != 1 {
		panic("UU did not download once")
	}
	coRoundtrip(s, 62002)
	checks = append(checks, "native_ntp_uu_starts_owned_worker_with_center_running")
	var parallel sync.WaitGroup
	for i := 0; i < 8; i++ {
		parallel.Add(1)
		go func(i int) {
			defer parallel.Done()
			local := *s
			if i%2 == 0 {
				coUUPage(&local)
			} else {
				code, body := local.request("GET", "/_api/localmod_coexist_", "")
				if code != 200 || !strings.Contains(body, "retained-with-uu") {
					panic("concurrent software-center read failed")
				}
			}
		}(i)
	}
	parallel.Wait()
	coUUAlive(pid)
	checks = append(checks, "concurrent_https_center_reads_and_native_uu_page_succeed")
	for i := 0; i < 3; i++ {
		command := exec.Command("/usr/bin/qemu-arm", "-0", "iptables-restore", "-L", "/work/build/casefs/official_rootfs", "/work/build/restore-fixture")
		command.Stdin = strings.NewReader("*filter\n:INPUT ACCEPT [0:0]\n:FORWARD ACCEPT [0:0]\n:OUTPUT ACCEPT [0:0]\n-A INPUT -i lo -j ACCEPT\nCOMMIT\n")
		b, e := command.CombinedOutput()
		if e != nil {
			panic(string(b))
		}
		coPrivateDenied()
	}
	coRoundtrip(s, 62003)
	coUUAlive(pid)
	checks = append(checks, "filter_reloads_keep_private_api_guard_callback_and_owned_uu_alive")
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "restart")
	coBackendReady()
	coRoundtrip(s, 62004)
	coUUAlive(pid)
	if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "localmod_coexist_persist")) != "retained-with-uu" {
		panic("center restart lost database")
	}
	if !bytes.Equal(nrRead("/jffs/cert.tgz"), savedArchive) {
		panic("center changed certificate archive")
	}
	checks = append(checks, "center_restart_preserves_database_certificate_and_owned_uu")
	backend := strings.TrimSpace(nrCommand("pidof", "httpdb"))
	s.stop()
	s = nrStart(ctx, "coexist-https-restart", true)
	defer s.stop()
	if s.fingerprint != fingerprint {
		panic("HTTPS restart changed certificate")
	}
	s.login()
	coRoundtrip(s, 62005)
	coUUPage(s)
	coUUAlive(pid)
	if strings.TrimSpace(nrCommand("pidof", "httpdb")) != backend {
		panic("HTTPS restart replaced center backend")
	}
	checks = append(checks, "https_restart_keeps_saved_certificate_center_and_owned_uu")
	coSync(ntp)
	coUUAlive(pid)
	if calls.Load() != 1 || downloads.Load() != 1 || string(nrRead("/tmp/owned-uu-launches")) != "start\n" {
		panic("repeated NTP sync downloaded/launched UU again")
	}
	checks = append(checks, "repeated_ntp_sync_does_not_duplicate_owned_uu_or_disrupt_center")
	nrMust(os.WriteFile("/jffs/localmod-disabled", nil, 0600))
	stopped := false
	for i := 0; i < 120; i++ {
		if exec.Command("pidof", "httpdb").Run() != nil {
			stopped = true
			break
		}
		time.Sleep(30 * time.Millisecond)
	}
	if !stopped {
		panic("recovery marker left center backend active")
	}
	coUUPage(s)
	coUUAlive(pid)
	code, _ := s.request("GET", "/_api/localmod_coexist_", "")
	if code == 200 {
		panic("center API still active after recovery stop")
	}
	checks = append(checks, "center_recovery_stop_keeps_native_https_and_owned_uu")
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "stop")
	coUUAlive(pid)
	ntp.Process.Kill()
	ntp.Wait()
	s.stop()
	nrResult("coexist", checks, map[string]any{"leaf_sha256": fingerprint, "uu_api_requests": calls.Load(), "uu_monitor_downloads": downloads.Load(), "parallel_requests": 8, "filter_reload_cycles": 3, "real_uu_monitor_executed": false})
	fmt.Println("PASS native HTTPd/rc with real center lifecycle; owned UU worker and local download only; no target kernel or actual acceleration")
}
