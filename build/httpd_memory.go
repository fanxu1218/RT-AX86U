package main

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

func httpdCacheRun(x *soak) {
	nrMust(os.WriteFile("/tmp/ddnsgo-memory-runtime.log", nil, 0600))
	started := time.Now()
	samples := []map[string]any{}
	for _, phase := range []string{"fresh1", "resumed", "fresh2"} {
		nrMust(os.WriteFile("/tmp/httpd-tls-phase", []byte(phase), 0600))
		t := x.s.client.Transport.(*http.Transport).Clone()
		t.TLSClientConfig = t.TLSClientConfig.Clone()
		if phase == "resumed" {
			t.TLSClientConfig.ClientSessionCache = tls.NewLRUClientSessionCache(16)
		}
		client := &http.Client{Transport: t, Timeout: 10 * time.Second}
		for i := 0; i < 100; i++ {
			req, e := http.NewRequest("GET", "https://192.168.77.1:34443/index.asp", nil)
			nrMust(e)
			req.Header.Set("User-Agent", "Mozilla/5.0 native-lifecycle-fixture")
			req.AddCookie(&http.Cookie{Name: "asus_s_token", Value: x.s.token})
			r, e := client.Do(req)
			nrMust(e)
			b, e := io.ReadAll(r.Body)
			r.Body.Close()
			nrMust(e)
			if r.StatusCode != 200 || !bytes.Contains(b, []byte("RT-AX86U")) {
				panic(fmt.Sprintf("protected page %s %d bytes=%d", phase, r.StatusCode, len(b)))
			}
		}
		client.CloseIdleConnections()
		x.data()
		samples = append(samples, memSample(x.s.cmd.Process.Pid, started, map[string]any{"subject": "original_asus_httpd", "stage": phase}))
	}
	log := nrRead("/tmp/httpd-tls-cache.log")
	fmt.Printf("HTTPD_TLS_CACHE_TRACE_BEGIN\n%sHTTPD_TLS_CACHE_TRACE_END\n", log)
	x.data()
	b, e := json.Marshal(map[string]any{"samples": samples, "protected_page_queries": 300, "data_preserved": true, "uu_launches": x.launches, "duration_seconds": time.Since(started).Seconds()})
	nrMust(e)
	fmt.Printf("HTTPD_CACHE_RESULT %s\n", b)
}

func httpdMemoryRun(x *soak) {
	p := x.s.cmd.Process.Pid
	nrMust(os.WriteFile("/tmp/ddnsgo-memory-runtime.log", nil, 0600)) // empty: HTTPd is not a Go process.
	started := time.Now()
	samples := []map[string]any{}
	take := func(stage string) {
		if x.s.cmd.Process.Pid != p {
			panic("HTTPd restarted during memory observation")
		}
		s := memSample(p, started, map[string]any{"subject": "original_asus_httpd", "stage": stage})
		samples = append(samples, s)
	}
	take("initial")
	time.Sleep(20 * time.Second)
	x.data()
	take("warmup")
	var id atomic.Int32
	id.Store(98000)
	query := func() error {
		n := int(id.Add(1))
		action := []string{"status", "version"}[n%2]
		b, _ := json.Marshal(map[string]any{"id": n, "method": "ddnsgo_config.sh", "params": []string{action}, "fields": ""})
		req, e := http.NewRequest("POST", "https://192.168.77.1:34443/_api/", bytes.NewReader(b))
		if e != nil {
			return e
		}
		req.Header.Set("User-Agent", "Mozilla/5.0 native-lifecycle-fixture")
		req.Header.Set("Origin", "https://192.168.77.1:34443")
		req.Header.Set("Content-Type", "application/json")
		req.AddCookie(&http.Cookie{Name: "asus_s_token", Value: x.s.token})
		r, e := x.s.client.Do(req)
		if e != nil {
			return e
		}
		body, e := io.ReadAll(r.Body)
		r.Body.Close()
		if e != nil {
			return e
		}
		var v struct {
			Result any `json:"result"`
		}
		e = json.Unmarshal(body, &v)
		valid := r.StatusCode == 200 && e == nil && ((action == "status" && strings.Contains(fmt.Sprint(v.Result), "进程运行正常")) || (action == "version" && strings.TrimSpace(fmt.Sprint(v.Result)) == x.version))
		if !valid {
			return fmt.Errorf("parallel query %d status %d bytes %d invalid", n, r.StatusCode, len(body))
		}
		return nil
	}
	const rounds = 6
	const concurrency = 4
	const perWorker = 10
	for round := 1; round <= rounds; round++ {
		// A partial TLS/HTTP client disconnects before the subsequent batch.
		raw, e := net.DialTimeout("tcp4", "192.168.77.1:34443", 3*time.Second)
		nrMust(e)
		nrMust(raw.(*net.TCPConn).SetLinger(0))
		raw.Write([]byte{0x16, 0x03, 0x03})
		time.Sleep(100 * time.Millisecond)
		raw.Close()
		var wg sync.WaitGroup
		failures := make(chan error, concurrency*perWorker)
		for w := 0; w < concurrency; w++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				for i := 0; i < perWorker; i++ {
					if e := query(); e != nil {
						failures <- e
						return
					}
				}
			}()
		}
		wg.Wait()
		close(failures)
		for e := range failures {
			panic(e)
		}
		x.data()
		take(fmt.Sprintf("load%d", round))
		time.Sleep(30 * time.Second)
		take(fmt.Sprintf("idle%d", round))
		x.data()
		fmt.Printf("HTTPD_MEMORY_ROUND round=%d queries=%d elapsed_seconds=%.3f\n", round, concurrency*perWorker, time.Since(started).Seconds())
	}
	old := x.s.token
	x.s.request("GET", "/Logout.asp", "")
	code, _ := x.s.request("GET", "/_api/softcenter_", "")
	if code != 401 {
		panic("logged out HTTPd session still accepted")
	}
	x.s.token = ""
	x.s.login()
	if x.s.token == "" || x.s.token == old {
		panic("fresh login failed after parallel workload")
	}
	for i := 0; i < 3; i++ {
		if e := query(); e != nil {
			panic(e)
		}
	}
	x.data()
	take("final")
	b, e := json.Marshal(map[string]any{"samples": samples, "rounds": rounds, "concurrent_clients": concurrency, "healthy_queries": rounds*concurrency*perWorker + 3, "slow_disconnects": rounds, "idle_seconds_per_round": 30, "duration_seconds": time.Since(started).Seconds(), "same_httpd_pid": p, "data_preserved": true, "uu_launches": x.launches, "logout_and_relogin_verified": true})
	nrMust(e)
	fmt.Printf("HTTPD_MEMORY_RESULT %s\n", b)
}
