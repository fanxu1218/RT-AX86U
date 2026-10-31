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
	"net"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
)

type realPackage struct {
	Module   string            `json:"module"`
	Version  string            `json:"catalog_version"`
	Phase    string            `json:"phase"`
	Path     string            `json:"path"`
	SHA256   string            `json:"sha256"`
	MD5      string            `json:"md5"`
	Internal string            `json:"internal_version"`
	Files    map[string]string `json:"files"`
}
type realSuite struct {
	t         *onlineTest
	packages  map[string]realPackage
	installed map[string]realPackage
	checks    []string
	details   map[string]any
}

func realCurlProbe() {
	var hits atomic.Int32
	l, e := net.Listen("tcp4", "127.0.0.1:35003")
	nrMust(e)
	server := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { hits.Add(1); fmt.Fprint(w, "owned-curl-probe") })}
	go server.Serve(l)
	defer server.Close()
	numeric := nrCommand("/usr/sbin/curl", "--noproxy", "*", "--max-time", "2", "http://127.0.0.1:35003/probe")
	before := hits.Load()
	host := nrCommand("/usr/sbin/curl", "--noproxy", "*", "--resolve", "localhost:35003:127.0.0.1", "--max-time", "2", "http://localhost:35003/probe")
	fmt.Printf("NATIVE_CURL_PROBE numeric_hits=%d numeric_body=%q hostname_hits=%d hostname_body=%q\n", before, numeric, hits.Load()-before, host)
	if before != 0 || hits.Load() != 1 || !strings.Contains(host, "owned-curl-probe") {
		panic("native curl protection probe differs")
	}
}
func realSHA(data []byte) string { sum := sha256.Sum256(data); return hex.EncodeToString(sum[:]) }
func (r *realSuite) record(name string) {
	r.t.record(name)
	r.checks = append(r.checks, name)
	fmt.Println("PASS", name)
}
func realDB(key string) string  { return strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", key)) }
func realSet(key, value string) { nrCommand("/usr/bin/dbus", "set", key+"="+value) }
func (r *realSuite) installedFiles(p realPackage) {
	if realDB("softcenter_module_"+p.Module+"_version") != p.Version || realDB(p.Module+"_version") != p.Version || realDB("softcenter_module_"+p.Module+"_install") != "1" {
		panic("real package registration mismatch: " + p.Module)
	}
	for path, expected := range p.Files {
		target := "/koolshare/" + path
		if path == "bin/ddnsto_arm" {
			target = "/koolshare/bin/ddnsto"
		} else if p.Module == "ddnsto" && strings.HasPrefix(path, "bin/") {
			continue
		}
		if !(strings.HasPrefix(path, "bin/") || strings.HasPrefix(path, "scripts/")) {
			continue
		}
		if realSHA(nrRead(target)) != expected {
			panic("real installed file differs from archive: " + target)
		}
	}
	code, body := r.t.s.request("GET", "/Module_"+p.Module+".asp", "")
	if code != 200 || !strings.Contains(body, "dbus") {
		panic(fmt.Sprintf("real plugin page %s %d", p.Module, code))
	}
	if _, e := os.Stat("/koolshare/scripts/uninstall_" + p.Module + ".sh"); e != nil {
		panic(e)
	}
}
func (r *realSuite) allFiles() {
	for _, p := range r.installed {
		r.installedFiles(p)
	}
}
func (r *realSuite) callback(module, action string, fields any) string {
	r.t.id++
	id := r.t.id
	// DDNS-Go's actual frontend sends an empty string for read-only RPCs.
	if fields == nil {
		fields = ""
	}
	payload, e := json.Marshal(map[string]any{"id": id, "method": module + "_config.sh", "params": []string{action}, "fields": fields})
	nrMust(e)
	code, body := r.t.s.request("POST", "/_api/", string(payload))
	var reply struct {
		Result any `json:"result"`
	}
	nrMust(json.Unmarshal([]byte(body), &reply))
	value := fmt.Sprint(reply.Result)
	valid := value == strconv.Itoa(id)
	if module == "ddnsgo" && action == "status" {
		valid = strings.Contains(value, "进程运行正常")
	}
	if module == "ddnsgo" && action == "version" {
		valid = strings.TrimSpace(value) == strings.TrimSpace(nrCommand("/koolshare/bin/ddnsgo", "-v"))
	}
	if code != 200 || !valid {
		panic(fmt.Sprintf("real callback %s %d %s", module, code, body))
	}
	return body
}
func (r *realSuite) operation(module, phase, event string) {
	p := r.packages[module+"-"+phase]
	r.t.operation(module+"-"+phase, "", true)
	r.installed[module] = p
	r.allFiles()
	r.record(module + "_" + event + "_original_scripts_files_and_authenticated_page")
}
func realPID(module string) string {
	b, e := exec.Command("/bin/pidof", module).Output()
	if e != nil {
		if status, ok := e.(*exec.ExitError); !ok || status.ExitCode() != 1 {
			nrMust(e)
		}
	}
	return strings.TrimSpace(string(b))
}
func (r *realSuite) ddnsgoAlive() string {
	client := &http.Client{Timeout: time.Second}
	for i := 0; i < 50; i++ {
		pid := realPID("ddnsgo")
		if pid != "" {
			res, e := client.Get("http://127.0.0.1:9876/")
			if e == nil {
				body, e := io.ReadAll(res.Body)
				res.Body.Close()
				if e == nil && res.StatusCode == 200 && strings.Contains(strings.ToLower(string(body)), "ddns") {
					return pid
				}
			}
		}
		time.Sleep(50 * time.Millisecond)
	}
	panic("real DDNS-Go process/local UI unavailable")
}
func (r *realSuite) ddnsgoStart(watchdog string) {
	r.callback("ddnsgo", "web_submit", map[string]string{"ddnsgo_enable": "1", "ddnsgo_watchdog": watchdog, "ddnsgo_publicswitch": "0", "ddnsgo_localcheck": "300", "ddnsgo_wancheck": "5", "ddnsgo_port": "9876", "ddnsgo_skipverify": "0"})
	for i := 0; i < 100; i++ {
		if b, _ := os.ReadFile("/tmp/upload/ddnsgo_log.txt"); bytes.Contains(b, []byte("DD01N05S")) {
			r.ddnsgoAlive()
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	panic("real DDNS-Go start callback did not finish")
}
func (r *realSuite) stop(module string) {
	action := "1"
	if module == "ddnsgo" {
		action = "web_submit"
	}
	r.callback(module, action, map[string]string{module + "_enable": "0"})
	for i := 0; i < 100; i++ {
		pid := realPID(module)
		if pid == "" {
			if module != "ddnsgo" {
				return
			}
			if b, _ := os.ReadFile("/tmp/upload/ddnsgo_log.txt"); bytes.Contains(b, []byte("DD01N05S")) {
				return
			}
		}
		time.Sleep(50 * time.Millisecond)
	}
	panic("real plugin stop did not settle: " + module)
}
func (r *realSuite) uninstall(module, event string) {
	r.stop(module)
	r.t.rpc("ks_app_remove.sh", "ks_app_remove", map[string]string{"softcenter_installing_todo": module, "softcenter_installing_title": module})
	r.t.wait(true)
	delete(r.installed, module)
	if realDB("softcenter_module_"+module+"_install") != "" || strings.TrimSpace(nrCommand("/usr/bin/dbus", "list", module+"_")) != "" {
		panic("uninstall left real plugin DBus keys: " + module)
	}
	for _, path := range []string{"/koolshare/webs/Module_" + module + ".asp", "/koolshare/scripts/" + module + "_config.sh", "/koolshare/scripts/uninstall_" + module + ".sh", "/koolshare/res/icon-" + module + ".png"} {
		if _, e := os.Lstat(path); !os.IsNotExist(e) {
			panic("uninstall left real plugin file: " + path)
		}
	}
	if module != "aliddns" {
		if _, e := os.Lstat("/koolshare/bin/" + module); !os.IsNotExist(e) {
			panic("uninstall left real binary")
		}
	}
	if module == "ddnsgo" {
		if _, e := os.Lstat("/koolshare/configs/ddnsgo"); !os.IsNotExist(e) {
			panic("uninstall left DDNS-Go configuration directory")
		}
	}
	for _, dir := range []string{"/koolshare/init.d", "/koolshare/perp"} {
		entries, e := os.ReadDir(dir)
		nrMust(e)
		for _, entry := range entries {
			if strings.Contains(strings.ToLower(entry.Name()), module) {
				panic("uninstall left startup/supervision entry: " + entry.Name())
			}
		}
	}
	r.allFiles()
	r.record(module + "_" + event + "_custom_uninstall_preserves_peers_and_uu")
}
func main() {
	defer func() {
		if failure := recover(); failure != nil {
			fmt.Println("DIAGNOSTIC processes", nrCommand("/bin/ps", "w"))
			fmt.Println("DIAGNOSTIC locks", nrCommand("/bin/ls", "-lR", "/tmp/.localmod"))
			for _, p := range []string{"/tmp/.localmod/bootstrap.log", "/tmp/upload/soft_install_log.txt", "/tmp/upload/ddnsgo_log.txt", "/tmp/upload/ddnsgo.log", "/tmp/online-wget-calls", "/var/log/perpd/current", nrOutput("real-plugins-server.log")} {
				if b, e := os.ReadFile(p); e == nil {
					fmt.Printf("DIAGNOSTIC %s\n%s\n", p, b)
				}
			}
			panic(failure)
		}
	}()
	if len(os.Args) != 2 || (os.Args[1] != "upgrade" && os.Args[1] != "fresh") {
		panic("real plugin phase required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 240*time.Second)
	defer cancel()
	repo := onlineRepository()
	defer repo.close()
	var input struct {
		Packages []realPackage `json:"packages"`
	}
	nrMust(json.Unmarshal(nrRead("/work/build/real_plugin_inputs.json"), &input))
	r := &realSuite{packages: map[string]realPackage{}, installed: map[string]realPackage{}, details: map[string]any{}}
	for _, p := range input.Packages {
		blob := nrRead("/work/" + p.Path)
		sum := md5.Sum(blob)
		if realSHA(blob) != p.SHA256 || hex.EncodeToString(sum[:]) != p.MD5 {
			panic("real package digest changed")
		}
		key := p.Module + "-" + p.Phase
		tarURL := p.Module + "/" + p.Phase + ".tar.gz"
		repo.apps[key] = onlineApp{p.Module, p.Module, p.Version, p.MD5, tarURL}
		repo.blobs["/"+tarURL] = blob
		r.packages[key] = p
	}
	s := nrStart(ctx, "real-plugins", true)
	defer s.stop()
	s.login()
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "start")
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	r.t = &onlineTest{s: s, repo: repo, uu: u, id: 81000, sentinels: map[string][]byte{}, archive: nrRead("/jffs/cert.tgz")}
	for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-cache/uu.tar.gz.md5", "/tmp/uu.tar.gz", "/tmp/foreign-job/install.sh", "/jffs/scripts/real-unrelated-user-hook"} {
		nrMust(os.MkdirAll(p[:strings.LastIndex(p, "/")], 0700))
		data := []byte("real-plugin-coexist-sentinel:" + p)
		nrMust(os.WriteFile(p, data, 0600))
		r.t.sentinels[p] = data
	}
	r.record("native_shell_resolution_center_start_original_process_helper_private_api_and_uu")
	realCurlProbe()
	r.record("native_curl_numeric_url_guard_retained_hostname_callback_pinned_to_loopback")
	fmt.Printf("PIPE_REGRESSION %q\n", nrCommand("/bin/sh", "-c", "echo owned-pipe | tee /tmp/real-pipe; cat /tmp/real-pipe"))
	if string(nrRead("/tmp/real-pipe")) != "owned-pipe\n" {
		panic("added tee did not preserve pipeline output")
	}
	if nrCommand("/bin/sh", "-c", "echo owned-xargs | xargs /bin/echo") != "owned-xargs\n" {
		panic("added xargs failed")
	}
	r.record("required_tee_xargs_added_without_replacing_official_busybox")
	if os.Args[1] != "fresh" {
		for _, module := range []string{"aliddns", "ddnsto", "ddnsgo"} {
			r.operation(module, "old", "fresh_old")
		}
		for key, value := range map[string]string{"aliddns_interval": "5", "aliddns_domain": "retained.invalid", "ddnsto_feat_disk_path_selected": "/jffs/retained", "ddnsgo_localcheck": "300"} {
			realSet(key, value)
		}
		config := []byte("notallowwanaccess: true\n# owned nonsecret retained configuration\n")
		nrMust(os.WriteFile("/koolshare/configs/ddnsgo/default.yaml", config, 0600))
		r.ddnsgoStart("0")
		oldPID := r.ddnsgoAlive()
		r.record("ddnsgo_old_real_arm_binary_runs_local_web_ui_alongside_uu")
		for _, module := range []string{"aliddns", "ddnsto", "ddnsgo"} {
			if module == "ddnsgo" {
				nrMust(os.WriteFile("/tmp/ddnsgo/owned-runtime-data", []byte("preserve"), 0600))
				r.t.operation("ddnsgo-current", "", false)
				if string(nrRead("/tmp/ddnsgo/owned-runtime-data")) != "preserve" || r.ddnsgoAlive() != oldPID {
					panic("rejected update changed running plugin/runtime data")
				}
				r.allFiles()
				r.record("nonempty_registered_runtime_directory_rejected_without_stopping_plugin_or_uu")
				nrMust(os.Remove("/tmp/ddnsgo/owned-runtime-data"))
			}
			r.operation(module, "current", "update")
			for key, value := range map[string]string{"aliddns_interval": "5", "aliddns_domain": "retained.invalid", "ddnsto_feat_disk_path_selected": "/jffs/retained", "ddnsgo_localcheck": "300"} {
				if realDB(key) != value {
					panic("update lost retained configuration: " + key)
				}
			}
			r.ddnsgoAlive()
		}
		if !bytes.Equal(config, nrRead("/koolshare/configs/ddnsgo/default.yaml")) {
			panic("real update changed DDNS-Go retained config")
		}
		if r.ddnsgoAlive() == oldPID {
			panic("DDNS-Go update did not restart real binary")
		}
		r.details["ddnsto_binary_version"] = strings.TrimSpace(nrCommand("/koolshare/bin/ddnsto", "-v"))
		r.details["ddnsgo_binary_version"] = strings.TrimSpace(nrCommand("/koolshare/bin/ddnsgo", "-v"))
		r.record("three_genuine_version_updates_preserve_configuration_and_restart_running_ddnsgo")
		for _, module := range []string{"aliddns", "ddnsto"} {
			r.callback(module, "1", map[string]string{module + "_enable": "0"})
			r.record(module + "_real_disabled_configuration_callback")
		}
		for i := 0; i < 4; i++ {
			r.callback("ddnsgo", "status", nil)
		}
		r.callback("ddnsgo", "version", nil)
		r.record("ddnsgo_real_status_callback_and_uu_coexist")
		r.ddnsgoStart("1")
		if !strings.Contains(nrCommand("/bin/sh", "-c", ". /koolshare/scripts/base.sh; perpls"), "ddnsgo") {
			panic("DDNS-Go not under actual perp supervisor")
		}
		r.record("ddnsgo_real_perp_supervision_shares_center_supervisor_with_uu_alive")
		hook := []byte("#!/bin/sh\nwhich sh > /tmp/real-wan-shell\nsh -c 'echo hook-ok' > /tmp/real-wan-result\n")
		nrMust(os.WriteFile("/jffs/scripts/wan-start", hook, 0700))
		before := r.ddnsgoAlive()
		nrCommand("/bin/sh", "/usr/libexec/localmod/dispatch.sh", "wan-start", "0")
		if strings.TrimSpace(string(nrRead("/tmp/real-wan-shell"))) != "/bin/sh" || strings.TrimSpace(string(nrRead("/tmp/real-wan-result"))) != "hook-ok" || r.ddnsgoAlive() == before {
			panic("actual WAN hook/shell/plugin restart failed")
		}
		r.record("wan_hook_uses_official_shell_and_restarts_real_plugin_without_restarting_uu")
		nrCommand("/bin/sh", "/usr/libexec/localmod/dispatch.sh", "nat-start")
		r.ddnsgoAlive()
		r.record("real_ddnsgo_nat_hook_preserves_private_api_and_uu")
		nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "restart")
		coBackendReady()
		r.ddnsgoAlive()
		r.allFiles()
		if realDB("aliddns_domain") != "retained.invalid" || !bytes.Equal(config, nrRead("/koolshare/configs/ddnsgo/default.yaml")) {
			panic("center restart lost real plugin configuration")
		}
		r.record("center_restart_restores_real_supervised_plugin_configuration_and_keeps_uu")
		for _, module := range []string{"aliddns", "ddnsto", "ddnsgo"} {
			r.uninstall(module, "updated")
		}
	} else {
		for _, module := range []string{"aliddns", "ddnsto", "ddnsgo"} {
			r.operation(module, "current", "fresh_current")
		}
		if realDB("ddnsgo_enable") != "0" || realDB("ddnsgo_watchdog") != "0" || realDB("ddnsgo_port") != "9876" || realDB("ddnsto_feat_disk_path_selected") != "" || realDB("aliddns_domain") != "" {
			panic("fresh install inherited removed plugin configuration")
		}
		r.record("fresh_current_install_defaults_are_unconfigured")
		r.details["ddnsto_binary_version"] = strings.TrimSpace(nrCommand("/koolshare/bin/ddnsto", "-v"))
		r.details["ddnsgo_binary_version"] = strings.TrimSpace(nrCommand("/koolshare/bin/ddnsgo", "-v"))
		for _, module := range []string{"aliddns", "ddnsto", "ddnsgo"} {
			r.uninstall(module, "fresh_current")
		}
	}
	r.details["uu_api_requests"] = u.calls.Load()
	r.details["uu_monitor_downloads"] = u.downloads.Load()
	r.details["uu_launches"] = strings.Count(string(nrRead("/tmp/owned-uu-launches")), "start\n")
	r.details["actual_process_helper_sha256"] = realSHA(nrRead("/koolshare/bin/start-stop-daemon"))
	r.details["native_wget_sha256"] = realSHA(nrRead("/usr/libexec/localmod/wget"))
	r.details["real_third_party_packages_executed"] = true
	r.details["real_uu_monitor_executed"] = false
	r.details["plugin_binaries_replaced_by_fixtures"] = false
	r.details["guest_architecture"] = strings.TrimSpace(nrCommand("/bin/uname", "-m"))
	report := map[string]any{"checks": r.checks, "details": r.details}
	b, e := json.Marshal(report)
	nrMust(e)
	fmt.Printf("REAL_PLUGIN_RESULT %s\n", b)
}
