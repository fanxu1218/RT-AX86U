package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

func boundRun(args ...string) (int, string) {
	b, e := exec.Command(args[0], args[1:]...).CombinedOutput()
	if e == nil {
		return 0, string(b)
	}
	if x, ok := e.(*exec.ExitError); ok {
		return x.ExitCode(), string(b)
	}
	panic(e)
}
func boundWait(p string, needle string) {
	for i := 0; i < 100; i++ {
		b, _ := os.ReadFile(p)
		if bytes.Contains(b, []byte(needle)) {
			return
		}
		time.Sleep(30 * time.Millisecond)
	}
	panic("expected log missing: " + p + " " + needle)
}
func main() {
	checks := map[string]bool{}
	base := "/tmp/localmod-bounds"
	nrMust(os.MkdirAll(base, 0700))
	nrMust(os.MkdirAll("/jffs/scripts", 0700))
	nrMust(os.WriteFile("/tmp/bounds-dispatch.sh", []byte("#!/bin/sh\nprintf '%s:%s\\n' \"$1\" \"$2\" >> /tmp/bounds-order\nif [ \"$2\" = noisy ];then dd if=/dev/zero bs=4096 count=100 2>/dev/null;fi\nif [ \"$2\" = background ];then (sleep 1;echo background-ok) & fi\n"), 0755))
	fixture := "/work/build/event-bounds-fixture"
	var accepted atomic.Int32
	var rejected atomic.Int32
	var wg sync.WaitGroup
	for n := 0; n < 8; n++ {
		wg.Add(1)
		go func(worker int) {
			defer wg.Done()
			for i := 0; i < 32; i++ {
				c, _ := boundRun(fixture, "wan-event", fmt.Sprintf("%d-%d", worker, i))
				if c == 0 {
					accepted.Add(1)
				} else {
					rejected.Add(1)
				}
			}
		}(n)
	}
	wg.Wait()
	entries, e := os.ReadDir(base + "/queue")
	nrMust(e)
	if accepted.Load() != 128 || rejected.Load() != 128 || len(entries) != 128 {
		panic(fmt.Sprintf("queue not bounded %d %d %d", accepted.Load(), rejected.Load(), len(entries)))
	}
	checks["concurrent_256_events_admit_exactly_128_with_explicit_backpressure"] = true
	// Synchronous critical hooks bypass the asynchronous storage cap.
	if c, _ := boundRun(fixture, "--sync", "pre-mount", "critical"); c != 0 {
		panic("full queue broke critical sync hook")
	}
	boundWait("/tmp/bounds-order", "pre-mount:critical")
	checks["full_queue_preserves_synchronous_pre_mount_execution"] = true
	// Compare delivery order with immutable queued records sorted by filename.
	expected := []string{}
	for _, entry := range entries {
		b := nrRead(base + "/queue/" + entry.Name())
		name := strings.TrimRight(string(b[4:36]), "\x00")
		arg := strings.TrimRight(string(b[36:4132]), "\x00")
		expected = append(expected, name+":"+arg)
	}
	if c, out := boundRun(fixture, "--drain"); c != 0 {
		panic(out)
	}
	lines := strings.Split(strings.TrimSpace(string(nrRead("/tmp/bounds-order"))), "\n")
	if len(lines) != 129 || strings.Join(lines[1:], "\n") != strings.Join(expected, "\n") {
		panic("event order or count changed")
	}
	checks["accepted_events_drain_once_in_queue_order"] = true
	if c, _ := boundRun(fixture, "wan-start", "recovered"); c != 0 {
		panic("queue did not accept after drain")
	}
	boundRun(fixture, "--drain")
	boundWait("/tmp/bounds-order", "wan-start:recovered")
	checks["queue_accepts_again_after_drain"] = true
	// Run a daemon barrier while accepted events exist: reserve avoids cap starvation.
	for i := 0; i < 128; i++ {
		if c, _ := boundRun(fixture, "nat-start", fmt.Sprint(i)); c != 0 {
			panic("refill failed")
		}
	}
	d := exec.Command(fixture, "--daemon")
	nrMust(d.Start())
	defer func() { d.Process.Signal(syscall.SIGTERM); d.Wait() }()
	ready := false
	for i := 0; i < 100; i++ {
		b, _ := os.ReadFile(base + "/eventd.pid")
		if strings.TrimSpace(string(b)) == fmt.Sprint(d.Process.Pid) {
			ready = true
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if !ready {
		panic("fixture event daemon did not publish its PID")
	}
	if c, out := boundRun("/work/build/barrier-bounds-fixture"); c != 0 {
		panic("barrier failed: " + out)
	}
	checks["barrier_finishes_prior_events_using_reserved_capacity"] = true
	nrMust(d.Process.Signal(syscall.SIGTERM))
	d.Wait()
	if c, _ := boundRun(fixture, "--sync", "wan-event", "noisy"); c != 0 {
		panic("noisy hook failed")
	}
	boundWait(base+"/events.log", "\x00")
	if c, _ := boundRun(fixture, "--sync", "wan-event", "background"); c != 0 {
		panic("background hook failed")
	}
	boundWait(base+"/events.log", "background-ok")
	for _, name := range []string{"events.log", "events.log.1"} {
		s, e := os.Stat(base + "/" + name)
		nrMust(e)
		if s.Size() > 128*1024 || s.Mode().Perm() != 0600 {
			panic("hook log bound/permissions failed")
		}
	}
	checks["noisy_and_background_hooks_keep_running_with_bounded_private_logs"] = true
	// Upgrade from an oversized legacy log must cap the retained .1 as well.
	nrMust(os.WriteFile("/tmp/.localmod/bootstrap.log", bytes.Repeat([]byte("old\n"), 100000), 0600))
	if c, _ := boundRun("/usr/libexec/localmod/log-limit", "bootstrap", "/bin/sh", "-c", "printf bounded-end; exit 9"); c != 9 {
		panic("logger changed command exit status")
	}
	boundWait("/tmp/.localmod/bootstrap.log", "bounded-end")
	for _, n := range []string{"bootstrap.log", "bootstrap.log.1"} {
		s, e := os.Stat("/tmp/.localmod/" + n)
		nrMust(e)
		if s.Size() > 128*1024 {
			panic("legacy log retained above bound")
		}
	}
	checks["legacy_large_logs_trim_and_rotate_without_changing_exit_status"] = true
	for _, kind := range []string{"install", "offline"} {
		cmd := exec.Command("/usr/libexec/localmod/log-limit", "--tee", kind)
		cmd.Stdin = bytes.NewReader(append(bytes.Repeat([]byte("owned-noisy-installer\n"), 20000), []byte("XU6J03M6\n")...))
		nrMust(cmd.Run())
	}
	for _, name := range []string{"soft_install_log.txt", "soft_log.txt", "soft_log_backup.txt"} {
		p := "/tmp/upload/" + name
		boundWait(p, "XU6J03M6")
		for _, suffix := range []string{"", ".1"} {
			s, e := os.Stat(p + suffix)
			nrMust(e)
			if s.Size() > 128*1024 {
				panic("installer frontend log above bound")
			}
		}
	}
	checks["noisy_online_offline_and_backup_frontend_logs_bounded_with_completion_marker"] = true
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	s := nrStart(ctx, "resource-bounds", true)
	defer s.stop()
	s.login()
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	cert := nrRead("/jffs/cert.tgz")
	nrCommand("/usr/bin/dbus", "set", "bounds_config=preserved")
	for i := 0; i < 2; i++ {
		nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "restart")
		coBackendReady()
		coUUAlive(u.pid)
	}
	if !bytes.Equal(cert, nrRead("/jffs/cert.tgz")) || strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "bounds_config")) != "preserved" {
		panic("bounded logs lifecycle lost data")
	}
	coPrivateDenied()
	coUUPage(s)
	checks["production_bootstrap_restart_preserves_database_certificate_private_api_and_uu"] = true
	for _, name := range []string{"bootstrap", "events", "skipd"} {
		for _, suffix := range []string{".log", ".log.1"} {
			p := filepath.Join("/tmp/.localmod", name+suffix)
			st, e := os.Stat(p)
			if e == nil && st.Size() > 128*1024 {
				panic("production log above bound")
			}
		}
	}
	checks["all_managed_logs_capped_at_two_128kib_files"] = true
	b, e := json.Marshal(map[string]any{"checks": checks, "accepted": accepted.Load(), "rejected": rejected.Load(), "maximum_queue_entries": 128, "managed_log_limit_bytes": 128 * 1024})
	nrMust(e)
	fmt.Printf("RESOURCE_BOUNDS_RESULT %s\n", b)
}
