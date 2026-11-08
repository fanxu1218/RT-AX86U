package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strings"
	"time"
)

var candidateChecks []string

func candidateRecord(s string) { candidateChecks = append(candidateChecks, s); fmt.Println("PASS", s) }
func candidateForm(s *nrServer, fields url.Values) (int, string) {
	r, e := http.NewRequest("POST", "https://192.168.77.1:34443/applyapp.cgi", strings.NewReader(fields.Encode()))
	nrMust(e)
	r.Header.Set("User-Agent", "Mozilla/5.0 native-lifecycle-fixture")
	r.Header.Set("Origin", "https://192.168.77.1:34443")
	r.Header.Set("Referer", "https://192.168.77.1:34443/Advanced_OpenVPNClient_Content.asp")
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
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
func candidateReadWritePages() {
	ctx, cancel := context.WithTimeout(context.Background(), 75*time.Second)
	defer cancel()
	started := time.Now()
	b, e := exec.CommandContext(ctx, "/usr/libexec/localmod/compat-bin/sleep", "0.1").CombinedOutput()
	if e != nil || time.Since(started) < 80*time.Millisecond {
		panic(fmt.Sprintf("center fractional sleep: %v %s", e, b))
	}
	// Native ash lacks the optional `command` builtin. Resolve through the
	// actual sourced base and execute the same bare command plugins use.
	selected := "/usr/libexec/localmod/compat-bin/sleep"
	path := nrCommand("/bin/sh", "-c", ". /koolshare/scripts/base.sh; printf '%s' \"$PATH\"")
	if !strings.HasPrefix(path, "/koolshare/bin:/koolshare/scripts:/usr/libexec/localmod/compat-bin:") {
		panic("center private tool path not installed: " + path)
	}
	started = time.Now()
	b, e = exec.CommandContext(ctx, "/bin/sh", "-c", ". /koolshare/scripts/base.sh; sleep 0.1").CombinedOutput()
	if e != nil || time.Since(started) < 80*time.Millisecond {
		panic(fmt.Sprintf("center base PATH fractional sleep: %v %s", e, b))
	}
	candidateRecord("candidate_center_private_fractional_sleep_and_managed_base_path")
	started = time.Now()
	b, e = exec.CommandContext(ctx, selected, "0.025s", "0.025").CombinedOutput()
	if e != nil || time.Since(started) < 40*time.Millisecond {
		panic(fmt.Sprintf("center duration sum: %v %s", e, b))
	}
	for _, args := range [][]string{nil, {"-1"}, {"NaN"}, {"inf"}, {"1e100"}, {"1ss"}, {"0", "garbage"}} {
		if b, e = exec.CommandContext(ctx, selected, args...).CombinedOutput(); e == nil {
			panic(fmt.Sprintf("center sleep accepted invalid duration %q: %s", args, b))
		}
	}
	if b, e = exec.CommandContext(ctx, selected, "0m", "0h", "0d").CombinedOutput(); e != nil {
		panic(fmt.Sprintf("center sleep suffixes: %v %s", e, b))
	}
	candidateRecord("candidate_center_sleep_sums_durations_and_rejects_invalid_input")
	s := nrStart(ctx, "candidate-native-pages", true)
	defer s.stop()
	fields := url.Values{"action_mode": {"apply"}, "vpn_client1_desc": {"candidate-native-profile"}}
	candidateForm(s, fields)
	if strings.TrimSpace(nrCommand("/bin/nvram", "get", "vpn_client1_desc")) == "candidate-native-profile" {
		panic("candidate unauthenticated VPN write")
	}
	s.login()
	for path, needle := range map[string]string{"Advanced_OpenVPNClient_Content.asp": "vpn_client_custom3", "Advanced_VPN_OpenVPN.asp": "vpn_server", "Advanced_VPNDirector.asp": "vpndirector", "DNSDirector.asp": "dnsfilter", "Advanced_VPNStatus.asp": "VPN", "UUAccelerator.asp": "uuRegister", "Module_Softcenter.asp": "softcenter"} {
		code, body := s.request("GET", "/"+path, "")
		if code != 200 || !strings.Contains(strings.ToLower(body), strings.ToLower(needle)) || strings.Contains(body, "<%") {
			panic(fmt.Sprintf("candidate page %s status=%d", path, code))
		}
		candidateRecord("candidate_native_page_" + path)
	}
	code, body := candidateForm(s, fields)
	if code != 200 || strings.TrimSpace(nrCommand("/bin/nvram", "get", "vpn_client1_desc")) != "candidate-native-profile" {
		panic(fmt.Sprintf("candidate native VPN save %d %s", code, body))
	}
	candidateRecord("candidate_native_auth_and_vpn_save_readback")
	for _, v := range []struct{ path, argv0, flag, version string }{
		{"/usr/sbin/openvpn", "openvpn", "--version", "2.7.6"},
		{"/usr/sbin/dnsmasq", "dnsmasq", "--version", "2.93"},
		{"/usr/sbin/curl", "curl", "--version", "8.17.0"},
		{"/usr/sbin/wget", "wget", "--version", "1.25.0"},
		{"/usr/bin/dropbearmulti", "dropbear", "-V", "2026.94"},
		{"/usr/sbin/miniupnpd", "miniupnpd", "--version", "2.3.11"},
	} {
		path := v.path
		// The owned repository transport wrapper retained the actual wget here.
		if v.argv0 == "wget" {
			path = "/usr/libexec/localmod/wget"
		}
		b, e := exec.CommandContext(ctx, "/usr/bin/qemu-arm", "-0", v.argv0, "-L", "/", path, v.flag).CombinedOutput()
		if !strings.Contains(string(b), v.version) {
			panic(fmt.Sprintf("candidate native component %s %v %s", v.argv0, e, b))
		}
		candidateRecord("candidate_native_component_loader_version_" + v.argv0)
	}
}
func candidateDuringUU(s *nrServer, u *onlineUU) {
	if countLines("/tmp/native-launcher-forwarded") != 1 {
		panic("candidate UU did not traverse its actual rc launcher exactly once")
	}
	if strings.TrimSpace(string(nrRead("/tmp/native-launcher-argv0"))) != "ntpd_synced" {
		panic("production launcher changed the native callback argv0")
	}
	dir := strings.TrimSpace(string(nrRead("/var/uu_plugin_dir")))
	info, e := os.Stat(dir)
	if e != nil || !info.IsDir() || dir == "/" {
		panic("native UU monitor plugin directory context missing")
	}
	modelBytes, _ := os.ReadFile("/var/model")
	model := strings.Split(strings.TrimSpace(string(modelBytes)), ",")[0]
	if model == "" {
		model = strings.TrimSpace(nrCommand("/bin/nvram", "get", "productid"))
	}
	if strings.ToLower(strings.ReplaceAll(model, "-", "")) != "rtax86u" {
		panic("native UU monitor model context mismatch: " + model)
	}
	mac := strings.TrimSpace(string(nrRead("/var/label_macaddr")))
	if _, e := net.ParseMAC(mac); e != nil {
		panic("native UU monitor label MAC context missing")
	}
	candidateRecord("candidate_native_uu_monitor_model_storage_and_mac_context")
	nrCommand("/usr/bin/dbus", "set", "localmod_candidate_alias=retained-db-value")
	nrCommand("/sbin/service", "restart_skipd")
	if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "localmod_candidate_alias")) != "retained-db-value" {
		panic("candidate database alias restart lost data")
	}
	coUUAlive(u.pid)
	candidateRecord("candidate_rc_database_alias_restart_preserves_state_and_uu")
	nrCommand("/sbin/service", "restart_softcenter")
	coBackendReady()
	coPrivateDenied()
	coUUAlive(u.pid)
	coUUPage(s)
	if countLines("/tmp/native-launcher-forwarded") != 1 {
		panic("software center alias fell through to vendor rc")
	}
	candidateRecord("candidate_rc_center_restart_keeps_native_uu_and_private_guard")
}
