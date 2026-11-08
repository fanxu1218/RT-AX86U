package main

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptrace"
	"os"
	"os/exec"
	"strings"
	"sync"
	"time"
)

func (c *coexistRun) fancyProbe() {
	// Test-owned copy only: preserve exact executable text except metadata writes.
	path := "/koolshare/scripts/ss_status.sh"
	original := string(nrRead(path))
	mark := func(label string) string {
		return "{ read uptime rest < /proc/uptime; printf '%s pid=%s stage=" + label + "\\n' \"$uptime\" \"$$\" >> /tmp/fancy-latency-stages; }\n"
	}
	traced := strings.Replace(original, "source /koolshare/scripts/ss_base.sh", mark("before_base")+"source /koolshare/scripts/ss_base.sh\n"+mark("after_base"), 1)
	traced = strings.Replace(traced, "\t\thttp_response \"${payload}\" >/dev/null 2>&1", "\t\t"+mark("before_callback")+"\t\thttp_response \"${payload}\" >/dev/null 2>&1\n\t\t"+mark("after_callback"), 1)
	if traced == original || !strings.Contains(traced, "stage=after_callback") {
		panic("status trace anchors")
	}
	nrMust(os.WriteFile(path, []byte(traced), 0755))
	rows := []map[string]any{}
	for i := 0; i < 24; i++ {
		limit := 10 * time.Second
		if i >= 12 {
			limit = 30 * time.Second
		}
		c.x.id++
		id := c.x.id
		body, _ := json.Marshal(map[string]any{"id": id, "method": "ss_status.sh", "params": []string{"1"}, "fields": ""})
		nrMust(os.WriteFile("/tmp/fancy-latency-stages", nil, 0600))
		req, e := http.NewRequest("POST", "https://192.168.77.1:34443/_api/", bytes.NewReader(body))
		nrMust(e)
		req.Header.Set("User-Agent", "Mozilla/5.0 native-lifecycle-fixture")
		req.Header.Set("Origin", "https://192.168.77.1:34443")
		req.Header.Set("Content-Type", "application/json")
		req.AddCookie(&http.Cookie{Name: "asus_s_token", Value: c.x.s.token})
		started := time.Now()
		trace := map[string]float64{}
		var mu sync.Mutex
		stamp := func(k string) { mu.Lock(); trace[k] = time.Since(started).Seconds(); mu.Unlock() }
		req = req.WithContext(httptrace.WithClientTrace(req.Context(), &httptrace.ClientTrace{TLSHandshakeDone: func(tls.ConnectionState, error) { stamp("tls_done") }, WroteRequest: func(httptrace.WroteRequestInfo) { stamp("request_written") }, GotFirstResponseByte: func() { stamp("first_response_byte") }}))
		done := make(chan struct{})
		snap := make(chan []string, 1)
		go func() {
			notes := []string{}
			for j := 0; j < 5; j++ {
				select {
				case <-done:
					snap <- notes
					return
				case <-time.After(2 * time.Second):
					b, _ := exec.Command("/bin/ps", "w").CombinedOutput()
					notes = append(notes, string(b))
				}
			}
			snap <- notes
		}()
		client := &http.Client{Transport: c.x.s.client.Transport, Timeout: limit, CheckRedirect: c.x.s.client.CheckRedirect}
		res, e := client.Do(req)
		code := 0
		valid := false
		n := 0
		if e == nil {
			code = res.StatusCode
			var b []byte
			b, e = io.ReadAll(res.Body)
			res.Body.Close()
			n = len(b)
			valid = e == nil && code == 200 && json.Valid(b)
		}
		elapsed := time.Since(started).Seconds()
		close(done)
		notes := <-snap
		// Observe late completion, never resend a timed-out request.
		if e != nil {
			time.Sleep(8 * time.Second)
		}
		b, _ := os.ReadFile("/tmp/fancy-latency-stages")
		mu.Lock()
		row := map[string]any{"index": i, "id": id, "timeout_seconds": limit.Seconds(), "elapsed_seconds": elapsed, "code": code, "valid": valid, "bytes": n, "error": fmt.Sprint(e), "timings": trace, "script_stages": string(b)}
		mu.Unlock()
		rows = append(rows, row)
		q, _ := json.Marshal(row)
		fmt.Printf("FANCY_LATENCY_CASE %s\n", q)
		if elapsed > 5 || e != nil {
			for _, note := range notes {
				fmt.Printf("FANCY_LATENCY_PROCESS_SNAPSHOT\n%s\n", note)
			}
		}
		c.core()
		c.data()
		c.vpn()
		c.proxyOK()
	}
	nrMust(os.WriteFile(path, []byte(original), 0755))
	b, _ := json.Marshal(map[string]any{"cases": rows, "data_preserved": true, "script_metadata_instrumentation_only": true, "query_replay": false})
	fmt.Printf("FANCY_LATENCY_RESULT %s\n", b)
}
