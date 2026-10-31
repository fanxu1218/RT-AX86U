package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/md5"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

type soak struct {
	ctx                           context.Context
	s                             *nrServer
	u                             *onlineUU
	repo                          *onlineRepo
	id, queries, events, launches int
	version, db                   string
	config, cert                  []byte
	sentinels                     map[string][]byte
	latencies                     []float64
	counts                        map[string]int
	samples                       []map[string]any
	started                       time.Time
}

func (x *soak) payload(action string) []byte {
	x.id++
	b, e := json.Marshal(map[string]any{"id": x.id, "method": "ddnsgo_config.sh", "params": []string{action}, "fields": ""})
	nrMust(e)
	return b
}
func (x *soak) request(action string) (int, []byte, error) {
	b := x.payload(action)
	req, e := http.NewRequest("POST", "https://192.168.77.1:34443/_api/", bytes.NewReader(b))
	if e != nil {
		return 0, nil, e
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 native-lifecycle-fixture")
	req.Header.Set("Origin", "https://192.168.77.1:34443")
	req.Header.Set("Content-Type", "application/json")
	req.AddCookie(&http.Cookie{Name: "asus_s_token", Value: x.s.token})
	res, e := x.s.client.Do(req)
	if e != nil {
		return 0, nil, e
	}
	defer res.Body.Close()
	body, e := io.ReadAll(res.Body)
	return res.StatusCode, body, e
}
func (x *soak) query(action string) {
	at := time.Now()
	code, b, e := x.request(action)
	var r struct {
		Result any `json:"result"`
	}
	parse := json.Unmarshal(b, &r)
	v := fmt.Sprint(r.Result)
	valid := e == nil && parse == nil && code == 200 && ((action == "status" && strings.Contains(v, "进程运行正常")) || (action == "version" && strings.TrimSpace(v) == x.version))
	if !valid {
		panic(fmt.Sprintf("unplanned query failure id=%d action=%s code=%d error=%v body=%q", x.id, action, code, e, b))
	}
	x.queries++
	x.counts[action]++
	x.latencies = append(x.latencies, float64(time.Since(at).Microseconds())/1000)
}
func (x *soak) window(name string, transient bool) func() string {
	stop := make(chan struct{})
	done := make(chan string, 1)
	go func() {
		n, unavailable := 0, 0
		for {
			select {
			case <-stop:
				done <- fmt.Sprintf("%s_reads=%d unavailable=%d", name, n, unavailable)
				return
			default:
			}
			code, b, e := x.request("status")
			var r struct {
				Result any `json:"result"`
			}
			parse := json.Unmarshal(b, &r)
			running := e == nil && code == 200 && parse == nil && strings.Contains(fmt.Sprint(r.Result), "进程运行正常")
			n++
			if !running {
				unavailable++
				fmt.Printf("SOAK_PLANNED_WINDOW name=%s id=%d code=%d error=%v bytes=%d\n", name, x.id, code, e, len(b))
			}
			if (!transient && !running) || code == 401 || code == 403 {
				done <- fmt.Sprintf("UNEXPECTED %s id=%d code=%d error=%v body=%q", name, x.id, code, e, b)
				return
			}
			time.Sleep(100 * time.Millisecond)
		}
	}()
	return func() string {
		close(stop)
		s := <-done
		if strings.HasPrefix(s, "UNEXPECTED") {
			panic(s)
		}
		return s
	}
}
func finishPending(conn *tls.Conn) (int, []byte, error) {
	res, e := http.ReadResponse(bufio.NewReader(conn), nil)
	if e != nil {
		return 0, nil, e
	}
	defer res.Body.Close()
	b, e := io.ReadAll(res.Body)
	return res.StatusCode, b, e
}
func pid(name string) int {
	out := strings.Fields(nrCommand("/bin/sh", "-c", "pidof "+name+" || true"))
	if len(out) != 1 {
		panic(fmt.Sprintf("expected one %s: %v", name, out))
	}
	n, e := strconv.Atoi(out[0])
	nrMust(e)
	return n
}
func rss(p int) int {
	b, e := os.ReadFile(fmt.Sprintf("/proc/%d/status", p))
	if e != nil {
		return -1
	}
	for _, l := range strings.Split(string(b), "\n") {
		if strings.HasPrefix(l, "VmRSS:") {
			v, _ := strconv.Atoi(strings.Fields(l)[1])
			return v
		}
	}
	return -1
}
func fds(p int) int {
	f, e := os.ReadDir(fmt.Sprintf("/proc/%d/fd", p))
	if e != nil {
		return -1
	}
	return len(f)
}
func (x *soak) sample() {
	process := map[string]int{"httpd": x.s.cmd.Process.Pid, "httpdb": pid("httpdb"), "skipd": pid("skipd"), "ddnsgo": pid("ddnsgo"), "uu": x.u.pid}
	row := map[string]any{"elapsed_seconds": int(time.Since(x.started).Seconds()), "queries": x.queries, "events": x.events}
	for name, p := range process {
		row[name] = map[string]int{"pid": p, "rss_kib": rss(p), "fds": fds(p)}
	}
	x.samples = append(x.samples, row)
	b, _ := json.Marshal(row)
	fmt.Printf("SOAK_SAMPLE %s\n", b)
}
func (x *soak) data() {
	if !bytes.Equal(x.config, nrRead("/koolshare/configs/ddnsgo/default.yaml")) || !bytes.Equal(x.cert, nrRead("/jffs/cert.tgz")) {
		panic("config or certificate archive changed")
	}
	if nrCommand("/usr/bin/dbus", "list", "ddnsgo_") != x.db {
		panic("plugin records changed")
	}
	for p, b := range x.sentinels {
		if !bytes.Equal(b, nrRead(p)) {
			panic("UU data changed: " + p)
		}
	}
	coUUAlive(x.u.pid)
	if x.u.calls.Load() != 1 || x.u.downloads.Load() != 1 || strings.Count(string(nrRead("/tmp/owned-uu-launches")), "start\n") != x.launches {
		panic("unexpected UU restart/download")
	}
	coPrivateDenied()
	coUUPage(x.s)
	res, e := (&http.Client{Timeout: 2 * time.Second}).Get("http://127.0.0.1:9876/")
	nrMust(e)
	defer res.Body.Close()
	b, e := io.ReadAll(res.Body)
	nrMust(e)
	if res.StatusCode != 200 || !strings.Contains(strings.ToLower(string(b)), "ddns") {
		panic("DDNS local page unavailable")
	}
}
func (x *soak) waitDDNS() {
	for i := 0; i < 150; i++ {
		b, _ := os.ReadFile("/tmp/upload/ddnsgo_log.txt")
		if bytes.Contains(b, []byte("DD01N05S")) {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	panic("DDNS restart did not finish")
}
func (x *soak) startDDNS(restart bool) {
	t := &onlineTest{s: x.s, id: x.id}
	enable := "1"
	if restart {
		enable = "2"
	}
	nrMust(os.WriteFile("/tmp/upload/ddnsgo_log.txt", nil, 0600))
	t.rpc("ddnsgo_config.sh", "web_submit", map[string]string{"ddnsgo_enable": enable, "ddnsgo_watchdog": "1", "ddnsgo_publicswitch": "0", "ddnsgo_localcheck": "300", "ddnsgo_wancheck": "5", "ddnsgo_port": "9876", "ddnsgo_skipverify": "0"})
	x.id = t.id
	var finish func() string
	if restart {
		finish = x.window("ddns_restart", true)
	}
	x.waitDDNS()
	if finish != nil {
		fmt.Println("SOAK_WINDOW_RESULT", finish())
	}
}
func waitGone(p int) {
	for i := 0; i < 100; i++ {
		b, e := os.ReadFile(fmt.Sprintf("/proc/%d/stat", p))
		if os.IsNotExist(e) || strings.Contains(string(b), ") Z ") {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	panic("owned worker did not stop")
}
func (x *soak) pending() (net.Conn, *tls.Conn) {
	for _, p := range []string{"/tmp/https-recv-ready", "/tmp/https-fault-mode"} {
		os.Remove(p)
	}
	nrMust(os.WriteFile("/tmp/https-fault-mode", []byte("signal"), 0600))
	raw, e := net.DialTimeout("tcp4", "192.168.77.1:34443", 3*time.Second)
	nrMust(e)
	nrMust(raw.SetDeadline(time.Now().Add(12 * time.Second)))
	cfg := x.s.client.Transport.(*http.Transport).TLSClientConfig.Clone()
	cfg.ServerName = "192.168.77.1"
	conn := tls.Client(raw, cfg)
	nrMust(conn.Handshake())
	b := x.payload("version")
	head := fmt.Sprintf("POST /_api/ HTTP/1.1\r\nHost: 192.168.77.1:34443\r\nUser-Agent: Mozilla/5.0 native-lifecycle-fixture\r\nOrigin: https://192.168.77.1:34443\r\nContent-Type: application/json\r\nCookie: asus_s_token=%s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n", x.s.token, len(b))
	_, e = conn.Write(append([]byte(head), b...))
	nrMust(e)
	for i := 0; i < 1000; i++ {
		if _, e := os.Stat("/tmp/https-recv-ready"); e == nil {
			return raw, conn
		}
		time.Sleep(5 * time.Millisecond)
	}
	panic("backend response header gate not reached")
}
func (x *soak) event(kind string) {
	at := time.Now()
	x.data()
	oldUU := x.u.pid
	oldDDNS := pid("ddnsgo")
	details := ""
	fmt.Printf("SOAK_EVENT_BEGIN index=%d kind=%s\n", x.events+1, kind)
	switch kind {
	case "abort":
		raw, conn := x.pending()
		nrMust(raw.(*net.TCPConn).SetLinger(0))
		raw.Close()
		conn.Close()
		details = "client_tcp_rst_while_backend_body_pending"
	case "partial":
		raw, e := net.DialTimeout("tcp4", "192.168.77.1:34443", 3*time.Second)
		nrMust(e)
		cfg := x.s.client.Transport.(*http.Transport).TLSClientConfig.Clone()
		cfg.ServerName = "192.168.77.1"
		conn := tls.Client(raw, cfg)
		nrMust(conn.Handshake())
		b := x.payload("version")
		head := fmt.Sprintf("POST /_api/ HTTP/1.1\r\nHost: 192.168.77.1:34443\r\nUser-Agent: Mozilla/5.0 native-lifecycle-fixture\r\nOrigin: https://192.168.77.1:34443\r\nCookie: asus_s_token=%s\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n", x.s.token, len(b))
		_, e = conn.Write(append([]byte(head), b[:len(b)/2]...))
		nrMust(e)
		raw.(*net.TCPConn).SetLinger(0)
		raw.Close()
		conn.Close()
		details = "client_rst_with_incomplete_request_body"
	case "backend":
		raw, conn := x.pending()
		old := pid("httpdb")
		nrMust(syscall.Kill(old, syscall.SIGKILL))
		code, b, e := finishPending(conn)
		details = fmt.Sprintf("backend_killed=%d pending_http_status=%d pending_body_bytes=%d expected_read_error=%v", old, code, len(b), e)
		if e == nil {
			panic("backend kill did not interrupt pending response")
		}
		raw.Close()
		conn.Close()
		coBackendReady()
		if pid("httpdb") == old {
			panic("backend did not respawn")
		}
	case "center":
		finish := x.window("center_restart", true)
		nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "restart")
		coBackendReady()
		details = "production_bootstrap_restart " + finish()
	case "ddns":
		x.startDDNS(true)
		if pid("ddnsgo") == oldDDNS {
			panic("DDNS restart reused PID")
		}
		details = "one_original_plugin_restart_rpc"
	case "uu":
		finish := x.window("uu_restart", false)
		x.u.close()
		waitGone(oldUU)
		for _, p := range []string{"/tmp/native-ntp-idle", "/tmp/native-ntp-synced", "/tmp/owned-uu-worker.pid"} {
			os.Remove(p)
		}
		x.u = onlineUUStart(x.ctx)
		x.launches++
		if x.u.pid == oldUU {
			panic("UU restart reused PID")
		}
		details = "one_fresh_native_ntp_uu_control_start " + finish()
	case "tls":
		fp := x.s.fingerprint
		backend := pid("httpdb")
		x.s.stop()
		x.s = nrStart(x.ctx, "soak-https-restart", true)
		if x.s.fingerprint != fp || pid("httpdb") != backend {
			panic("HTTPS restart changed certificate or backend")
		}
		x.s.login()
		details = "native_https_restart_and_new_login"
	case "signals":
		raw, conn := x.pending()
		for i := 0; i < 3; i++ {
			nrMust(x.s.cmd.Process.Signal(syscall.SIGALRM))
			time.Sleep(20 * time.Millisecond)
		}
		code, b, e := finishPending(conn)
		nrMust(e)
		var r struct {
			Result string `json:"result"`
		}
		nrMust(json.Unmarshal(b, &r))
		if code != 200 || strings.TrimSpace(r.Result) != x.version {
			panic("signal query lost version")
		}
		conn.Close()
		raw.Close()
		details = "three_sigalrm_during_pending_body"
	default:
		panic("unknown event")
	}
	os.Remove("/tmp/https-fault-mode")
	if kind != "uu" && x.u.pid != oldUU {
		panic("unplanned UU PID change")
	}
	for i := 0; i < 3; i++ {
		x.query([]string{"status", "version"}[i%2])
	}
	x.data()
	x.events++
	x.counts[kind]++
	fmt.Printf("SOAK_EVENT index=%d kind=%s seconds=%.3f details=%s\n", x.events, kind, time.Since(at).Seconds(), details)
}
func main() {
	x := &soak{id: 91000, counts: map[string]int{}, sentinels: map[string][]byte{}}
	defer func() {
		if e := recover(); e != nil {
			fmt.Println("SOAK_FAILURE", e)
			for _, p := range []string{"/tmp/https-relay-trace", "/tmp/.localmod/bootstrap.log", "/tmp/.localmod/skipd.log", "/var/log/perpd/current", nrOutput("soak-server.log"), nrOutput("soak-https-restart-server.log")} {
				if b, e := os.ReadFile(p); e == nil {
					if len(b) > 65536 {
						b = b[len(b)-65536:]
					}
					fmt.Printf("DIAGNOSTIC %s\n%s\n", p, b)
				}
			}
			fmt.Println(nrCommand("/bin/ps", "w"))
			panic(e)
		}
	}()
	duration := 30 * time.Minute
	period := 90 * time.Second
	if len(os.Args) > 1 && os.Args[1] == "soak-smoke" {
		duration = 100 * time.Second
		period = 8 * time.Second
	}
	ctx, cancel := context.WithTimeout(context.Background(), duration+4*time.Minute)
	defer cancel()
	x.ctx = ctx
	nrMust(os.WriteFile("/tmp/https-trace-quiet", []byte("1"), 0600))
	x.repo = onlineRepository()
	defer x.repo.close()
	var m struct {
		Packages []struct {
			Module, Phase, Path string
			Version             string `json:"catalog_version"`
			SHA                 string `json:"sha256"`
			MD5                 string `json:"md5"`
		}
	}
	nrMust(json.Unmarshal(nrRead("/work/build/real_plugin_inputs.json"), &m))
	for _, p := range m.Packages {
		if p.Module != "ddnsgo" || p.Phase != "current" {
			continue
		}
		b := nrRead("/work/" + p.Path)
		s := sha256.Sum256(b)
		d := md5.Sum(b)
		if hex.EncodeToString(s[:]) != p.SHA || hex.EncodeToString(d[:]) != p.MD5 {
			panic("package changed")
		}
		x.repo.apps["ddnsgo-current"] = onlineApp{p.Module, p.Module, p.Version, p.MD5, "ddnsgo/current.tar.gz"}
		x.repo.blobs["/ddnsgo/current.tar.gz"] = b
	}
	x.s = nrStart(ctx, "soak", true)
	defer func() { x.s.stop() }()
	x.s.login()
	coBackendReady()
	x.u = onlineUUStart(ctx)
	x.launches = 1
	defer func() { x.u.close() }()
	t := &onlineTest{s: x.s, repo: x.repo, uu: x.u, id: x.id, sentinels: x.sentinels, archive: nrRead("/jffs/cert.tgz")}
	for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-cache/uu.tar.gz.md5", "/jffs/uu-state/user.dat", "/tmp/uu.tar.gz"} {
		nrMust(os.MkdirAll(filepath.Dir(p), 0700))
		b := []byte("soak-synthetic-data:" + p)
		nrMust(os.WriteFile(p, b, 0600))
		x.sentinels[p] = b
	}
	t.operation("ddnsgo-current", "", true)
	x.id = t.id
	x.startDDNS(false)
	x.version = strings.TrimSpace(nrCommand("/koolshare/bin/ddnsgo", "-v"))
	x.db = nrCommand("/usr/bin/dbus", "list", "ddnsgo_")
	x.config = nrRead("/koolshare/configs/ddnsgo/default.yaml")
	x.cert = nrRead("/jffs/cert.tgz")
	x.data()
	x.started = time.Now()
	x.sample()
	deadline := x.started.Add(duration)
	nextEvent := x.started.Add(period)
	nextSample := x.started.Add(20 * time.Second)
	kinds := []string{"abort", "partial", "backend", "center", "ddns", "uu", "tls", "signals"}
	for time.Now().Before(deadline) {
		tick := time.Now()
		if !tick.Before(nextEvent) {
			x.event(kinds[x.events%len(kinds)])
			nextEvent = nextEvent.Add(period)
		}
		x.query([]string{"status", "version"}[x.queries%2])
		if time.Now().After(nextSample) {
			x.data()
			x.sample()
			nextSample = nextSample.Add(20 * time.Second)
		}
		if delay := time.Until(tick.Add(time.Second)); delay > 0 {
			time.Sleep(delay)
		}
	}
	x.data()
	for i := 0; i < 5; i++ {
		x.query([]string{"status", "version"}[i%2])
	}
	x.sample()
	sort.Float64s(x.latencies)
	report := map[string]any{"duration_seconds": time.Since(x.started).Seconds(), "started_utc": x.started.UTC().Format(time.RFC3339), "finished_utc": time.Now().UTC().Format(time.RFC3339), "requested_duration_seconds": int(duration.Seconds()), "healthy_queries": x.queries, "unplanned_query_failures": 0, "counts": x.counts, "events": x.events, "uu_launches": x.launches, "latency_ms": map[string]float64{"p50": x.latencies[len(x.latencies)/2], "p95": x.latencies[len(x.latencies)*95/100], "max": x.latencies[len(x.latencies)-1]}, "samples": x.samples, "data_preserved": true, "tls_archive_preserved": true, "private_api_denied": true}
	b, e := json.Marshal(report)
	nrMust(e)
	fmt.Printf("SOAK_RESULT %s\n", b)
	fmt.Println("PASS continuous_queries_restarts_and_disconnects_preserve_data_and_uu")
}
