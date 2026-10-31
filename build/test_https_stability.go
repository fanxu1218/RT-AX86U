package main

import (
	"bytes"
	"context"
	"crypto/md5"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"syscall"
	"time"
)

func main() {
	defer func() {
		for _, p := range []string{"/tmp/https-relay-trace", "/tmp/.localmod/bootstrap.log", "/var/log/perpd/current", nrOutput("https-stability-server.log")} {
			if b, e := os.ReadFile(p); e == nil {
				fmt.Printf("DIAGNOSTIC %s\n%s\n", p, b)
			}
		}
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 220*time.Second)
	defer cancel()
	fmt.Print(nrCommand("/work/build/relay-idle-fixture"))
	repo := onlineRepository()
	defer repo.close()
	var manifest struct {
		Packages []struct {
			Module, Phase, Path string
			Version             string `json:"catalog_version"`
			SHA256              string `json:"sha256"`
			MD5                 string `json:"md5"`
		}
	}
	nrMust(json.Unmarshal(nrRead("/work/build/real_plugin_inputs.json"), &manifest))
	for _, p := range manifest.Packages {
		if p.Module != "ddnsgo" || p.Phase != "current" {
			continue
		}
		blob := nrRead("/work/" + p.Path)
		sum := sha256.Sum256(blob)
		m := md5.Sum(blob)
		if hex.EncodeToString(sum[:]) != p.SHA256 || hex.EncodeToString(m[:]) != p.MD5 {
			panic("package mismatch")
		}
		repo.apps["ddnsgo-current"] = onlineApp{p.Module, p.Module, p.Version, p.MD5, "ddnsgo/current.tar.gz"}
		repo.blobs["/ddnsgo/current.tar.gz"] = blob
	}
	s := nrStart(ctx, "https-stability", true)
	defer s.stop()
	s.login()
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	t := &onlineTest{s: s, repo: repo, uu: u, id: 87000, sentinels: map[string][]byte{}, archive: nrRead("/jffs/cert.tgz")}
	for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-cache/uu.tar.gz.md5", "/jffs/uu-state/user.dat", "/tmp/uu.tar.gz"} {
		nrMust(os.MkdirAll(p[:strings.LastIndex(p, "/")], 0700))
		b := []byte("https-coexist-synthetic:" + p)
		nrMust(os.WriteFile(p, b, 0600))
		t.sentinels[p] = b
	}
	t.operation("ddnsgo-current", "", true)
	t.rpc("ddnsgo_config.sh", "web_submit", map[string]string{"ddnsgo_enable": "1", "ddnsgo_watchdog": "0", "ddnsgo_publicswitch": "0", "ddnsgo_localcheck": "300", "ddnsgo_wancheck": "5", "ddnsgo_port": "9876", "ddnsgo_skipverify": "0"})
	for i := 0; i < 100; i++ {
		b, _ := os.ReadFile("/tmp/upload/ddnsgo_log.txt")
		if bytes.Contains(b, []byte("DD01N05S")) {
			break
		}
		time.Sleep(50 * time.Millisecond)
		if i == 99 {
			panic("DDNS-Go start incomplete")
		}
	}
	expectedVersion := strings.TrimSpace(nrCommand("/koolshare/bin/ddnsgo", "-v"))
	dbBefore := nrCommand("/usr/bin/dbus", "list", "ddnsgo_")
	alone := strings.HasSuffix(os.Args[1], "alone")
	if alone {
		u.close()
		stopped := false
		for i := 0; i < 100; i++ {
			b, e := os.ReadFile(fmt.Sprintf("/proc/%d/stat", u.pid))
			if os.IsNotExist(e) || strings.Contains(string(b), ") Z ") {
				stopped = true
				break
			}
			time.Sleep(20 * time.Millisecond)
		}
		if !stopped {
			panic("UU worker did not stop for isolated comparison")
		}
	}
	config := nrRead("/koolshare/configs/ddnsgo/default.yaml")
	cert := nrRead("/jffs/cert.tgz")
	failures := 0
	total := 68
	if alone {
		total = 36
	}
	for i := 0; i < total; i++ {
		action := "status"
		if i%2 != 0 {
			action = "version"
		}
		id := 88000 + i
		if alone {
			id += 1000
		}
		eintrBefore := 0
		mode := ""
		if i >= total-4 {
			mode = []string{"before", "after", "signal", "signal"}[i-(total-4)]
		}
		os.Remove("/tmp/https-recv-ready")
		os.Remove("/tmp/https-fault-mode")
		if mode != "" {
			nrMust(os.WriteFile("/tmp/https-fault-mode", []byte(mode), 0600))
		}
		signalDone := make(chan int, 1)
		if mode == "signal" {
			eintrBefore = strings.Count(string(nrRead("/tmp/https-relay-trace")), "returned=-1 errno=4")
			go func() {
				for k := 0; k < 500; k++ {
					if _, e := os.Stat("/tmp/https-recv-ready"); e == nil {
						time.Sleep(5 * time.Millisecond)
						for n := 0; n < 3; n++ {
							nrMust(s.cmd.Process.Signal(syscall.SIGALRM))
							time.Sleep(20 * time.Millisecond)
						}
						signalDone <- 3
						return
					}
					time.Sleep(5 * time.Millisecond)
				}
				signalDone <- 0
			}()
		}
		data, _ := json.Marshal(map[string]any{"id": id, "method": "ddnsgo_config.sh", "params": []string{action}, "fields": ""})
		req, _ := http.NewRequest("POST", "https://192.168.77.1:34443/_api/", bytes.NewReader(data))
		req.Header.Set("Origin", "https://192.168.77.1:34443")
		req.Header.Set("Referer", "https://192.168.77.1:34443/Module_ddnsgo.asp")
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("User-Agent", "Mozilla/5.0 native-lifecycle-fixture")
		req.AddCookie(&http.Cookie{Name: "asus_s_token", Value: s.token})
		started := time.Now()
		res, e := s.client.Do(req)
		body := []byte{}
		status := 0
		var hdr http.Header
		if e == nil {
			status = res.StatusCode
			hdr = res.Header
			body, e = io.ReadAll(res.Body)
			res.Body.Close()
		}
		var reply struct {
			Result any `json:"result"`
		}
		parse := json.Unmarshal(body, &reply)
		v := fmt.Sprint(reply.Result)
		ok := e == nil && status == 200 && parse == nil && ((action == "status" && strings.Contains(v, "进程运行正常")) || (action == "version" && strings.TrimSpace(v) == expectedVersion))
		fmt.Printf("READONLY_QUERY id=%d action=%s status=%d bytes=%d valid=%t duration=%s error=%v headers=%v\n", id, action, status, len(body), ok, time.Since(started), e, hdr)
		if !ok {
			failures++
			fmt.Printf("FAILED_BODY %q\n", body)
		}
		if mode == "signal" {
			sent := <-signalDone
			observed := strings.Count(string(nrRead("/tmp/https-relay-trace")), "returned=-1 errno=4") - eintrBefore
			fmt.Printf("FORCED_SIGNAL_QUERY id=%d signals=%d kernel_eintr=%d\n", id, sent, observed)
			if observed < 1 {
				panic("native recv was not interrupted by forced signal")
			}
			if sent != 3 {
				panic("signal gate not reached")
			}
		}
		os.Remove("/tmp/https-fault-mode")
		if !alone {
			coUUAlive(u.pid)
		}
		if i%8 == 0 {
			coUUPage(s)
		}
	}
	if !bytes.Equal(config, nrRead("/koolshare/configs/ddnsgo/default.yaml")) || !bytes.Equal(cert, nrRead("/jffs/cert.tgz")) {
		panic("read-only request changed persistent inputs")
	}
	if nrCommand("/usr/bin/dbus", "list", "ddnsgo_") != dbBefore {
		panic("read-only request changed plugin records")
	}
	for p, b := range t.sentinels {
		if !bytes.Equal(b, nrRead(p)) {
			panic("UU data changed: " + p)
		}
	}
	if !alone {
		coUUAlive(u.pid)
	}
	trace := string(nrRead("/tmp/https-relay-trace"))
	if strings.Count(trace, "INJECT_EINTR phase=") != 2 || strings.Count(trace, "returned=-1 errno=4") < 2 {
		panic("interrupt fault coverage missing")
	}
	fmt.Printf("HTTPS_STABILITY_RESULT phase=%s queries=%d failures=%d uu_running=%t uu_pid=%d uu_api_requests=%d uu_downloads=%d uu_launches=%s trace_eintr=%d\n", os.Args[1], total, failures, !alone, u.pid, u.calls.Load(), u.downloads.Load(), strings.TrimSpace(string(nrRead("/tmp/owned-uu-launches"))), strings.Count(trace, "returned=-1 errno=4"))
	fmt.Println("PASS same_connection_resume_complete_json_and_no_request_replay")
	fmt.Println("PASS original_login_tls_uu_page_and_private_plugin_state_preserved")
	fmt.Println("PASS interrupted_reads_keep_config_certificates_and_uu_data")
	if failures > 0 {
		panic("read-only HTTPS query failure")
	}
}
