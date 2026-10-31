package main

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

func nrMust(e error) {
	if e != nil {
		panic(e)
	}
}
func nrRead(path string) []byte { b, e := os.ReadFile(path); nrMust(e); return b }
func nrOutput(name string) string {
	base := os.Getenv("LOCALMOD_TEST_OUTPUT")
	if base == "" {
		base = "/work/build"
	}
	return filepath.Join(base, name)
}
func nrQEMURoot() string {
	if root := os.Getenv("LOCALMOD_QEMU_ROOT"); root != "" {
		return root
	}
	return "/work/build/casefs/official_rootfs"
}
func nrHTTPTimeout() time.Duration {
	if raw := os.Getenv("LOCALMOD_HTTP_REQUEST_TIMEOUT"); raw != "" {
		value, e := time.ParseDuration(raw)
		nrMust(e)
		if value <= 0 || value > 30*time.Second {
			panic("invalid native HTTP timeout")
		}
		return value
	}
	return 2 * time.Second
}
func nrCommand(args ...string) string {
	b, e := exec.Command(args[0], args[1:]...).CombinedOutput()
	if e != nil {
		panic(fmt.Sprintf("%v: %v %s", args, e, b))
	}
	return string(b)
}

type nrServer struct {
	cmd         *exec.Cmd
	log         *os.File
	client      *http.Client
	fingerprint string
	token       string
}

func nrStart(ctx context.Context, name string, adapt bool) *nrServer {
	log, e := os.Create(nrOutput(name + "-server.log"))
	nrMust(e)
	preload := "/work/build/native_hw_fixture.so"
	if adapt {
		preload = "/work/build/httpd_bridge.so:" + preload
	}
	cmd := exec.CommandContext(ctx, "/usr/bin/qemu-arm", "-L", nrQEMURoot(), "-E", "LD_PRELOAD="+preload, "/usr/libexec/localmod/httpd", "-s", "-p", "34443")
	cmd.Dir = "/www"
	cmd.Stdout = log
	cmd.Stderr = log
	nrMust(cmd.Start())
	s := &nrServer{cmd: cmd, log: log}
	wait := 18 * time.Second
	if value := os.Getenv("LOCALMOD_TLS_START_TIMEOUT"); value != "" {
		wait, e = time.ParseDuration(value)
		nrMust(e)
		if wait <= 0 || wait > time.Minute {
			panic("invalid native TLS startup timeout")
		}
	}
	deadline := time.Now().Add(wait)
	for time.Now().Before(deadline) && ctx.Err() == nil {
		ca, _ := os.ReadFile("/etc/cacert.pem")
		cert, _ := os.ReadFile("/etc/cert.pem")
		roots := x509.NewCertPool()
		block, _ := pem.Decode(cert)
		if block != nil && roots.AppendCertsFromPEM(ca) {
			leaf, e := x509.ParseCertificate(block.Bytes)
			if e == nil {
				transport := &http.Transport{TLSClientConfig: &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12}, DisableKeepAlives: true}
				client := &http.Client{Transport: transport, Timeout: nrHTTPTimeout(), CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
				res, e := client.Get("https://192.168.77.1:34443/Main_Login.asp")
				if e == nil {
					body, err := io.ReadAll(res.Body)
					res.Body.Close()
					if err == nil && res.StatusCode == 200 && strings.Contains(string(body), "login_authorization") && res.TLS != nil && len(res.TLS.VerifiedChains) > 0 {
						sum := sha256.Sum256(leaf.Raw)
						s.fingerprint = hex.EncodeToString(sum[:])
						s.client = client
						return s
					}
				}
				transport.CloseIdleConnections()
			}
		}
		time.Sleep(60 * time.Millisecond)
	}
	s.stop()
	panic("native TLS did not initialize: " + string(nrRead(nrOutput(name+"-server.log"))))
}
func (s *nrServer) stop() {
	if s.cmd != nil {
		_ = s.cmd.Process.Kill()
		_ = s.cmd.Wait()
		s.log.Close()
		s.cmd = nil
	}
	if s.client != nil {
		s.client.CloseIdleConnections()
	}
}
func (s *nrServer) request(method, path, body string) (int, string) {
	req, e := http.NewRequest(method, "https://192.168.77.1:34443"+path, strings.NewReader(body))
	nrMust(e)
	req.Header.Set("User-Agent", "Mozilla/5.0 native-lifecycle-fixture")
	req.Header.Set("Origin", "https://192.168.77.1:34443")
	req.Header.Set("Referer", "https://192.168.77.1:34443/Main_Login.asp")
	if s.token != "" {
		req.AddCookie(&http.Cookie{Name: "asus_s_token", Value: s.token})
	}
	if body != "" {
		kind := "application/json"
		if path == "/login.cgi" {
			kind = "application/x-www-form-urlencoded"
		}
		req.Header.Set("Content-Type", kind)
	}
	res, e := s.client.Do(req)
	nrMust(e)
	b, e := io.ReadAll(res.Body)
	res.Body.Close()

	if e != nil {
		panic(fmt.Sprintf("native response %s %s status=%d length=%d received=%d body=%q: %v", method, path, res.StatusCode, res.ContentLength, len(b), b, e))
	}
	for _, c := range res.Cookies() {
		if c.Name == "asus_s_token" {
			s.token = c.Value
		}
	}
	return res.StatusCode, string(b)
}
func (s *nrServer) login() {
	form := url.Values{"login_authorization": {base64.StdEncoding.EncodeToString([]byte("admin:local-test-password"))}, "next_page": {"index.asp"}}
	s.request("POST", "/login.cgi", form.Encode())
	if s.token == "" {
		panic("native login did not issue a TLS session")
	}
}
func nrResult(name string, checks []string, details map[string]any) {
	for _, c := range checks {
		fmt.Println("PASS", c)
	}
	report := map[string]any{"checks": checks, "details": details}
	b, e := json.MarshalIndent(report, "", "  ")
	nrMust(e)
	nrMust(os.WriteFile(nrOutput(name+"_result.json"), append(b, '\n'), 0644))
}
