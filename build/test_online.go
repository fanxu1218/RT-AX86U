package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/md5"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"log"
	"math/big"
	"net"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

type onlineApp struct {
	Name    string `json:"name"`
	Title   string `json:"title"`
	Version string `json:"version"`
	MD5     string `json:"md5"`
	TarURL  string `json:"tar_url"`
}
type onlineRepo struct {
	apps        map[string]onlineApp
	blobs       map[string][]byte
	mu          sync.Mutex
	requests    map[string]int
	hold        chan struct{}
	holding     chan struct{}
	server, bad *http.Server
	client      *http.Client
}

func onlineCertificate() (tls.Certificate, []byte) {
	key, e := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	nrMust(e)
	cert := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "owned-plugin-repository"}, IPAddresses: []net.IP{net.ParseIP("127.0.0.1")}, DNSNames: []string{"repo.fixture.test"}, NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}, IsCA: true, BasicConstraintsValid: true}
	der, e := x509.CreateCertificate(rand.Reader, cert, cert, &key.PublicKey, key)
	nrMust(e)
	return tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
}
func onlinePackage(module, version, kind string) []byte {
	install := fmt.Sprintf(`#!/bin/sh
mkdir -p /koolshare/%s /koolshare/scripts /koolshare/webs
cp /tmp/%s/webs/Module_%s.asp /koolshare/webs/
cp /tmp/%s/scripts/* /koolshare/scripts/
chmod 755 /koolshare/scripts/%s*.sh
printf '%%s' '%s' > /koolshare/%s/version
if [ -z "$(dbus get %s_enable)" ];then dbus set %s_enable=1;fi
if [ ! -s /tmp/owned-online-plugin.pid ] || ! kill -0 "$(cat /tmp/owned-online-plugin.pid)" 2>/dev/null;then
 /bin/sh /koolshare/scripts/%s_worker.sh </dev/null >/tmp/owned-online-plugin.log 2>&1 &
fi
`, module, module, module, module, module, version, module, module, module, module)
	if kind == "installfail" {
		install = "#!/bin/sh\nexit 9\n"
	}
	callback := fmt.Sprintf(`#!/bin/sh
. /koolshare/scripts/base.sh
if [ "$2" = stop ];then
 [ ! -f /tmp/owned-online-plugin.pid ] || kill "$(cat /tmp/owned-online-plugin.pid)" 2>/dev/null
 dbus set %s_enable=0
else
 dbus set %s_runtime="$(cat /koolshare/%s/version):$(dbus get %s_input)"
fi
http_response "$ID"
`, module, module, module, module)
	worker := fmt.Sprintf("#!/bin/sh\ntrap 'exit 0' TERM INT\nprintf '%%s\\n' \"$$\" > /tmp/owned-online-plugin.pid\nwhile :;do cat /koolshare/%s/version >> /tmp/owned-online-plugin-heartbeat;sleep 0.1;done\n", module)
	uninstall := fmt.Sprintf("#!/bin/sh\n[ ! -f /tmp/owned-online-uninstall-fail ] || exit 9\n[ ! -f /tmp/owned-online-plugin.pid ] || kill \"$(cat /tmp/owned-online-plugin.pid)\" 2>/dev/null\nrm -rf /koolshare/%s\nrm -f /koolshare/scripts/%s.sh /koolshare/scripts/%s_worker.sh /koolshare/webs/Module_%s.asp /tmp/owned-online-plugin.pid\nprintf removed > /tmp/owned-online-uninstalled\n", module, module, module, module)
	if kind == "installfail" {
		uninstall += "# replacement from failed update must not replace old uninstaller\n"
	}
	files := map[string]string{"install.sh": install, "uninstall.sh": uninstall, "webs/Module_" + module + ".asp": "<html>skin=fixture online-plugin-" + version + "</html>", "scripts/" + module + ".sh": callback, "scripts/" + module + "_worker.sh": worker}
	if kind == "missing" {
		delete(files, "install.sh")
	}
	if kind == "wrongprefix" {
		module = "other-owned-fixture"
	}
	var buffer bytes.Buffer
	z := gzip.NewWriter(&buffer)
	t := tar.NewWriter(z)
	for name, body := range files {
		nrMust(t.WriteHeader(&tar.Header{Name: module + "/" + name, Mode: 0755, Size: int64(len(body)), Typeflag: tar.TypeReg}))
		_, e := t.Write([]byte(body))
		nrMust(e)
	}
	nrMust(t.Close())
	nrMust(z.Close())
	if kind == "corrupt" {
		return []byte("owned-corrupt-archive")
	}
	return buffer.Bytes()
}
func onlineRepository() *onlineRepo {
	repo := &onlineRepo{apps: map[string]onlineApp{}, blobs: map[string][]byte{}, requests: map[string]int{}, hold: make(chan struct{}), holding: make(chan struct{})}
	for _, kind := range []string{"v1", "v2", "retry", "installfail", "missing", "wrongprefix", "corrupt", "hold", "second"} {
		module, version := "onlineprobe", "2.0"
		if kind == "v1" {
			version = "1.0"
		}
		if kind == "retry" {
			version = "3.0"
		}
		if kind == "second" {
			module, version = "secondprobe", "1.0"
		}
		blob := onlinePackage(module, version, kind)
		sum := md5.Sum(blob)
		path := module + "/" + kind + ".tar.gz"
		repo.apps[kind] = onlineApp{module, "Owned Online Probe", version, hex.EncodeToString(sum[:]), path}
		repo.blobs["/"+path] = blob
	}
	a := repo.apps["v2"]
	a.MD5 = strings.Repeat("0", 32)
	repo.apps["badmd5"] = a
	a = repo.apps["v2"]
	a.TarURL = "onlineprobe/notfound.tar.gz"
	repo.apps["notfound"] = a
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/koolcenter/app.json.js" {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]any{"apps": []onlineApp{repo.apps[r.URL.Query().Get("kind")]}})
			return
		}
		repo.mu.Lock()
		repo.requests[r.URL.Path]++
		count := repo.requests[r.URL.Path]
		repo.mu.Unlock()
		blob, ok := repo.blobs[r.URL.Path]
		if !ok {
			w.WriteHeader(404)
			return
		}
		if strings.Contains(r.URL.Path, "/hold.") {
			close(repo.holding)
			select {
			case <-repo.hold:
			case <-time.After(8 * time.Second):
				w.WriteHeader(503)
				return
			}
		}
		if strings.Contains(r.URL.Path, "/retry.") && count == 1 {
			w.Header().Set("Content-Length", strconv.Itoa(len(blob)))
			w.Write(blob[:len(blob)/2])
			return
		}
		w.Write(blob)
	})
	cert, ca := onlineCertificate()
	nrMust(os.WriteFile("/tmp/online-repo-ca.pem", ca, 0600))
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(ca) {
		panic("repository CA parse")
	}
	repo.client = &http.Client{Transport: &http.Transport{TLSClientConfig: &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12}}, Timeout: 2 * time.Second}
	repo.server = &http.Server{Handler: handler, ErrorLog: log.New(io.Discard, "", 0)}
	listener, e := net.Listen("tcp4", "127.0.0.1:35001")
	nrMust(e)
	go repo.server.Serve(tls.NewListener(listener, &tls.Config{Certificates: []tls.Certificate{cert}, MinVersion: tls.VersionTLS12}))
	bad, _ := onlineCertificate()
	repo.bad = &http.Server{Handler: handler, ErrorLog: log.New(io.Discard, "", 0)}
	listener, e = net.Listen("tcp4", "127.0.0.1:35002")
	nrMust(e)
	go repo.bad.Serve(tls.NewListener(listener, &tls.Config{Certificates: []tls.Certificate{bad}, MinVersion: tls.VersionTLS12}))
	return repo
}
func (r *onlineRepo) catalog(kind string) onlineApp {
	res, e := r.client.Get("https://repo.fixture.test:35001/koolcenter/app.json.js?kind=" + kind)
	nrMust(e)
	defer res.Body.Close()
	if res.TLS == nil || len(res.TLS.VerifiedChains) == 0 {
		panic("catalog TLS not verified")
	}
	var d struct {
		Apps []onlineApp `json:"apps"`
	}
	nrMust(json.NewDecoder(res.Body).Decode(&d))
	if len(d.Apps) != 1 {
		panic("catalog contract")
	}
	return d.Apps[0]
}
func (r *onlineRepo) count(path string) int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.requests["/"+path]
}
func (r *onlineRepo) close() { r.server.Close(); r.bad.Close(); r.client.CloseIdleConnections() }

type onlineUU struct {
	cmd              *exec.Cmd
	server           *http.Server
	log              *os.File
	pid              int
	calls, downloads atomic.Int32
}

func onlineUUStart(ctx context.Context) *onlineUU {
	u := &onlineUU{}
	worker := []byte("#!/bin/sh\ntrap 'exit 0' TERM INT\nprintf '%s\\n' \"$$\" > /tmp/owned-uu-worker.pid\nwhile :;do printf tick >> /tmp/owned-uu-heartbeat;sleep 0.1;done\n")
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
	u.log, e = os.Create("/work/build/online-" + os.Args[1] + "-ntp.log")
	nrMust(e)
	u.cmd = exec.CommandContext(ctx, "/usr/bin/qemu-arm", "-0", "ntp", "-L", "/work/build/casefs/official_rootfs", "-E", "LD_PRELOAD=/work/build/rc_bridge.so:/work/build/native_hw_fixture.so:/work/build/native_uu_transport.so", "/usr/libexec/localmod/rc.vendor")
	u.cmd.Env = append(os.Environ(), "NATIVE_UU_CASE=1", "NATIVE_UU_TERRITORY=CN/01", "NATIVE_UU_MODE=1")
	u.cmd.Stdout = u.log
	u.cmd.Stderr = u.log
	nrMust(u.cmd.Start())
	ready := false
	for i := 0; i < 180; i++ {
		if _, e := os.Stat("/tmp/native-ntp-idle"); e == nil {
			ready = true
			break
		}
		time.Sleep(30 * time.Millisecond)
	}
	if !ready {
		panic("native NTP not ready")
	}
	nrMust(os.WriteFile("/tmp/native-ntp-synced", []byte("1"), 0600))
	coSync(u.cmd)
	for i := 0; i < 100; i++ {
		if b, e := os.ReadFile("/tmp/owned-uu-worker.pid"); e == nil {
			u.pid, e = strconv.Atoi(strings.TrimSpace(string(b)))
			nrMust(e)
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if u.pid == 0 {
		panic("owned UU worker missing")
	}
	coUUAlive(u.pid)
	return u
}
func (u *onlineUU) close() {
	if u.cmd == nil {
		return
	}
	if u.pid != 0 {
		syscall.Kill(u.pid, syscall.SIGTERM)
	}
	u.cmd.Process.Kill()
	u.cmd.Wait()
	u.server.Close()
	u.log.Close()
	u.cmd = nil
}

type onlineTest struct {
	s         *nrServer
	repo      *onlineRepo
	uu        *onlineUU
	checks    []string
	sentinels map[string][]byte
	archive   []byte
	id        int
}

func (t *onlineTest) record(name string) {
	for path, expected := range t.sentinels {
		b, e := os.ReadFile(path)
		if e != nil || !bytes.Equal(b, expected) {
			panic("plugin operation changed unrelated/UU data: " + path)
		}
	}
	if !bytes.Equal(t.archive, nrRead("/jffs/cert.tgz")) {
		panic("plugin operation changed certificate archive")
	}
	coUUAlive(t.uu.pid)
	coUUPage(t.s)
	coPrivateDenied()
	if t.uu.calls.Load() != 1 || t.uu.downloads.Load() != 1 || string(nrRead("/tmp/owned-uu-launches")) != "start\n" {
		panic("UU restarted or redownloaded")
	}
	t.checks = append(t.checks, name)
}
func (t *onlineTest) rpc(method, action string, fields map[string]string) {
	t.id++
	payload, e := json.Marshal(map[string]any{"id": t.id, "method": method, "params": []string{action}, "fields": fields})
	nrMust(e)
	code, body := t.s.request("POST", "/_api/", string(payload))
	if code != 200 || !strings.Contains(body, strconv.Itoa(t.id)) {
		panic(fmt.Sprintf("online RPC ack %d %s", code, body))
	}
}
func (t *onlineTest) begin(kind, mirror string) {
	a := t.repo.catalog(kind)
	if mirror == "" {
		mirror = "https://repo.fixture.test:35001"
	}
	t.rpc("ks_app_install.sh", "ks_app_install", map[string]string{"softcenter_home_url": mirror, "softcenter_installing_todo": a.Name, "softcenter_installing_title": a.Title, "softcenter_installing_version": a.Version, "softcenter_installing_md5": a.MD5, "softcenter_installing_tar_url": a.TarURL})
}
func (t *onlineTest) wait(success bool) string {
	for i := 0; i < 150; i++ {
		code, body := t.s.request("GET", "/_temp/soft_install_log.txt", "")
		if code == 200 && strings.Contains(body, "XU6J03M6") {
			value := strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "softcenter_installing_result"))
			_, e := os.Stat("/tmp/.localmod/plugin-operation.lock")
			if os.IsNotExist(e) && value != "running" {
				if (value == "0") != success {
					panic(fmt.Sprintf("online result %s expected_success=%v: %s", value, success, body))
				}
				return body
			}
		}
		time.Sleep(40 * time.Millisecond)
	}
	panic("online operation did not finish: " + string(nrRead("/tmp/upload/soft_install_log.txt")))
}
func (t *onlineTest) operation(kind, mirror string, success bool) string {
	t.begin(kind, mirror)
	return t.wait(success)
}
func (t *onlineTest) plugin(version string) {
	if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "onlineprobe_config")) != "user-retained" {
		panic("plugin operation lost retained user configuration")
	}
	if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "softcenter_module_onlineprobe_version")) != version || string(nrRead("/koolshare/onlineprobe/version")) != version {
		panic("plugin file/registered version mismatch")
	}
	t.rpc("onlineprobe.sh", "probe", map[string]string{"onlineprobe_input": "actual-callback"})
	value := strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "onlineprobe_runtime"))
	if value != version+":actual-callback" {
		panic("installed plugin callback/version mismatch: " + value)
	}
	if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "onlineprobe_enable")) == "1" {
		pid, e := strconv.Atoi(strings.TrimSpace(string(nrRead("/tmp/owned-online-plugin.pid"))))
		nrMust(e)
		nrMust(syscall.Kill(pid, 0))
		before := len(nrRead("/tmp/owned-online-plugin-heartbeat"))
		alive := false
		for i := 0; i < 20; i++ {
			if len(nrRead("/tmp/owned-online-plugin-heartbeat")) > before {
				alive = true
				break
			}
			time.Sleep(20 * time.Millisecond)
		}
		if !alive {
			panic("owned plugin heartbeat stopped")
		}
	}
}
func (t *onlineTest) stopPlugin() {
	t.rpc("onlineprobe.sh", "stop", map[string]string{})
	for i := 0; i < 20; i++ {
		if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "onlineprobe_enable")) == "0" {
			return
		}
		time.Sleep(30 * time.Millisecond)
	}
	panic("owned plugin did not disable")
}
func (t *onlineTest) uninstall(success bool) string {
	t.rpc("ks_app_remove.sh", "ks_app_remove", map[string]string{"softcenter_installing_todo": "onlineprobe", "softcenter_installing_title": "Owned Online Probe"})
	return t.wait(success)
}
func main() {
	if len(os.Args) != 2 {
		panic("phase required")
	}
	phase := os.Args[1]
	ctx, cancel := context.WithTimeout(context.Background(), 48*time.Second)
	defer cancel()
	repo := onlineRepository()
	defer repo.close()
	s := nrStart(ctx, "online-"+phase, true)
	defer s.stop()
	s.login()
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "start")
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	test := &onlineTest{s: s, repo: repo, uu: u, id: 73000, sentinels: map[string][]byte{}, archive: nrRead("/jffs/cert.tgz")}
	for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-cache/uu.tar.gz.md5", "/tmp/uu.tar.gz", "/tmp/foreign-job/install.sh", "/tmp/.localmod/online-owned-sentinel"} {
		nrMust(os.MkdirAll(p[:strings.LastIndex(p, "/")], 0700))
		value := []byte("owned-coexistence-sentinel:" + p)
		nrMust(os.WriteFile(p, value, 0600))
		test.sentinels[p] = value
	}
	test.operation("v1", "", true)
	nrCommand("/usr/bin/dbus", "set", "onlineprobe_config=user-retained")
	test.plugin("1.0")
	test.record("https_catalog_native_wget_install_and_installed_callback_with_uu")
	switch phase {
	case "success":
		test.operation("v2", "", true)
		test.plugin("2.0")
		if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "onlineprobe_config")) != "user-retained" {
			panic("update lost user configuration")
		}
		test.record("online_update_changes_files_and_metadata_keeps_config_and_uu")
		test.operation("retry", "", true)
		test.plugin("3.0")
		if repo.count(repo.apps["retry"].TarURL) != 2 {
			panic("native wget retry not exercised")
		}
		test.record("native_wget_retries_interrupted_https_download_without_uu_restart")
		before := repo.count(repo.apps["retry"].TarURL)
		a := repo.apps["retry"]
		repo.apps["equal"] = a
		test.operation("equal", "", true)
		test.plugin("3.0")
		if repo.count(a.TarURL) != before {
			panic("same version downloaded again")
		}
		test.record("same_version_is_noop_with_uu_running")
		before = repo.count(repo.apps["v1"].TarURL)
		test.operation("v1", "", true)
		test.plugin("3.0")
		if repo.count(repo.apps["v1"].TarURL) != before {
			panic("downgrade downloaded")
		}
		test.record("downgrade_is_noop_and_retains_installed_version")
		body := test.uninstall(false)
		if !strings.Contains(body, "已经开启") {
			panic("enabled uninstall failed for wrong reason")
		}
		test.plugin("3.0")
		test.record("enabled_plugin_uninstall_rejected_without_affecting_uu")
		test.stopPlugin()
		test.uninstall(true)
		if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "softcenter_module_onlineprobe_install")) != "" {
			panic("successful uninstall kept registration")
		}
		if _, e := os.Stat("/koolshare/webs/Module_onlineprobe.asp"); !os.IsNotExist(e) {
			panic("successful uninstall kept page")
		}
		test.record("online_uninstall_removes_owned_plugin_and_registration_keeps_uu")
	case "errors":
		for _, c := range []struct{ kind, mirror, name, reason string }{{"notfound", "", "download_404_keeps_installed_plugin_and_uu", "下载错误"}, {"badmd5", "", "checksum_mismatch_never_executes_update", "校验不一致"}, {"corrupt", "", "corrupt_archive_fails_and_cleans_only_owned_stage", "目录不匹配或解压失败"}, {"wrongprefix", "", "wrong_package_root_rejected_before_extraction", "目录不匹配或解压失败"}, {"missing", "", "missing_install_script_keeps_old_plugin", "未找到 install.sh"}, {"v2", "https://repo.fixture.test:35002", "native_wget_rejects_untrusted_repository_certificate", "下载错误"}, {"v2", "https://bad-name.test:35001", "native_wget_rejects_repository_hostname_mismatch", "下载错误"}} {
			body := test.operation(c.kind, c.mirror, false)
			if !strings.Contains(body, c.reason) {
				panic("failure for wrong reason: " + c.name + " " + body)
			}
			if c.mirror != "" && !strings.Contains(body, "错误代码：5") {
				panic("TLS failure did not come from certificate validation: " + body)
			}
			test.plugin("1.0")
			test.record(c.name)
		}
		previous := nrRead("/koolshare/scripts/uninstall_onlineprobe.sh")
		test.operation("installfail", "", false)
		if !bytes.Equal(previous, nrRead("/koolshare/scripts/uninstall_onlineprobe.sh")) {
			panic("failed update lost/replaced previous uninstaller")
		}
		test.plugin("1.0")
		test.record("failed_update_preserves_previous_uninstaller_metadata_and_live_plugin")
		nrMust(os.Mkdir("/tmp/onlineprobe", 0700))
		nrMust(os.WriteFile("/tmp/onlineprobe/owned-existing", []byte("preserve-existing-stage"), 0600))
		test.operation("v2", "", false)
		if string(nrRead("/tmp/onlineprobe/owned-existing")) != "preserve-existing-stage" {
			panic("preexisting directory was removed")
		}
		nrMust(os.RemoveAll("/tmp/onlineprobe"))
		test.record("preexisting_stage_is_preserved_and_operation_refused")
		available, _ := strconv.Atoi(strings.TrimSpace(nrCommand("/bin/sh", "-c", "df -k /jffs | awk 'END {print $4}'")))
		if available < 4096 {
			panic("test JFFS unexpectedly full")
		}
		nrCommand("dd", "if=/dev/zero", "of=/jffs/.owned-online-fill", "bs=1024", "count="+strconv.Itoa(available-1024))
		body := test.operation("v2", "", false)
		nrMust(os.Remove("/jffs/.owned-online-fill"))
		if !strings.Contains(body, "小于2MB") {
			panic("low space failed for wrong reason")
		}
		test.plugin("1.0")
		test.record("low_jffs_space_update_returns_failure_and_keeps_old_state")
	case "concurrent":
		test.begin("hold", "")
		select {
		case <-repo.holding:
		case <-time.After(3 * time.Second):
			panic("held native download did not start")
		}
		test.begin("second", "")
		body := string(nrRead("/tmp/upload/soft_install_log.txt"))
		if !strings.Contains(body, "已有插件操作") {
			panic("overlapping operation was not rejected")
		}
		close(repo.hold)
		test.wait(true)
		test.plugin("2.0")
		if repo.count(repo.apps["second"].TarURL) != 0 || strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "softcenter_module_secondprobe_install")) != "" {
			panic("busy request ran/downloaded")
		}
		test.record("overlapping_online_rpc_rejected_without_overwriting_active_operation")
		test.stopPlugin()
		nrMust(os.WriteFile("/koolshare/scripts/onlineprobe_uninstall.sh", []byte("#!/bin/sh\nexit 9\n"), 0700))
		body = test.uninstall(false)
		if strings.Contains(body, "卸载成功") {
			panic("module-specific uninstall failure reported success")
		}
		test.plugin("2.0")
		test.record("module_specific_uninstall_failure_keeps_registration_and_config")
		nrMust(os.Remove("/koolshare/scripts/onlineprobe_uninstall.sh"))
		nrMust(os.WriteFile("/tmp/owned-online-uninstall-fail", []byte("1"), 0600))
		body = test.uninstall(false)
		if strings.Contains(body, "卸载成功") {
			panic("auto uninstall failure reported success")
		}
		test.plugin("2.0")
		test.record("copied_uninstall_failure_keeps_registration_and_config")
		nrMust(os.Remove("/tmp/owned-online-uninstall-fail"))
		nrMust(os.Remove("/koolshare/scripts/uninstall_onlineprobe.sh"))
		nrMust(os.WriteFile("/koolshare/scripts/onlineprobeextra.sh", []byte("neighbor-owned-script"), 0600))
		nrMust(os.WriteFile("/koolshare/init.d/S90onlineprobeextra.sh", []byte("neighbor-owned-hook"), 0600))
		nrCommand("/usr/bin/dbus", "set", "onlineprobeextra_config=neighbor-retained")
		test.uninstall(true)
		if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "onlineprobeextra_config")) != "neighbor-retained" || string(nrRead("/koolshare/scripts/onlineprobeextra.sh")) != "neighbor-owned-script" || string(nrRead("/koolshare/init.d/S90onlineprobeextra.sh")) != "neighbor-owned-hook" {
			panic("default uninstall removed another module's data")
		}
		test.record("default_uninstall_keeps_neighbor_module_prefixes_and_uu")
		for _, module := range []string{"softcenter", "koolcenter", "../uu"} {
			test.rpc("ks_app_install.sh", "ks_app_install", map[string]string{"softcenter_installing_todo": module, "softcenter_installing_title": "Blocked owned test"})
			test.wait(false)
			test.record("online_core_or_invalid_identifier_blocked_" + strings.ReplaceAll(module, "/", "_"))
		}
	default:
		panic("unknown online phase")
	}
	nrResult("online_"+phase, test.checks, map[string]any{"native_wget_sha256": fmt.Sprintf("%x", sha256.Sum256(nrRead("/usr/libexec/localmod/wget"))), "uu_api_requests": u.calls.Load(), "uu_monitor_downloads": u.downloads.Load(), "uu_launches": 1, "tls_verification_disabled": false, "real_uu_monitor_executed": false})
	fmt.Println("PASS online workflow via native HTTPS/session, actual httpdb/skipd, retained wget with verified local repository TLS, and owned plugin/UU workers")
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "stop")
	u.close()
	u.cmd = nil
	s.stop()
}
