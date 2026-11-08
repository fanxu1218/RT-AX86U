package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

type diagnostic struct {
	c                               *coexistRun
	target                          int
	control                         int
	controlCmd                      *exec.Cmd
	controlLog                      *os.File
	controlStartTicks               string
	controlPages                    map[string]int
	started                         time.Time
	startTicks                      string
	runtimeOriginal, statusOriginal []byte
	cases, samples, boundaries      []map[string]any
	backgroundErrors                []string
	pages                           map[string]int
	stage                           atomic.Value
	mu                              sync.Mutex
	pids                            map[string]int
}

func dEmit(prefix string, v any) {
	b, e := json.Marshal(v)
	nrMust(e)
	fmt.Printf("%s %s\n", prefix, b)
}
func dProc(p int) map[string]any {
	exe, e := os.Readlink(fmt.Sprintf("/proc/%d/exe", p))
	nrMust(e)
	stat := string(nrRead(fmt.Sprintf("/proc/%d/stat", p)))
	f := strings.Fields(stat[strings.LastIndex(stat, ") ")+2:])
	if len(f) < 20 {
		panic("invalid proc stat")
	}
	out := map[string]any{"pid": p, "executable": exe, "rss_kib": rss(p), "fds": fds(p), "start_ticks": f[19], "user_ticks": f[11], "system_ticks": f[12]}
	for _, l := range strings.Split(string(nrRead(fmt.Sprintf("/proc/%d/status", p))), "\n") {
		parts := strings.Fields(l)
		if len(parts) > 1 && (parts[0] == "Threads:" || parts[0] == "THP_enabled:") {
			out[strings.TrimSuffix(parts[0], ":")] = parts[1]
		}
	}
	return out
}
func (d *diagnostic) processIDs() map[string]int {
	ids := map[string]int{"httpd": d.c.x.s.cmd.Process.Pid, "httpdb": pid("httpdb"), "skipd": pid("skipd"), "ddnsgo": pid("ddnsgo"), "uu": d.c.x.u.pid}
	if d.control > 0 {
		ids["ddnsgo_no_thp"] = d.control
	}
	for name, p := range d.c.procs {
		ids[name] = p.cmd.Process.Pid
	}
	return ids
}
func (d *diagnostic) integrity() {
	c, x := d.c, d.c.x
	for p, want := range c.files {
		if !bytes.Equal(want, nrRead(p)) {
			panic("changed retained file " + p)
		}
	}
	for p, want := range x.sentinels {
		if !bytes.Equal(want, nrRead(p)) {
			panic("changed UU file " + p)
		}
	}
	if !bytes.Equal(x.config, nrRead("/koolshare/configs/ddnsgo/default.yaml")) || !bytes.Equal(x.cert, nrRead("/jffs/cert.tgz")) || nrCommand("/usr/bin/dbus", "list", "ddnsgo_") != x.db {
		panic("DDNS config/database/cert changed")
	}
	for k, v := range c.db {
		if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", k)) != v {
			panic("changed Fancyss key " + k)
		}
	}
	coUUAlive(x.u.pid)
	if x.u.calls.Load() != 1 || x.u.downloads.Load() != 1 || strings.Count(string(nrRead("/tmp/owned-uu-launches")), "start\n") != 1 {
		panic("unexpected UU download/restart")
	}
	if d.pids != nil {
		for name, p := range d.processIDs() {
			if d.pids[name] != p {
				panic("unexpected service PID change " + name)
			}
		}
	}
	if d.target > 0 && pid("ddnsgo") != d.target {
		panic("memory target changed PID")
	}
}
func (d *diagnostic) installTracing() {
	path := "/koolshare/scripts/ss_status.sh"
	d.statusOriginal = nrRead(path)
	mark := func(label string) string {
		return "{ read diag_now diag_rest < /proc/uptime; printf '%s pid=%s stage=" + label + " callback_id=%s\\n' \"$diag_now\" \"$$\" \"$ID\" >> /tmp/diag-fancy/${STATUS_HTTP_ID}.log; }\n"
	}
	s := string(d.statusOriginal)
	if strings.Count(s, "source /koolshare/scripts/ss_base.sh") != 1 {
		panic("status source anchor")
	}
	s = strings.Replace(s, "source /koolshare/scripts/ss_base.sh", mark("before_base")+"source /koolshare/scripts/ss_base.sh\n"+mark("after_base"), 1)
	anchor := "\t\thttp_response \"${payload}\" >/dev/null 2>&1"
	if strings.Count(s, anchor) != 1 {
		panic("status callback anchor")
	}
	s = strings.Replace(s, anchor, mark("before_callback")+anchor+"\n"+mark("after_callback"), 1)
	nrMust(os.MkdirAll("/tmp/diag-fancy", 0700))
	nrMust(os.WriteFile(path, []byte(s), 0755))
	mWrite("/koolshare/scripts/diag_fancy_control.sh", "#!/bin/sh\n. /koolshare/scripts/base.sh\nhttp_response diag-control-$ID\n", 0755)
	dEmit("DIAG_SCRIPT_TRACE", map[string]any{"original_sha256": fmt.Sprintf("%x", sha256.Sum256(d.statusOriginal)), "instrumented_sha256": fmt.Sprintf("%x", sha256.Sum256([]byte(s))), "changes": "builtin uptime/phase metadata only; no status logic, timeout, cache or callback changes"})
}
func (d *diagnostic) runtimeStart() {
	c := d.c
	old := pid("ddnsgo")
	nrCommand("/bin/sh", "-c", ". /koolshare/scripts/base.sh; perpctl d ddnsgo")
	waitGone(old)
	p := "/koolshare/perp/ddnsgo/rc.main"
	d.runtimeOriginal = nrRead(p)
	if strings.Count(string(d.runtimeOriginal), "exec ddnsgo ") != 1 {
		panic("runtime supervisor anchor")
	}
	rows := strings.Split(string(d.runtimeOriginal), "\n")
	for i, l := range rows {
		if strings.Contains(l, "exec ddnsgo ") {
			rows[i] = strings.Replace(l, "exec ddnsgo ", "exec env GODEBUG=gctrace=1,scavtrace=1,gcpacertrace=1 ddnsgo ", 1) + " >/tmp/diag-ddns-runtime.log 2>&1"
		}
	}
	nrMust(os.WriteFile(p, []byte(strings.Join(rows, "\n")), 0755))
	nrCommand("/bin/sh", "-c", ". /koolshare/scripts/base.sh; perpctl u ddnsgo")
	deadline := time.Now().Add(30 * time.Second)
	for time.Now().Before(deadline) {
		b, _ := exec.Command("/bin/sh", "-c", "pidof ddnsgo || true").CombinedOutput()
		if strings.TrimSpace(string(b)) != "" {
			con, e := net.DialTimeout("tcp4", "127.0.0.1:9876", 100*time.Millisecond)
			if e == nil {
				con.Close()
				d.target = pid("ddnsgo")
				break
			}
		}
		time.Sleep(100 * time.Millisecond)
	}
	if d.target == 0 || d.target == old {
		panic("runtime listener not ready")
	}
	d.startTicks = dProc(d.target)["start_ticks"].(string)
	h, e := mRun("/koolshare/bin/ddnsgo", "-h")
	dEmit("DIAG_DDNS_HELP", map[string]any{"output": h, "error": fmt.Sprint(e)})
	b := nrRead("/koolshare/bin/ddnsgo")
	dEmit("DIAG_DDNS_EXECUTABLE", map[string]any{"sha256": fmt.Sprintf("%x", sha256.Sum256(b)), "process": dProc(d.target), "original_pid": old, "gc_policy": "default unchanged; GODEBUG observational traces only", "model_copied_config_unchanged": bytes.Equal(c.x.config, nrRead("/koolshare/configs/ddnsgo/default.yaml"))})
}
func (d *diagnostic) request(kind, method string, pause time.Duration) map[string]any {
	x := d.c.x
	x.id++
	id := x.id
	body, _ := json.Marshal(map[string]any{"id": id, "method": method, "params": []string{"1"}, "fields": ""})
	url := "https://192.168.77.1:34443/_api/"
	var transport http.RoundTripper = x.s.client.Transport
	if kind == "backend" {
		dial := &net.Dialer{Timeout: 3 * time.Second, LocalAddr: &net.TCPAddr{IP: net.ParseIP("127.0.0.1"), Port: 500 + id%250}}
		t := &http.Transport{DialContext: dial.DialContext, DisableKeepAlives: true}
		defer t.CloseIdleConnections()
		transport = t
		url = "http://127.0.0.1:3032/_api/"
	}
	req, e := http.NewRequest("POST", url, bytes.NewReader(body))
	nrMust(e)
	req.Header.Set("User-Agent", "Mozilla/5.0 native-lifecycle-fixture")
	req.Header.Set("Origin", "https://192.168.77.1:34443")
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(&http.Cookie{Name: "asus_s_token", Value: x.s.token})
	started := time.Now()
	timings := map[string]float64{}
	var mu sync.Mutex
	stamp := func(k string) { mu.Lock(); timings[k] = time.Since(started).Seconds(); mu.Unlock() }
	written := make(chan struct{}, 1)
	req = req.WithContext(httptrace.WithClientTrace(req.Context(), &httptrace.ClientTrace{ConnectDone: func(_, _ string, e error) { stamp("connect_done") }, TLSHandshakeStart: func() { stamp("tls_start") }, TLSHandshakeDone: func(tls.ConnectionState, error) { stamp("tls_done") }, WroteRequest: func(httptrace.WroteRequestInfo) {
		stamp("request_written")
		select {
		case written <- struct{}{}:
		default:
		}
	}, GotFirstResponseByte: func() { stamp("first_response_byte") }}))
	stop := make(chan struct{})
	watched := make(chan string, 1)
	go func() {
		select {
		case <-stop:
			watched <- ""
		case <-time.After(7 * time.Second):
			b, _ := exec.Command("/bin/ps", "w").CombinedOutput()
			watched <- string(b)
		}
	}()
	resume := make(chan struct{})
	if pause > 0 {
		go func() {
			defer close(resume)
			select {
			case <-written:
			case <-time.After(10 * time.Second):
				return
			}
			nrMust(syscall.Kill(x.s.cmd.Process.Pid, syscall.SIGSTOP))
			time.Sleep(pause)
			nrMust(syscall.Kill(x.s.cmd.Process.Pid, syscall.SIGCONT))
		}()
	} else {
		close(resume)
	}
	client := &http.Client{Transport: transport, Timeout: 10 * time.Second, CheckRedirect: x.s.client.CheckRedirect}
	response, e := client.Do(req)
	code, n := 0, 0
	valid := false
	replyID := ""
	resultBytes := 0
	if e == nil {
		code = response.StatusCode
		b, err := io.ReadAll(response.Body)
		response.Body.Close()
		e = err
		n = len(b)
		var out struct {
			ID     any             `json:"id"`
			Result json.RawMessage `json:"result"`
		}
		parse := json.Unmarshal(b, &out)
		replyID = fmt.Sprint(out.ID)
		resultBytes = len(out.Result)
		var text string
		resultErr := json.Unmarshal(out.Result, &text)
		expected := strings.Contains(text, "等待") && strings.Contains(text, "@@")
		if method == "diag_fancy_control.sh" {
			expected = text == "diag-control-"+strconv.Itoa(id)
		}
		valid = e == nil && parse == nil && resultErr == nil && code == 200 && (out.ID == nil || replyID == strconv.Itoa(id)) && resultBytes > 0 && expected
	}
	elapsed := time.Since(started).Seconds()
	close(stop)
	processes := <-watched
	<-resume
	// Preserve late markers for this ID only; do not replay any request.
	if e != nil {
		time.Sleep(time.Second)
	}
	stages, _ := os.ReadFile(fmt.Sprintf("/tmp/diag-fancy/%d.log", id))
	mu.Lock()
	row := map[string]any{"id": id, "kind": kind, "method": method, "error": fmt.Sprint(e), "code": code, "valid": valid, "reply_id": replyID, "body_bytes": n, "result_bytes": resultBytes, "timeout_seconds": 10, "elapsed_seconds": elapsed, "controlled_httpd_pause_seconds": pause.Seconds(), "timings": cloneTimes(timings), "script_stages": string(stages), "process_snapshot_at_7s": processes}
	mu.Unlock()
	d.cases = append(d.cases, row)
	dEmit("DIAG_LATENCY", row)
	return row
}
func (d *diagnostic) switchHTTPd(qemu bool, label string) {
	d.c.x.s.stop()
	if qemu {
		os.Setenv("DIAG_HTTPD_QEMU", "1")
	} else {
		os.Unsetenv("DIAG_HTTPD_QEMU")
	}
	d.c.x.s = nrStart(d.c.x.ctx, label, true)
	d.c.x.s.login()
	dEmit("DIAG_HTTPD", dProc(d.c.x.s.cmd.Process.Pid))
}
func (d *diagnostic) calibrate(short bool) {
	n := 6
	if short {
		n = 2
	}
	for block, emulated := range []bool{false, true, false} {
		if block > 0 {
			d.switchHTTPd(emulated, fmt.Sprintf("diag-mode-%d", block))
		}
		kind := fmt.Sprintf("native_%d", block)
		if emulated {
			kind = "qemu_user"
		}
		for i := 0; i < n; i++ {
			d.request(kind, "ss_status.sh", 0)
			d.request(kind, "diag_fancy_control.sh", 0)
			d.request("backend", "ss_status.sh", 0)
			d.integrity()
		}
	}
	// Expected scheduler-unavailability controls validate attribution, not a natural failure claim.
	d.request("controlled_pause_4s", "ss_status.sh", 4*time.Second)
	d.request("controlled_pause_12s", "ss_status.sh", 12*time.Second)
	d.c.x.query("status")
	d.integrity()
}
func (d *diagnostic) heapProbe() map[string]any {
	client := &http.Client{Timeout: 3 * time.Second, Transport: &http.Transport{DisableKeepAlives: true}, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	r, e := client.Get("http://127.0.0.1:9876/debug/pprof/heap?debug=1")
	if e != nil {
		return map[string]any{"available": false, "error": fmt.Sprint(e)}
	}
	defer r.Body.Close()
	b, e := io.ReadAll(io.LimitReader(r.Body, 4*1024*1024))
	valid := e == nil && r.StatusCode == 200 && bytes.Contains(b, []byte("# runtime.MemStats")) && bytes.Contains(b, []byte("heap profile:"))
	out := map[string]any{"available": valid, "code": r.StatusCode, "bytes": len(b), "content_type": r.Header.Get("Content-Type")}
	if valid {
		out["profile"] = string(b)
	}
	return out
}
func (d *diagnostic) sample(stage, role string) map[string]any {
	if pid("ddnsgo") != d.target {
		panic("DDNS PID changed")
	}
	proc := dProc(d.target)
	if proc["start_ticks"] != d.startTicks {
		panic("DDNS start time changed")
	}
	maps := smaps(d.target)
	rss, dirty, anon, huge, swap := 0, 0, 0, 0, 0
	groups := map[string]map[string]int{}
	for _, m := range maps {
		rss += m.RSS
		dirty += m.PrivateDirty
		anon += m.Anonymous
		huge += m.Huge
		swap += m.Swap
		name := m.Path
		if name == "" {
			name = "anonymous"
		}
		key := m.Perm + " " + name
		if groups[key] == nil {
			groups[key] = map[string]int{}
		}
		g := groups[key]
		g["rss_kib"] += m.RSS
		g["private_dirty_kib"] += m.PrivateDirty
		g["anonymous_kib"] += m.Anonymous
		g["anon_huge_pages_kib"] += m.Huge
		g["virtual_kib"] += int((m.End - m.Start) / 1024)
	}
	log, _ := os.ReadFile("/tmp/diag-ddns-runtime.log")
	gc := []string{}
	scav := []string{}
	pacer := []string{}
	for _, l := range strings.Split(string(log), "\n") {
		if strings.HasPrefix(l, "gc ") {
			gc = append(gc, l)
		}
		if strings.HasPrefix(l, "scav ") {
			scav = append(scav, l)
		}
		if strings.HasPrefix(l, "pacer:") {
			pacer = append(pacer, l)
		}
	}
	co := map[string]any{}
	for name, p := range d.processIDs() {
		if d.pids[name] != p {
			panic("coexist PID changed " + name)
		}
		co[name] = dProc(p)
	}
	row := map[string]any{"elapsed_seconds": time.Since(d.started).Seconds(), "stage": stage, "role": role, "process": proc, "smaps_rss_kib": rss, "private_dirty_kib": dirty, "anonymous_kib": anon, "anon_huge_pages_kib": huge, "swap_kib": swap, "rollup": dRollup(d.target), "no_thp_control": d.controlSample(), "maps": groups, "gc_count": len(gc), "scav_count": len(scav), "pacer_count": len(pacer), "coexist_processes": co}
	if len(gc) > 0 {
		row["latest_gc"] = gc[len(gc)-1]
	}
	if len(scav) > 0 {
		row["latest_scav"] = scav[len(scav)-1]
	}
	d.samples = append(d.samples, row)
	if role != "periodic" {
		d.boundaries = append(d.boundaries, row)
	}
	dEmit("DIAG_MEMORY", row)
	return row
}
func dStage(elapsed time.Duration, short bool) (string, int) {
	warm, load, idle, rounds, final := 120, 120, 300, 6, 960
	if short {
		warm, load, idle, rounds, final = 15, 30, 120, 1, 15
	}
	t := int(elapsed.Seconds())
	if t < warm {
		return "warmup", warm
	}
	t -= warm
	if t >= rounds*(load+idle) {
		return "final_idle", warm + rounds*(load+idle) + final
	}
	round := t/(load+idle) + 1
	in := t % (load + idle)
	if in < load {
		return fmt.Sprintf("load_%d", round), warm + (round-1)*(load+idle) + load
	}
	return fmt.Sprintf("idle_%d", round), warm + round*(load+idle)
}
func (d *diagnostic) memoryCycles(short bool) map[string]any {
	seconds := 3600
	if short {
		seconds = 180
	}
	d.pids = d.processIDs()
	d.started = time.Now()
	d.stage.Store("warmup")
	d.pages = map[string]int{}
	d.controlPages = map[string]int{}
	d.backgroundErrors = []string{}
	ctx, cancel := context.WithCancel(d.c.x.ctx)
	done := make(chan struct{})
	var targetRequests atomic.Int64
	go func() {
		defer close(done)
		client := &http.Client{Timeout: 5 * time.Second, Transport: &http.Transport{DisableKeepAlives: true}}
		tick := time.NewTicker(500 * time.Millisecond)
		defer tick.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-tick.C:
				stage := d.stage.Load().(string)
				if stage != "warmup" && !strings.HasPrefix(stage, "load_") {
					continue
				}
				ports := []int{9876, 19876}
				if targetRequests.Load()%2 == 1 {
					ports = []int{19876, 9876}
				}
				for _, port := range ports {
					r, e := client.Get(fmt.Sprintf("http://127.0.0.1:%d/", port))
					valid := false
					if e == nil {
						b, err := io.ReadAll(r.Body)
						r.Body.Close()
						valid = err == nil && r.StatusCode == 200 && len(b) > 1000 && bytes.Contains(bytes.ToLower(b), []byte("ddns"))
					}
					d.mu.Lock()
					if !valid && len(d.backgroundErrors) < 16 {
						d.backgroundErrors = append(d.backgroundErrors, fmt.Sprintf("port=%d stage=%s error=%v", port, stage, e))
					}
					if port == 9876 {
						d.pages[stage]++
						targetRequests.Add(1)
					} else {
						d.controlPages[stage]++
					}
					d.mu.Unlock()
				}
			}
		}
	}()
	current := "warmup"
	d.sample(current, "initial")
	nextSample := d.started.Add(15 * time.Second)
	nextIntegrity := d.started
	nextFancy := d.started
	nextStatus := d.started
	for time.Since(d.started) < time.Duration(seconds)*time.Second {
		stage, _ := dStage(time.Since(d.started), short)
		if stage != current {
			d.sample(current, "phase_end")
			current = stage
			d.stage.Store(stage)
			dEmit("DIAG_MEMORY_STAGE", map[string]any{"elapsed_seconds": time.Since(d.started).Seconds(), "stage": stage})
		}
		if time.Now().After(nextSample) {
			d.sample(current, "periodic")
			nextSample = time.Now().Add(15 * time.Second)
		}
		if time.Now().After(nextIntegrity) {
			d.integrity()
			d.c.proxyOK()
			nextIntegrity = time.Now().Add(30 * time.Second)
		}
		if time.Now().After(nextStatus) {
			d.c.x.query("status")
			nextStatus = time.Now().Add(5 * time.Second)
		}
		if time.Now().After(nextFancy) {
			d.request("native_cycles", "ss_status.sh", 0)
			nextFancy = time.Now().Add(30 * time.Second)
		}
		time.Sleep(100 * time.Millisecond)
	}
	d.stage.Store("stopped")
	cancel()
	<-done
	last := d.sample(current, "final_idle_end")
	d.integrity()
	log, _ := os.ReadFile("/tmp/diag-ddns-runtime.log")
	runtimeLines := []string{}
	for _, l := range strings.Split(string(log), "\n") {
		if strings.HasPrefix(l, "gc ") || strings.HasPrefix(l, "scav ") || strings.HasPrefix(l, "pacer:") {
			runtimeLines = append(runtimeLines, l)
		}
	}
	return map[string]any{"requested_memory_seconds": seconds, "duration_seconds": time.Since(d.started).Seconds(), "memory_pid": d.target, "same_memory_pid": pid("ddnsgo") == d.target, "process_start_ticks": d.startTicks, "target_page_requests": targetRequests.Load(), "page_counts": d.pages, "background_load_errors": d.backgroundErrors, "runtime_lines": runtimeLines, "no_thp_control_runtime_lines": dRuntimeLines("/tmp/diag-ddns-no-thp.log"), "no_thp_control_same_pid": dProc(d.control)["start_ticks"] == d.controlStartTicks, "no_thp_control_pid": d.control, "no_thp_control_page_counts": d.controlPages, "no_thp_control_binary_matches": bytes.Equal(nrRead("/koolshare/bin/ddnsgo"), nrRead("/koolshare/bin/diag-ddnsgo-control")), "last_sample": last, "pids": d.pids}
}
func (c *coexistRun) diagnostics() {
	d := &diagnostic{c: c}
	short := os.Getenv("DIAG_MODE") == "preflight"
	defer func() {
		if p := recover(); p != nil {
			b, _ := exec.Command("/bin/ps", "w").CombinedOutput()
			fmt.Printf("DIAGNOSTIC_LIVE_FAILURE %v\n%s\n", p, b)
			for _, name := range []string{"/tmp/diag-ddns-runtime.log", "/tmp/coexist-tls-errors.log", nrOutput("diag-mode-2-server.log")} {
				if b, e := os.ReadFile(name); e == nil {
					if len(b) > 12000 {
						b = b[len(b)-12000:]
					}
					fmt.Printf("DIAGNOSTIC_LIVE_LOG %s\n%s\n", name, b)
				}
			}
			panic(p)
		}
	}()
	d.installTracing()
	defer func() { os.WriteFile("/koolshare/scripts/ss_status.sh", d.statusOriginal, 0755) }()
	d.runtimeStart()
	defer func() { os.WriteFile("/koolshare/perp/ddnsgo/rc.main", d.runtimeOriginal, 0755) }()
	d.controlStart()
	defer func() { d.controlCmd.Process.Kill(); d.controlCmd.Wait(); d.controlLog.Close() }()
	d.calibrate(short)
	heap := d.heapProbe()
	dEmit("DIAG_HEAP_PROBE", heap)
	result := d.memoryCycles(short)
	nrMust(os.WriteFile("/koolshare/perp/ddnsgo/rc.main", d.runtimeOriginal, 0755))
	nrMust(os.WriteFile("/koolshare/scripts/ss_status.sh", d.statusOriginal, 0755))
	result["runtime_script_restored"] = bytes.Equal(d.runtimeOriginal, nrRead("/koolshare/perp/ddnsgo/rc.main")) && bytes.Equal(d.statusOriginal, nrRead("/koolshare/scripts/ss_status.sh"))
	result["data_preserved"] = true
	result["latency_cases"] = d.cases
	result["samples"] = d.samples
	result["phase_boundaries"] = d.boundaries
	result["heap_profile_probe"] = heap
	result["normal_status_queries"] = c.x.queries
	result["fancyss_global_proxy_enabled"] = false
	// Retained diagnostics contain no user configuration, keys or response bodies.
	result["binary_sha256"] = fmt.Sprintf("%x", sha256.Sum256(nrRead("/koolshare/bin/ddnsgo")))
	stages := map[string]string{}
	files, e := filepath.Glob("/tmp/diag-fancy/*.log")
	nrMust(e)
	for _, p := range files {
		b, e := os.ReadFile(p)
		nrMust(e)
		stages[strings.TrimSuffix(filepath.Base(p), ".log")] = string(b)
	}
	result["completed_script_stages"] = stages
	result["metadata_log_files"] = lenMust(filepath.Glob("/tmp/diag-fancy/*.log"))
	dEmit("DIAGNOSTIC_RESULT", result)
}
func lenMust(paths []string, e error) int { nrMust(e); return len(paths) }

func cloneTimes(in map[string]float64) map[string]float64 {
	out := make(map[string]float64, len(in))
	for k, v := range in {
		out[k] = v
	}
	return out
}

func dRollup(p int) map[string]int {
	out := map[string]int{}
	b, e := os.ReadFile(fmt.Sprintf("/proc/%d/smaps_rollup", p))
	if e != nil {
		return out
	}
	for _, l := range strings.Split(string(b), "\n") {
		f := strings.Fields(l)
		if len(f) == 3 && f[2] == "kB" {
			n, e := strconv.Atoi(f[1])
			if e == nil {
				out[strings.TrimSuffix(f[0], ":")] = n
			}
		}
	}
	return out
}
func dRuntimeLines(p string) []string {
	b := nrRead(p)
	out := []string{}
	for _, l := range strings.Split(string(b), "\n") {
		if strings.HasPrefix(l, "gc ") || strings.HasPrefix(l, "scav ") || strings.HasPrefix(l, "pacer:") {
			out = append(out, l)
		}
	}
	return out
}
func (d *diagnostic) controlStart() {
	original := nrRead("/koolshare/bin/ddnsgo")
	nrMust(os.WriteFile("/koolshare/bin/diag-ddnsgo-control", original, 0755))
	nrMust(os.WriteFile("/tmp/diag-ddns-control.yaml", d.c.x.config, 0600))
	f, e := os.Create("/tmp/diag-ddns-no-thp.log")
	nrMust(e)
	d.controlLog = f
	cmd := exec.CommandContext(d.c.x.ctx, "/work/build/diag-thp-exec", "/koolshare/bin/diag-ddnsgo-control", "-l", "127.0.0.1:19876", "-f", "300", "-cacheTimes", "5", "-c", "/tmp/diag-ddns-control.yaml")
	cmd.Env = append(os.Environ(), "GODEBUG=gctrace=1,scavtrace=1,gcpacertrace=1")
	cmd.Stdout = f
	cmd.Stderr = f
	nrMust(cmd.Start())
	d.controlCmd = cmd
	d.control = cmd.Process.Pid
	mWait("noTHP DDNS listener", func() bool {
		c, e := net.DialTimeout("tcp4", "127.0.0.1:19876", 100*time.Millisecond)
		if e == nil {
			c.Close()
			return true
		}
		return false
	})
	d.controlStartTicks = dProc(d.control)["start_ticks"].(string)
	if dProc(d.control)["THP_enabled"] != "0" {
		panic("control THP policy not disabled")
	}
	dEmit("DIAG_NO_THP_CONTROL", map[string]any{"process": dProc(d.control), "binary_sha256": fmt.Sprintf("%x", sha256.Sum256(original)), "configuration_seed_sha256": fmt.Sprintf("%x", sha256.Sum256(d.c.x.config)), "limits": "Identical executable bytes and config seed; owned different basename/port/config path to avoid primary pidof collision; process-scoped prctl only, no global kernel setting"})
}
func (d *diagnostic) controlSample() map[string]any {
	proc := dProc(d.control)
	if proc["start_ticks"] != d.controlStartTicks || proc["THP_enabled"] != "0" {
		panic("control identity/THP changed")
	}
	total, dirty, anon, huge, swap := 0, 0, 0, 0, 0
	groups := map[string]map[string]int{}
	for _, m := range smaps(d.control) {
		total += m.RSS
		dirty += m.PrivateDirty
		anon += m.Anonymous
		huge += m.Huge
		swap += m.Swap
		name := m.Path
		if name == "" {
			name = "anonymous"
		}
		key := m.Perm + " " + name
		if groups[key] == nil {
			groups[key] = map[string]int{}
		}
		g := groups[key]
		g["rss_kib"] += m.RSS
		g["private_dirty_kib"] += m.PrivateDirty
		g["anonymous_kib"] += m.Anonymous
		g["anon_huge_pages_kib"] += m.Huge
		g["virtual_kib"] += int((m.End - m.Start) / 1024)
	}
	if huge != 0 {
		panic("NoTHP control acquired huge pages")
	}
	row := map[string]any{"process": proc, "smaps_rss_kib": total, "private_dirty_kib": dirty, "anonymous_kib": anon, "anon_huge_pages_kib": huge, "swap_kib": swap, "maps": groups, "rollup": dRollup(d.control)}
	lines := dRuntimeLines("/tmp/diag-ddns-no-thp.log")
	gc, scav := 0, 0
	for _, l := range lines {
		if strings.HasPrefix(l, "gc ") {
			gc++
			row["latest_gc"] = l
		}
		if strings.HasPrefix(l, "scav ") {
			scav++
			row["latest_scav"] = l
		}
	}
	row["gc_count"] = gc
	row["scav_count"] = scav
	return row
}
