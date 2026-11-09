package main

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync/atomic"
	"syscall"
	"time"
)

func waitFile(ctx context.Context, p string, limit time.Duration) bool {
	end := time.Now().Add(limit)
	for time.Now().Before(end) && ctx.Err() == nil {
		if _, e := os.Stat(p); e == nil {
			return true
		}
		time.Sleep(30 * time.Millisecond)
	}
	return false
}
func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 150*time.Second)
	defer cancel()
	body := []byte("#!/bin/sh\n[ -z \"$LD_PRELOAD\" ] || exit 19\nprintf 'controlled-monitor\\n' >> /tmp/native-uu-executed\n")
	sum := md5.Sum(body)
	checksum := hex.EncodeToString(sum[:])
	var scenario, api, downloads atomic.Int32
	listener, e := net.Listen("tcp4", "127.0.0.1:35000")
	if e != nil {
		panic(e)
	}
	server := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api":
			api.Add(1)
			switch scenario.Load() {
			case 2:
				w.WriteHeader(503)
				return
			case 3:
				fmt.Fprint(w, "malformed-response")
				return
			}
			hash := checksum
			if scenario.Load() == 1 {
				hash = strings.Repeat("0", 32)
			}
			fmt.Fprintf(w, "http://127.0.0.1:35000/monitor,%s", hash)
		case "/monitor":
			downloads.Add(1)
			w.Write(body)
		default:
			w.WriteHeader(404)
		}
	})}
	go server.Serve(listener)
	defer server.Close()
	tests := []struct {
		name, territory, mode  string
		fault                  int32
		api, download, execute bool
	}{
		{"normal", "CN/01", "1", 0, true, true, true}, {"bad_checksum", "CN/01", "1", 1, true, true, false},
		{"api_503", "CN/01", "1", 2, true, false, false}, {"malformed", "CN/01", "1", 3, true, false, false},
		{"non_china", "US/01", "1", 0, false, false, false}, {"ap_mode", "CN/01", "3", 0, false, false, false},
	}
	rows := []map[string]any{}
	for _, test := range tests {
		scenario.Store(test.fault)
		api.Store(0)
		downloads.Store(0)
		for _, p := range []string{"/tmp/native-ntp-synced", "/tmp/native-uu-executed", "/var/run/ntp.pid", "/tmp/native-ntp-idle"} {
			os.Remove(p)
		}
		os.RemoveAll("/tmp/uu")
		os.RemoveAll("/tmp/native-nvram")
		if e := os.MkdirAll("/tmp/native-nvram", 0700); e != nil {
			panic(e)
		}
		logPath := filepath.Join("/tmp/uu-matrix", test.name+".log")
		f, e := os.Create(logPath)
		if e != nil {
			panic(e)
		}
		executable := os.Getenv("MATRIX_RC_PATH")
		makeCommand := func(applet string, extra ...string) *exec.Cmd {
			args := []string{"-0", applet, "-L", "/", "-E", "LD_PRELOAD=/work/build/merlin38813-uu-matrix/native_hw_fixture.so:/work/build/merlin38813-uu-matrix/native_uu_transport.so:/work/build/merlin38813-uu-matrix/clear_preload.so", executable}
			cmd := exec.CommandContext(ctx, "/usr/bin/qemu-arm", append(args, extra...)...)
			cmd.Env = append(os.Environ(), "NATIVE_UU_CASE=1", "NATIVE_UU_TERRITORY="+test.territory, "NATIVE_UU_MODE="+test.mode)
			cmd.Stdout = f
			cmd.Stderr = f
			return cmd
		}
		ready := false
		finished, repeated := false, false
		var cmd *exec.Cmd
		if os.Getenv("MATRIX_EVENT") == "ntpd_step" {
			cmd = makeCommand("ntpd_synced", "step")
			e = cmd.Run()
			ready = e == nil
			state := func(k string) string { b, _ := os.ReadFile("/tmp/native-nvram/" + k); return string(b) }
			finished = ready && state("ntp_ready") == "11" && state("svc_ready") == "11"
		} else {
			cmd = makeCommand("ntp")
			if e = cmd.Start(); e != nil {
				panic(e)
			}
			ready = waitFile(ctx, "/tmp/native-ntp-idle", 12*time.Second)
			if ready {
				os.Remove("/tmp/native-ntp-idle")
				os.WriteFile("/tmp/native-ntp-synced", []byte("1"), 0600)
				cmd.Process.Signal(syscall.SIGTSTP)
				finished = waitFile(ctx, "/tmp/native-ntp-idle", 12*time.Second)
			}
		}
		// exec_uu starts its monitor asynchronously. Observe every case for the
		// same bounded window, including cases where execution is forbidden.
		observationStart := time.Now()
		timer := time.NewTimer(1500 * time.Millisecond)
		select {
		case <-timer.C:
		case <-ctx.Done():
			timer.Stop()
		}
		_, executeErr := os.Stat("/tmp/native-uu-executed")
		executed := executeErr == nil
		before := api.Load()
		if finished {
			if os.Getenv("MATRIX_EVENT") == "ntpd_step" {
				repeated = makeCommand("ntpd_synced", "step").Run() == nil
			} else {
				os.Remove("/tmp/native-ntp-idle")
				cmd.Process.Signal(syscall.SIGTSTP)
				repeated = waitFile(ctx, "/tmp/native-ntp-idle", 8*time.Second)
			}
		}
		// A repeated event must not enqueue a delayed second monitor either.
		time.Sleep(250 * time.Millisecond)
		monitor, _ := os.ReadFile("/tmp/native-uu-executed")
		runs := strings.Count(string(monitor), "controlled-monitor\n")
		if os.Getenv("MATRIX_EVENT") != "ntpd_step" {
			cmd.Process.Signal(syscall.SIGTERM)
			exited := make(chan struct{})
			go func() { cmd.Wait(); close(exited) }()
			select {
			case <-exited:
			case <-time.After(time.Second):
				cmd.Process.Kill()
				<-exited
			}
		}
		f.Close()
		b, _ := os.ReadFile(logPath)
		expectedRuns := 0
		if test.execute {
			expectedRuns = 1
		}
		pass := ready && finished && repeated && (api.Load() > 0) == test.api && (downloads.Load() > 0) == test.download && executed == test.execute && runs == expectedRuns && api.Load() == before
		row := map[string]any{"name": test.name, "ready": ready, "event_completed": finished, "event_entry": os.Getenv("MATRIX_EVENT"), "repeat_completed": repeated, "api_calls": api.Load(), "downloads": downloads.Load(), "monitor_executed": executed, "monitor_runs": runs, "launch_observation_ms": time.Since(observationStart).Milliseconds(), "matches_factory_contract": pass, "native_log": string(b)}
		rows = append(rows, row)
		fmt.Printf("UU_MATRIX_CASE %s ready=%v complete=%v api=%d downloads=%d executed=%v contract=%v\n", test.name, ready, finished, api.Load(), downloads.Load(), executed, pass)
	}
	b, e := json.Marshal(map[string]any{"base": os.Getenv("MATRIX_BASE"), "rc_path": os.Getenv("MATRIX_RC_PATH"), "cases": rows, "real_uu_monitor_or_acceleration_tested": false})
	if e != nil {
		panic(e)
	}
	fmt.Println("UU_MATRIX_RESULT", string(b))
}
