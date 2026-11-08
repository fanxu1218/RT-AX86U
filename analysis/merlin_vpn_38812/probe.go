package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

func vpRun(ctx context.Context, args ...string) ([]byte, error) {
	c := exec.CommandContext(ctx, args[0], args[1:]...)
	var stderr bytes.Buffer
	c.Stderr = &stderr
	b, e := c.Output()
	if e != nil {
		return append(b, stderr.Bytes()...), e
	}
	return b, nil
}
func vpModel(ctx context.Context, args ...string) map[string]any {
	argv := []string{"/usr/bin/qemu-arm", "-L", "/", "-E", "LD_PRELOAD=/work/build/native_hw_fixture.so", "/usr/libexec/localmod/merlin-vpn-model"}
	b, e := vpRun(ctx, append(argv, args...)...)
	if e != nil {
		panic(fmt.Sprintf("model failed %v: %s", e, b))
	}
	if bytes.Contains(b, []byte("owned-private-password")) || bytes.Contains(b, []byte("owned-private-username")) || bytes.Contains(b, []byte("owned-private-custom")) {
		panic("private field disclosed")
	}
	var v map[string]any
	nrMust(json.Unmarshal(b, &v))
	return v
}
func vpFiles(prefix string) map[string]string {
	out := map[string]string{}
	nrMust(filepath.Walk(prefix, func(p string, s os.FileInfo, e error) error {
		if e != nil {
			return e
		}
		if s.Mode().IsRegular() {
			out[p] = fmt.Sprintf("%x", sha256.Sum256(nrRead(p)))
		}
		return nil
	}))
	return out
}
func vpEqual(a, b any) {
	aa, _ := json.Marshal(a)
	bb, _ := json.Marshal(b)
	if !bytes.Equal(aa, bb) {
		panic("retained state mismatch")
	}
}
func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()
	checks := []string{}
	record := func(s string) { checks = append(checks, s); fmt.Println("PASS", s) }
	before := map[string]string{}
	for _, p := range []string{"/usr/libexec/localmod/rc.vendor", "/usr/libexec/localmod/httpd", "/usr/lib/libshared.so", "/usr/lib/libssl.so.1.1", "/usr/lib/libcrypto.so.1.1", "/www/UUAccelerator.asp"} {
		before[p] = fmt.Sprintf("%x", sha256.Sum256(nrRead(p)))
	}
	nrMust(os.MkdirAll("/jffs/openvpn", 0700))
	nrMust(os.WriteFile("/jffs/openvpn/vpn_client1_custom3", []byte("owned-private-custom"), 0600))
	nrMust(os.WriteFile("/koolshare/scripts/coexist_probe.sh", []byte("#!/bin/sh\n. /koolshare/scripts/base.sh\ndbus set localmod_coexist_output=\"$(dbus get localmod_coexist_input)-ok\"\nhttp_response \"$ID\"\n"), 0755))
	u := onlineUUStart(ctx)
	defer u.close()
	record("factory_ntp_download_checksum_start_and_owned_uu_worker_alive")
	s := nrStart(ctx, "vpn38812-phase1", true)
	defer s.stop()
	s.login()
	coUUPage(s)
	coBackendReady()
	coPrivateDenied()
	coRoundtrip(s, 801)
	record("factory_https_login_uu_page_and_authenticated_software_center_callback")
	set := func(k, v string) { _, e := vpRun(ctx, "/bin/nvram", "set", k+"="+v); nrMust(e) }
	for i := 1; i <= 5; i++ {
		p := fmt.Sprintf("vpn_client%d_", i)
		for k, v := range map[string]string{"if": "tun", "port": "35325", "proto": "udp", "hmac": "4", "rgw": "3", "adns": "3", "fw": "2", "nat": "1", "ncp_ciphers": "AES-256-GCM:AES-128-GCM", "username": "owned-private-username", "password": "owned-private-password"} {
			set(p+k, v)
		}
	}
	for i := 1; i <= 2; i++ {
		p := fmt.Sprintf("vpn_server%d_", i)
		for k, v := range map[string]string{"if": "tun", "port": "35326", "proto": "udp", "hmac": "4", "client_access": "2", "pdns": "1", "ncp_ciphers": "AES-256-GCM"} {
			set(p+k, v)
		}
	}
	set("vpn_client2_if", "tap")
	set("vpn_client2_hmac", "3")
	nvramBefore := vpFiles("/tmp/native-nvram")
	jffsBefore := vpFiles("/jffs/openvpn")
	certBefore := fmt.Sprintf("%x", sha256.Sum256(nrRead("/jffs/cert.tgz")))
	cap := vpModel(ctx, "capabilities")
	if cap["private_libovpn"] != true || cap["private_libshared"] != true || cap["service_control_enabled"] != false {
		panic("capability mismatch")
	}
	record("real_merlin_libovpn_and_libshared_loaded_from_private_paths_without_global_replacement")
	models := []map[string]any{}
	for round := 0; round < 3; round++ {
		for i := 1; i <= 5; i++ {
			v := vpModel(ctx, "client", fmt.Sprint(i))
			tls, iface := float64(2), fmt.Sprintf("tun%d", i+10)
			if i == 2 {
				tls, iface = 1, "tap12"
			}
			if v["unit"] != float64(i) || v["tls_crypt"] != tls || v["interface"] != iface || v["port"] != float64(35325) || v["dns_mode"] != float64(3) || v["redirect_gateway"] != float64(3) || v["firewall_mode"] != float64(2) {
				panic(fmt.Sprint(v))
			}
			if round == 0 {
				models = append(models, v)
			}
		}
		for i := 1; i <= 2; i++ {
			v := vpModel(ctx, "server", fmt.Sprint(i))
			if v["tls_crypt"] != float64(2) || v["port"] != float64(35326) || v["client_access"] != float64(2) || v["push_dns"] != float64(1) {
				panic(fmt.Sprint(v))
			}
			if round == 0 {
				models = append(models, v)
			}
		}
		coUUAlive(u.pid)
	}
	record("five_client_two_server_native_models_repeat_three_rounds_tlscrypt_v1_v2_tun_tap_dns_policy_fields")
	record("username_password_and_custom_directives_are_not_returned_by_model_api")
	for _, args := range [][]string{{"client", "0"}, {"client", "6"}, {"server", "3"}, {"client", "1;reboot"}, {"client", "01"}, {"start-client", "1"}, {"stop-client", "1"}, {"reset"}} {
		argv := append([]string{"/usr/bin/qemu-arm", "-L", "/", "/usr/libexec/localmod/merlin-vpn-model"}, args...)
		if _, e := vpRun(ctx, argv...); e == nil {
			panic("invalid/write request accepted")
		}
	}
	record("invalid_units_and_write_start_stop_reset_commands_refused")
	vpEqual(nvramBefore, vpFiles("/tmp/native-nvram"))
	vpEqual(jffsBefore, vpFiles("/jffs/openvpn"))
	record("native_configuration_queries_and_rejected_controls_preserve_all_fixture_nvram_and_openvpn_files")
	library := "/usr/lib/localmod/vpn38812/libovpn.so"
	nrMust(os.Rename(library, library+".unavailable"))
	_, e := vpRun(ctx, "/usr/bin/qemu-arm", "-L", "/", "-E", "LD_PRELOAD=/work/build/native_hw_fixture.so", "/usr/libexec/localmod/merlin-vpn-model", "capabilities")
	nrMust(os.Rename(library+".unavailable", library))
	if e == nil {
		panic("missing private library was accepted")
	}
	record("missing_private_library_refuses_operation_without_factory_service_fallback")
	coUUAlive(u.pid)
	coUUPage(s)
	coRoundtrip(s, 802)
	coPrivateDenied()
	if u.calls.Load() != 1 || u.downloads.Load() != 1 || string(nrRead("/tmp/owned-uu-launches")) != "start\n" {
		panic("UU restarted")
	}
	if fmt.Sprintf("%x", sha256.Sum256(nrRead("/jffs/cert.tgz"))) != certBefore {
		panic("TLS certificate changed")
	}
	for p, h := range before {
		if fmt.Sprintf("%x", sha256.Sum256(nrRead(p))) != h {
			panic("factory core was replaced")
		}
	}
	record("factory_core_tls_certificate_software_center_and_single_uu_worker_preserved_after_prototype_queries")
	b, e := json.Marshal(map[string]any{"checks": checks, "models": models, "capabilities": cap, "model_queries": 22, "uu_api_calls": u.calls.Load(), "uu_downloads": u.downloads.Load(), "uu_pid": u.pid, "factory_files_preserved": before, "full_firmware_upgrade_complete": false, "service_control_enabled": false, "real_uu_acceleration_tested": false})
	nrMust(e)
	fmt.Println("VPN38812_PHASE1_RESULT", strings.TrimSpace(string(b)))
}
