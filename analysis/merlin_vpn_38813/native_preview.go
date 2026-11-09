package main

import (
	"context"
	"crypto/md5"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

func previewUUStart(ctx context.Context) *onlineUU {
	u := &onlineUU{}
	worker := []byte("#!/bin/sh\ntrap 'exit 0' TERM INT\nprintf '%s\\n' \"$$\" > /tmp/owned-uu-worker.pid\nwhile :;do printf tick >> /tmp/owned-uu-heartbeat;usleep 100000;done\n")
	nrMust(os.WriteFile("/tmp/owned-uu-worker.sh", worker, 0700))
	monitor := []byte("#!/bin/sh\n[ -z \"$LD_PRELOAD\" ] || exit 19\nprintf 'start\\n' >> /tmp/owned-uu-launches\n/bin/sh /tmp/owned-uu-worker.sh </dev/null >/tmp/owned-uu-worker.log 2>&1 &\n")
	sum := md5.Sum(monitor)
	u.server = &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/api":
			u.calls.Add(1)
			fmt.Fprintf(w, "http://uu.fixture.test:35000/monitor,%x", sum)
		case "/monitor":
			u.downloads.Add(1)
			w.Write(monitor)
		default:
			w.WriteHeader(404)
		}
	})}
	l, e := net.Listen("tcp4", "127.0.0.1:35000")
	nrMust(e)
	go u.server.Serve(l)
	u.log, e = os.Create(nrOutput("merlin-native-uu.log"))
	nrMust(e)
	u.cmd = exec.CommandContext(ctx, "/usr/bin/qemu-arm", "-0", "ntpd_synced", "-L", "/", "-E", "LD_PRELOAD=/work/build/native_hw_fixture.so:/work/build/native_uu_transport.so:/work/build/merlin38813-native-preview/clear_preload.so", "/sbin/rc", "step")
	u.cmd.Env = append(os.Environ(), "NATIVE_UU_CASE=1", "NATIVE_UU_TERRITORY=CN/01", "NATIVE_UU_MODE=1")
	u.cmd.Stdout, u.cmd.Stderr = u.log, u.log
	nrMust(u.cmd.Run())
	deadline := time.Now().Add(4 * time.Second)
	for time.Now().Before(deadline) {
		if b, e := os.ReadFile("/tmp/owned-uu-worker.pid"); e == nil && strings.TrimSpace(string(b)) != "" {
			u.pid, e = strconv.Atoi(strings.TrimSpace(string(b)))
			nrMust(e)
			break
		}
		time.Sleep(25 * time.Millisecond)
	}
	if u.pid == 0 {
		panic("native Merlin UU worker not started: " + string(nrRead(u.log.Name())))
	}
	coUUAlive(u.pid)
	return u
}

func previewForm(s *nrServer, fields url.Values) (int, string) {
	r, e := http.NewRequest("POST", "https://192.168.77.1:34443/applyapp.cgi", strings.NewReader(fields.Encode()))
	nrMust(e)
	// Native sessions bind the client identity used by nrServer.login().
	r.Header.Set("User-Agent", "Mozilla/5.0 native-lifecycle-fixture")
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Origin", "https://192.168.77.1:34443")
	r.Header.Set("Referer", "https://192.168.77.1:34443/Advanced_OpenVPNClient_Content.asp")
	if s.token != "" {
		r.AddCookie(&http.Cookie{Name: "asus_s_token", Value: s.token})
	}
	res, e := s.client.Do(r)
	nrMust(e)
	b, e := io.ReadAll(res.Body)
	res.Body.Close()
	nrMust(e)
	return res.StatusCode, string(b)
}

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 230*time.Second)
	defer cancel()
	checks := []string{}
	record := func(s string) { checks = append(checks, s); fmt.Println("PASS", s) }
	repo := onlineRepository()
	defer repo.close()
	u := previewUUStart(ctx)
	defer u.close()
	record("native_merlin_ntpd_callback_download_checksum_owned_uu_worker")
	s := nrStart(ctx, "merlin-native-preview", true)
	defer s.stop()
	code, body := s.request("GET", "/_api/softcenter_", "")
	if code == 200 && strings.Contains(body, "softcenter_version") {
		panic("unauthenticated center data")
	}
	fields := url.Values{"action_mode": {"apply"}, "vpn_client1_desc": {"owned-preview-profile"}}
	previewForm(s, fields)
	if strings.TrimSpace(nrCommand("/bin/nvram", "get", "vpn_client1_desc")) == "owned-preview-profile" {
		panic("unauthenticated VPN write")
	}
	record("native_authentication_denies_center_query_and_vpn_write")
	s.login()
	record("native_merlin_https_certificate_and_login")
	pages := map[string]string{
		"Advanced_OpenVPNClient_Content.asp": "vpn_client_custom3",
		"Advanced_VPN_OpenVPN.asp":           "vpn_server",
		"Advanced_VPNDirector.asp":           "vpndirector",
		"DNSDirector.asp":                    "dnsfilter",
		"Advanced_VPNStatus.asp":             "VPN",
		"UUAccelerator.asp":                  "uuRegister",
		"Module_Softcenter.asp":              "softcenter",
	}
	for path, needle := range pages {
		code, body := s.request("GET", "/"+path, "")
		if code != 200 || !strings.Contains(strings.ToLower(body), strings.ToLower(needle)) || strings.Contains(body, "<%") {
			panic(fmt.Sprintf("native page %s status=%d length=%d body=%s", path, code, len(body), body))
		}
		record("native_authenticated_page_" + path)
	}
	code, body = previewForm(s, fields)
	if code != 200 || strings.TrimSpace(nrCommand("/bin/nvram", "get", "vpn_client1_desc")) != "owned-preview-profile" {
		panic(fmt.Sprintf("native VPN save status=%d body=%s", code, body))
	}
	record("native_authenticated_vpn_profile_save_and_nvram_readback")
	nrMust(os.WriteFile("/koolshare/scripts/coexist_probe.sh", []byte("#!/bin/sh\n. /koolshare/scripts/base.sh\ndbus set localmod_coexist_output=\"$(dbus get localmod_coexist_input)-ok\"\nhttp_response \"$ID\"\n"), 0755))
	coBackendReady()
	coPrivateDenied()
	coRoundtrip(s, 11201)
	record("native_https_center_callback_and_private_backend_guard")
	test := &onlineTest{s: s, repo: repo, uu: u, id: 11300, sentinels: map[string][]byte{}, archive: nrRead("/jffs/cert.tgz")}
	for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-cache/uu.tar.gz.md5", "/tmp/uu.tar.gz"} {
		nrMust(os.MkdirAll(p[:strings.LastIndex(p, "/")], 0700))
		value := []byte("owned-native-preview:" + p)
		nrMust(os.WriteFile(p, value, 0600))
		test.sentinels[p] = value
	}
	test.operation("v1", "", true)
	nrCommand("/usr/bin/dbus", "set", "onlineprobe_config=user-retained")
	test.plugin("1.0")
	test.record("native_base_install_callback_keeps_uu")
	test.operation("v2", "", true)
	test.plugin("2.0")
	test.record("native_base_update_keeps_config_and_uu")
	test.stopPlugin()
	test.uninstall(true)
	test.record("native_base_uninstall_keeps_uu_and_certificates")
	oldFP := s.fingerprint
	s.stop()
	s = nrStart(ctx, "merlin-native-preview-restart", true)
	defer s.stop()
	s.login()
	if s.fingerprint != oldFP {
		panic("certificate changed on restart")
	}
	coRoundtrip(s, 11401)
	coUUAlive(u.pid)
	coUUPage(s)
	if strings.TrimSpace(nrCommand("/bin/nvram", "get", "vpn_client1_desc")) != "owned-preview-profile" {
		panic("saved profile lost on HTTPd restart")
	}
	record("native_httpd_restart_preserves_certificate_profile_center_and_uu")
	// Exercise a genuine failing installer last. The production checkpoint
	// contract deliberately blocks writes until a later boot; it must remain
	// intact on the new base instead of being bypassed by this test.
	test.s = s
	test.operation("v1", "", true)
	nrCommand("/usr/bin/dbus", "set", "onlineprobe_config=user-retained")
	test.plugin("1.0")
	previousUninstaller := string(nrRead("/koolshare/scripts/uninstall_onlineprobe.sh"))
	failing := repo.apps["installfail"]
	failing.Version = "3.0"
	repo.apps["installfail"] = failing
	test.operation("installfail", "", false)
	test.pluginCheck("1.0", false)
	if previousUninstaller != string(nrRead("/koolshare/scripts/uninstall_onlineprobe.sh")) || strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "softcenter_recovery_required")) != "1" {
		panic("failed installer did not preserve the prior plugin and recovery requirement")
	}
	code, _ = s.request("POST", "/_api/", `{"id":11501,"method":"onlineprobe.sh","params":["probe"],"fields":{}}`)
	if code != 423 {
		panic(fmt.Sprintf("checkpoint write lock missing: %d", code))
	}
	code, body = s.request("GET", "/_api/onlineprobe_", "")
	if code != 200 || !strings.Contains(body, "user-retained") {
		panic("read-only inspection unavailable during recovery")
	}
	test.record("failed_update_preserves_plugin_config_uu_and_requires_next_boot_recovery")
	checks = append(checks, test.checks...)
	b, e := json.Marshal(map[string]any{"checks": checks, "uu_api_requests": u.calls.Load(), "uu_downloads": u.downloads.Load(), "real_uu_acceleration_tested": false, "native_boot_tested": false, "failed_update_requires_next_boot_recovery": true, "next_boot_recovery_tested": false, "full_upgrade_complete": false})
	nrMust(e)
	fmt.Println("NATIVE_PREVIEW_RESULT", string(b))
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "stop")
}
