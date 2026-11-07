package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

type fancyPackage struct {
	Version, Phase, Path string
	SHA256               string `json:"sha256"`
	AdaptedPath          string `json:"adapted_path"`
	AdaptedSHA256        string `json:"adapted_sha256"`
	AdaptedMD5           string `json:"adapted_md5"`
	Files                map[string]struct {
		SHA256 string `json:"sha256"`
	}
}

func fancySHA(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func fancyDB(k string) string  { return strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", k)) }
func fancySet(k, v string)     { nrCommand("/usr/bin/dbus", "set", k+"="+v) }
func fancyWait(log string, success bool) string {
	deadline := time.Now().Add(90 * time.Second)
	for time.Now().Before(deadline) {
		b, _ := os.ReadFile(log)
		_, err := os.Stat("/tmp/.localmod/plugin-operation.lock")
		if bytes.Contains(b, []byte("XU6J03M6")) && os.IsNotExist(err) {
			result := fancyDB("softcenter_installing_result")
			if (result == "0") != success {
				panic(fmt.Sprintf("Fancyss result %q expected %v: %s", result, success, b))
			}
			return string(b)
		}
		time.Sleep(100 * time.Millisecond)
	}
	b, _ := os.ReadFile(log)
	panic("Fancyss operation timeout: " + string(b))
}
func fancyOffline(t *onlineTest, p fancyPackage, adapted, success bool) string {
	path, expected := p.Path, p.SHA256
	if adapted {
		path, expected = p.AdaptedPath, p.AdaptedSHA256
	}
	blob := nrRead("/work/" + path)
	if fancySHA(blob) != expected {
		panic("Fancyss input digest differs")
	}
	name := "fancyss-owned-" + p.Version + ".tar.gz"
	nrMust(os.WriteFile("/tmp/upload/"+name, blob, 0600))
	nrMust(os.WriteFile("/tmp/upload/soft_log.txt", nil, 0600))
	t.rpc("ks_tar_install.sh", "", map[string]string{"soft_name": name})
	return fancyWait("/tmp/upload/soft_log.txt", success)
}
func main() {
	defer func() {
		if v := recover(); v != nil {
			for _, p := range []string{"/tmp/upload/soft_log.txt", "/tmp/upload/soft_install_log.txt", "/tmp/upload/ss_log.txt", "/tmp/.localmod/bootstrap.log", nrOutput("fancyss-server.log")} {
				if b, e := os.ReadFile(p); e == nil {
					fmt.Printf("DIAGNOSTIC %s\n%s\n", p, b)
				}
			}
			panic(v)
		}
	}()
	phase := os.Args[1]
	ctx, cancel := context.WithTimeout(context.Background(), 600*time.Second)
	defer cancel()
	var inputs struct{ Packages []fancyPackage }
	nrMust(json.Unmarshal(nrRead("/work/build/fancyss_inputs.json"), &inputs))
	if strings.HasSuffix(phase, "proxy") {
		p := inputs.Packages[1]
		nrCommand("/bin/tar", "-xzf", "/work/"+p.Path, "-C", "/tmp", "shadowsocks/bin/xray")
		b := nrRead("/tmp/shadowsocks/bin/xray")
		if fancySHA(b) != p.Files["bin/xray"].SHA256 {
			panic("Xray probe binary changed")
		}
		nrMust(os.WriteFile("/koolshare/bin/xray", b, 0755))
		checks := map[string]bool{}
		fancyProxy(ctx, func(n string) { checks[n] = true; fmt.Println("PASS", n) })
		fmt.Printf("FANCYSS_RESULT %s\n", mustFancyJSON(map[string]any{"checks": checks}))
		return
	}
	repo := onlineRepository()
	defer repo.close()
	s := nrStart(ctx, "fancyss", true)
	defer s.stop()
	_, unauthPage := s.request("GET", "/Module_FancyssLocalmod.asp", "")
	if strings.Contains(unauthPage, "ks_app_install.sh") {
		panic("Fancyss installation page served without native login")
	}
	s.login()
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	t := &onlineTest{s: s, repo: repo, uu: u, id: 134000, sentinels: map[string][]byte{}, archive: nrRead("/jffs/cert.tgz")}
	for _, p := range []string{"/jffs/uu.tar.gz", "/jffs/uu.tar.gz.md5", "/jffs/uu-state/account", "/tmp/uu.tar.gz", "/jffs/syslog.log", "/jffs/scripts/unrelated-user-hook"} {
		nrMust(os.MkdirAll(filepath.Dir(p), 0700))
		b := []byte("owned-fancyss-peer-sentinel:" + p)
		nrMust(os.WriteFile(p, b, 0600))
		t.sentinels[p] = b
	}
	checks := map[string]bool{}
	record := func(name string) { t.record(name); checks[name] = true; fmt.Println("PASS", name) }
	current := inputs.Packages[1]
	if strings.HasSuffix(phase, "baseline") {
		log := fancyOffline(t, current, false, false)
		if !strings.Contains(log, "不是ASUS hnd平台") {
			panic("r8 platform rejection not reproduced")
		}
		record("r8_original_hnd_v8_package_rejected_before_mutation_uu_preserved")
		fmt.Printf("FANCYSS_RESULT %s\n", mustFancyJSON(map[string]any{"checks": checks, "baseline": true}))
		return
	}
	// Only the package's platform gate sees the original target's identity.
	// The guest kernel/iptables remain Alpine 6.12; this is never a kernel test.
	nrMust(os.Remove("/bin/uname")) // Remove BusyBox symlink before writing the fixture.
	nrMust(os.WriteFile("/bin/uname", []byte("#!/bin/sh\ncase \"$*\" in -r) echo 4.1.52;; -m) echo aarch64;; *) exec /bin/busybox uname \"$@\";; esac\n"), 0755))
	fancySet("ss_basic_enable", "0")
	for k, v := range map[string]string{"ssid_owned": "retained-ssid", "ssserver_owned": "retained-peer", "ddnsgo_localcheck": "300", "ddnsto_owned": "retained-tunnel"} {
		fancySet(k, v)
	}
	retained := func() {
		for k, v := range map[string]string{"ssid_owned": "retained-ssid", "ssserver_owned": "retained-peer", "ddnsgo_localcheck": "300", "ddnsto_owned": "retained-tunnel"} {
			if fancyDB(k) != v {
				panic("peer dbus key changed: " + k)
			}
		}
	}
	// A raw upstream package would delete UU's root-level archives. New policy
	// must reject it even after HND v8 platform support is added.
	log := fancyOffline(t, current, false, false)
	if !strings.Contains(log, "兼容包") {
		panic("unadapted Fancyss was not policy-rejected")
	}
	record("unadapted_upstream_package_denied_uu_and_router_logs_retained")
	code, page := s.request("GET", "/Module_FancyssLocalmod.asp", "")
	if code != 200 || strings.Contains(page, "@FANCYSS_") || !strings.Contains(page, current.AdaptedMD5) || !strings.Contains(page, "ks_app_install.sh") {
		panic("built-in Fancyss installation page differs from pinned package")
	}
	record("native_authenticated_installation_entry_has_pinned_version_and_package_metadata")
	fancyCompat(t, record)
	if strings.HasSuffix(phase, "components") {
		owned := "/tmp/fancyss-jq-probe"
		nrMust(os.Mkdir(owned, 0700))
		defer os.RemoveAll(owned)
		nrCommand("/bin/tar", "-xzf", "/work/"+current.Path, "-C", owned, "shadowsocks/bin/jq")
		b := nrRead(owned + "/shadowsocks/bin/jq")
		if fancySHA(b) != current.Files["bin/jq"].SHA256 {
			panic("component JQ source differs")
		}
		nrMust(os.WriteFile("/koolshare/bin/jq", b, 0755))
		remove := fancyExtended(t, record, false)
		remove()
		fmt.Printf("FANCYSS_RESULT %s\n", mustFancyJSON(map[string]any{"checks": checks, "components_only": true}))
		return
	}
	retainedNode := map[string]string{"type": "0", "name": "isolated-owned-node", "group": "manual", "mode": "1", "server": "retained.invalid", "port": "443", "method": "aes-128-gcm", "password": "owned-test-secret-not-a-real-account", "_source": "manual"}
	for _, p := range inputs.Packages {
		log := fancyOffline(t, p, true, true)
		fmt.Printf("FANCYSS_INSTALL_LOG %s\n%s\n", p.Version, log)
		if fancyDB("softcenter_module_shadowsocks_version") != p.Version || strings.TrimSpace(string(nrRead("/koolshare/ss/version"))) != p.Version {
			panic("Fancyss installed version mismatch")
		}
		if fancyDB("ss_basic_enable") != "0" {
			panic("Fancyss unexpectedly enabled")
		}
		for name, file := range p.Files {
			if !strings.HasPrefix(name, "bin/") && !strings.HasPrefix(name, "scripts/") {
				continue
			}
			// Official curl supports proxy; upstream intentionally links this name.
			if name == "bin/curl-fancyss" {
				continue
			}
			if fancySHA(nrRead("/koolshare/"+name)) != file.SHA256 {
				panic("Fancyss installed file changed: " + name)
			}
		}
		code, body := s.request("GET", "/Module_shadowsocks.asp", "")
		if code != 200 || !strings.Contains(body, "ws_enable = 0") {
			panic("authenticated Fancyss page unavailable")
		}
		if c, e := net.DialTimeout("tcp4", "127.0.0.1:803", time.Second); e == nil {
			c.Close()
			panic("unauthenticated Fancyss websocket listener started")
		}
		retained()
		record("adapted_" + p.Version + "_installed_disabled_original_binaries_auth_page_no_803_and_uu")
		if p.Phase == "old" {
			fancySet("ss_basic_interval", "4")
			b, e := json.Marshal(retainedNode)
			nrMust(e)
			for k, v := range map[string]string{"fss_node_order": "1", "fss_node_current": "1", "fss_node_next_id": "2", "fss_data_schema": "2", "fss_data_secret_mode": "raw", "fss_node_1": base64.StdEncoding.EncodeToString(b)} {
				fancySet(k, v)
			}
			nrMust(os.MkdirAll("/koolshare/configs/fancyss", 0700))
			nrMust(os.WriteFile("/koolshare/configs/fancyss/owned-retained.conf", []byte("owned nonsecret configuration\n"), 0600))
		} else {
			if fancyDB("ss_basic_interval") != "4" || string(nrRead("/koolshare/configs/fancyss/owned-retained.conf")) != "owned nonsecret configuration\n" {
				panic("genuine Fancyss upgrade lost config")
			}
			record("genuine_3_5_28_to_3_5_29_upgrade_preserves_plugin_config_peers_and_uu")
			b, e := base64.StdEncoding.DecodeString(fancyDB("fss_node_1"))
			nrMust(e)
			var node map[string]any
			nrMust(json.Unmarshal(b, &node))
			for k, v := range retainedNode {
				if node[k] != v {
					panic("real schema2 node field changed: " + k)
				}
			}
			if fancyDB("fss_node_order") != "1" || fancyDB("fss_node_current") != "1" {
				panic("real selected node changed")
			}
			record("real_schema2_node_selection_and_owned_secret_fields_survive_genuine_fancyss_upgrade")
		}
	}
	version := nrCommand("/koolshare/bin/xray", "version")
	if !strings.Contains(strings.ToLower(version), "xray") {
		panic("real Xray binary did not run")
	}
	if ok, _ := regexp.MatchString(`^\d+\.\d+\.\d+\s*$`, nrCommand("/koolshare/bin/node-tool", "version")); !ok {
		panic("real node-tool binary did not run")
	}
	record("actual_aarch64_xray_and_node_tool_execute_with_retained_vendor_libraries")
	fancyProxy(ctx, record)
	removeExtended := fancyExtended(t, record, false)
	t.rpc("ss_update.sh", "update", map[string]string{})
	for i := 0; i < 30; i++ {
		if strings.Contains(string(nrRead("/tmp/upload/ss_log.txt")), "XU6J03M6") {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if !strings.Contains(string(nrRead("/tmp/upload/ss_log.txt")), "兼容") && !strings.Contains(string(nrRead("/tmp/upload/ss_log.txt")), "适配") {
		panic("managed updater did not explain update path")
	}
	record("plugin_self_update_uses_managed_transaction_path")
	// Exercise the actual upstream HTTP status callback while disabled.
	t.id++
	payload := mustFancyJSON(map[string]any{"id": t.id, "method": "ss_status.sh", "params": []string{"1"}, "fields": ""})
	code, body := s.request("POST", "/_api/", payload)
	if code != 200 || !strings.Contains(body, "result") {
		panic(fmt.Sprintf("Fancyss native HTTP status %d %s", code, body))
	}
	record("real_fancyss_status_http_callback_over_original_https_with_uu")
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "restart")
	coBackendReady()
	retained()
	record("center_restart_keeps_fancyss_configuration_and_uu")
	t.rpc("ks_app_remove.sh", "ks_app_remove", map[string]string{"softcenter_installing_todo": "shadowsocks", "softcenter_installing_title": "Fancyss"})
	t.wait(true)
	for _, p := range []string{"/koolshare/ss", "/koolshare/bin/xray", "/koolshare/scripts/uninstall_shadowsocks.sh", "/koolshare/webs/Module_shadowsocks.asp"} {
		if _, e := os.Lstat(p); !os.IsNotExist(e) {
			panic("Fancyss uninstall left " + p)
		}
	}
	if fancyDB("softcenter_module_shadowsocks_version") != "" {
		panic("Fancyss registration left after uninstall")
	}
	retained()
	record("authentic_uninstaller_removes_plugin_preserves_peer_namespaces_uu_logs_and_certificate")
	removeExtended()
	if _, e := os.Stat("/koolshare/configs/fancyss/owned-retained.conf"); !os.IsNotExist(e) {
		panic("plugin configuration not cleared by explicit uninstall")
	}
	// Fresh installation after complete explicit removal, through the native
	// TLS download/transaction flow used by the built-in installation entry.
	url := "featured/fancyss-current.tar.gz"
	repo.mu.Lock()
	repo.apps["fancyss-featured"] = onlineApp{"shadowsocks", "Fancyss", current.Version, current.AdaptedMD5, url}
	repo.blobs["/"+url] = nrRead("/work/" + current.AdaptedPath)
	repo.mu.Unlock()
	t.operation("fancyss-featured", "", true)
	if fancyDB("ss_basic_enable") == "1" || fancyDB("ss_basic_interval") != "2" || fancyDB("softcenter_module_shadowsocks_version") != current.Version {
		panic("fresh current Fancyss defaults differ")
	}
	record("fresh_current_fancyss_via_verified_https_native_wget_and_managed_transaction_after_complete_uninstall")
	removeFresh := fancyExtended(t, record, true)
	t.rpc("ks_app_remove.sh", "ks_app_remove", map[string]string{"softcenter_installing_todo": "shadowsocks", "softcenter_installing_title": "Fancyss"})
	t.wait(true)
	removeFresh()
	if u.calls.Load() != 1 || u.downloads.Load() != 1 {
		panic("UU download/restart changed")
	}
	fmt.Printf("FANCYSS_RESULT %s\n", mustFancyJSON(map[string]any{"checks": checks, "xray_version": strings.TrimSpace(version), "uu_api_requests": u.calls.Load(), "uu_launches": strings.Count(string(nrRead("/tmp/owned-uu-launches")), "start\n"), "platform_gate_fixture": true, "original_binary_files": len(current.Files), "phase": phase, "end_id": strconv.Itoa(t.id)}))
}
func mustFancyJSON(v any) string { b, e := json.Marshal(v); nrMust(e); return string(b) }
