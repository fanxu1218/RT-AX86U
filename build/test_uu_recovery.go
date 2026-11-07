package main

import (
	"bytes"
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"sync/atomic"
	"syscall"
	"time"
)

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 240*time.Second)
	defer cancel()
	s := nrStart(ctx, "uu-recovery", true)
	defer s.stop()
	s.login()
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	// Preserve the owned running worker; replace only its test HTTP server and
	// test NTP controller so each native failure branch has independent counts.
	u.cmd.Process.Kill()
	u.cmd.Wait()
	u.server.Close()
	coUUAlive(u.pid)
	checks := map[string]bool{}
	details := map[string]any{}
	cert := nrRead("/jffs/cert.tgz")
	nrCommand("/usr/bin/dbus", "set", "uu_recovery_probe=preserved")
	for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-state/user.dat", "/tmp/uu.tar.gz"} {
		nrMust(os.MkdirAll(p[:strings.LastIndex(p, "/")], 0700))
		nrMust(os.WriteFile(p, []byte("preserve-uu-recovery:"+p), 0600))
	}
	monitor := []byte("#!/bin/sh\nprintf invoked\\n >> /tmp/uu-recovery-invocations\n")
	sum := md5.Sum(monitor)
	digest := hex.EncodeToString(sum[:])
	var scenario atomic.Int32
	var calls, downloads atomic.Int32
	l, e := net.Listen("tcp4", "127.0.0.1:35000")
	nrMust(e)
	server := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api":
			calls.Add(1)
			switch scenario.Load() {
			case 1:
				w.WriteHeader(503)
				return
			case 2:
				fmt.Fprintln(w, "invalid-response")
				return
			}
			fmt.Fprintf(w, "http://uu.fixture.test:35000/monitor,%s", digest)
		case "/monitor":
			downloads.Add(1)
			if scenario.Load() == 3 {
				w.Header().Set("Content-Length", fmt.Sprint(len(monitor)+100))
				w.Write(monitor[:8])
				if h, ok := w.(http.Hijacker); ok {
					c, _, e := h.Hijack()
					if e == nil {
						c.Close()
					}
				}
				return
			}
			if scenario.Load() == 4 {
				w.Write([]byte("owned-bad-checksum"))
				return
			}
			w.Write(monitor)
		default:
			w.WriteHeader(404)
		}
	})}
	go server.Serve(l)
	defer server.Close()
	// DNS outage is an explicit test transport boundary; other downloads still
	// use the native wget wrapper with the local CA and hostname verification.
	nrMust(os.Rename("/usr/sbin/wget", "/usr/sbin/wget.recovery-fixture"))
	nrMust(os.WriteFile("/usr/sbin/wget", []byte("#!/bin/sh\nif [ -f /tmp/uu-dns-unavailable ];then for a do case \"$a\" in *router.uu.163.com*|*uu.fixture.test*) exit 6;; esac;done;fi\nexec /usr/sbin/wget.recovery-fixture \"$@\"\n"), 0755))
	defer func() { os.Remove("/usr/sbin/wget"); os.Rename("/usr/sbin/wget.recovery-fixture", "/usr/sbin/wget") }()
	verify := func() {
		coUUAlive(u.pid)
		coUUPage(s)
		coPrivateDenied()
		if !bytes.Equal(cert, nrRead("/jffs/cert.tgz")) || strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "uu_recovery_probe")) != "preserved" {
			panic("network fault changed certificate or plugin data")
		}
		for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-state/user.dat", "/tmp/uu.tar.gz"} {
			if string(nrRead(p)) != "preserve-uu-recovery:"+p {
				panic("UU data lost")
			}
		}
		if string(nrRead("/tmp/owned-uu-launches")) != "start\n" {
			panic("network fault restarted owned UU worker")
		}
		code, body := s.request("GET", "/_api/uu_recovery_", "")
		if code != 200 || !strings.Contains(body, "preserved") {
			panic("center query failed during UU fault")
		}
	}
	start := func(name string) *exec.Cmd {
		for _, p := range []string{"/tmp/native-ntp-idle", "/tmp/native-ntp-synced", "/tmp/uu-recovery-invocations"} {
			os.Remove(p)
		}
		log, e := os.Create(nrOutput("uu-recovery-" + name + ".log"))
		nrMust(e)
		cmd := exec.CommandContext(ctx, "/usr/bin/qemu-arm", "-0", "ntp", "-L", nrQEMURoot(), "-E", "LD_PRELOAD=/work/build/rc_bridge.so:/work/build/native_hw_fixture.so:/work/build/native_uu_transport.so", "/usr/libexec/localmod/rc.vendor")
		cmd.Env = append(os.Environ(), "NATIVE_UU_CASE=1", "NATIVE_UU_TERRITORY=CN/01", "NATIVE_UU_MODE=1")
		cmd.Stdout = log
		cmd.Stderr = log
		nrMust(cmd.Start())
		log.Close()
		ready := false
		for i := 0; i < 200; i++ {
			if _, e := os.Stat("/tmp/native-ntp-idle"); e == nil {
				ready = true
				break
			}
			time.Sleep(30 * time.Millisecond)
		}
		if !ready {
			panic("NTP did not become ready")
		}
		return cmd
	}
	for _, test := range []struct {
		name       string
		mode       int32
		dns, delay bool
	}{{"dns_unavailable", 0, true, false}, {"api_503", 1, false, false}, {"malformed_response", 2, false, false}, {"truncated_monitor", 3, false, false}, {"checksum_mismatch", 4, false, false}, {"delayed_ntp_then_success", 0, false, true}} {
		scenario.Store(test.mode)
		calls.Store(0)
		downloads.Store(0)
		if test.dns {
			nrMust(os.WriteFile("/tmp/uu-dns-unavailable", []byte("1"), 0600))
		} else {
			os.Remove("/tmp/uu-dns-unavailable")
		}
		cmd := start(test.name)
		if test.delay {
			for i := 0; i < 3; i++ {
				verify()
				time.Sleep(200 * time.Millisecond)
			}
			if calls.Load() != 0 {
				panic("UU download before NTP synchronization")
			}
			checks["no_download_before_delayed_ntp_ready"] = true
		}
		nrMust(os.WriteFile("/tmp/native-ntp-synced", []byte("1"), 0600))
		coSync(cmd)
		executed := false
		if b, _ := os.ReadFile("/tmp/uu-recovery-invocations"); len(b) > 0 {
			executed = true
		}
		if executed != test.delay {
			panic("unexpected monitor execution in " + test.name)
		}
		if test.dns && calls.Load() != 0 {
			panic("DNS unavailable still reached repository")
		}
		before := calls.Load()
		coSync(cmd)
		if calls.Load() != before {
			panic("repeated NTP event repeated UU download")
		}
		verify()
		cmd.Process.Signal(syscall.SIGTERM)
		cmd.Wait()
		checks[test.name+"_preserves_center_worker_data_and_native_once_policy"] = true
		details[test.name] = map[string]any{"api_calls": calls.Load(), "monitor_downloads": downloads.Load(), "monitor_executed": executed}
	}
	os.Remove("/tmp/uu-dns-unavailable")
	scenario.Store(0)
	calls.Store(0)
	downloads.Store(0)
	// Model disconnect/reconnect notifications separately from a physical WAN.
	nrCommand("/usr/libexec/localmod/localmod-event", "--sync", "wan-event", "0", "disconnected")
	verify()
	nrCommand("/usr/libexec/localmod/localmod-event", "--sync", "wan-event", "0", "connected")
	verify()
	cmd := start("explicit_network_recovery")
	nrMust(os.WriteFile("/tmp/native-ntp-synced", []byte("1"), 0600))
	coSync(cmd)
	if b, _ := os.ReadFile("/tmp/uu-recovery-invocations"); strings.Count(string(b), "invoked") != 1 {
		panic("explicit recovery did not invoke one monitor")
	}
	before := calls.Load()
	coSync(cmd)
	if calls.Load() != before {
		panic("recovery repeated monitor")
	}
	verify()
	cmd.Process.Signal(syscall.SIGTERM)
	cmd.Wait()
	checks["controlled_wan_notifications_and_fresh_ntp_cycle_recover_once"] = true
	checks["existing_owned_uu_worker_pid_stays_alive_through_all_faults"] = true
	b, e := json.Marshal(map[string]any{"checks": checks, "details": details, "uu_worker_pid": u.pid, "persistent_data_preserved": true, "recovery_policy": "fresh native NTP cycle after controlled network restoration; no automatic replay of a failed native once-only cycle"})
	nrMust(e)
	fmt.Printf("UU_RECOVERY_RESULT %s\n", b)
}
