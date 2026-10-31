package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/md5"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

type interruptPhase struct {
	Case       string `json:"case"`
	Initialize bool   `json:"initialize"`
	Boot       string `json:"boot"`
}

var irqPhase interruptPhase
var irqChecks []string
var irqConfig = []byte("token: synthetic-only\nlist: [one, two]\n")
var irqQuote = "first\nliteral=$HOME; $(touch /tmp/should-never-run)\n\"quoted\""

func irqSHA(b []byte) string { s := sha256.Sum256(b); return hex.EncodeToString(s[:]) }
func irqLoad()               { nrMust(json.Unmarshal(nrRead("/work/build/interrupt-phase.json"), &irqPhase)) }
func irqRecord(name string)  { irqChecks = append(irqChecks, name); fmt.Println("PASS", name) }
func irqResult() {
	b, e := json.Marshal(map[string]any{"case": irqPhase.Case, "boot": irqPhase.Boot, "checks": irqChecks})
	nrMust(e)
	fmt.Printf("INTERRUPT_RESULT %s\n", b)
}
func irqUUData(root string) {
	for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-cache/uu.tar.gz.md5", "/jffs/uu-state/user.dat"} {
		expected := []byte("interrupt-uu-preserve:" + p)
		if !bytes.Equal(nrRead(root+p), expected) {
			panic("UU persistent data changed: " + p)
		}
	}
}
func irqOriginal(root string) {
	if !bytes.Equal(nrRead(root+"/koolshare/configs/onlineprobe/active.yaml"), irqConfig) {
		panic("original plugin file lost")
	}
}
func irqAddReal(repo *onlineRepo) {
	var m struct {
		Packages []struct {
			Module  string `json:"module"`
			Phase   string `json:"phase"`
			Version string `json:"catalog_version"`
			Path    string `json:"path"`
			SHA     string `json:"sha256"`
			MD5     string `json:"md5"`
		}
	}
	nrMust(json.Unmarshal(nrRead("/work/build/real_plugin_inputs.json"), &m))
	for _, p := range m.Packages {
		if p.Module != "ddnsgo" {
			continue
		}
		b := nrRead("/work/" + p.Path)
		if irqSHA(b) != p.SHA {
			panic("real package changed")
		}
		key := p.Module + "-" + p.Phase
		path := p.Module + "/" + p.Phase + ".tar.gz"
		repo.apps[key] = onlineApp{p.Module, p.Module, p.Version, p.MD5, path}
		repo.blobs["/"+path] = b
	}
}
func irqMigration(repo *onlineRepo, fresh bool) {
	module := "onlineprobe"
	if fresh {
		module = "freshprobe"
	}
	data := onlinePackage(module, "2.0", "v2")
	z, e := gzip.NewReader(bytes.NewReader(data))
	nrMust(e)
	defer z.Close()
	input := tar.NewReader(z)
	var out bytes.Buffer
	gz := gzip.NewWriter(&out)
	target := tar.NewWriter(gz)
	for {
		h, e := input.Next()
		if e == io.EOF {
			break
		}
		nrMust(e)
		b, e := io.ReadAll(input)
		nrMust(e)
		if h.Name == module+"/install.sh" {
			b = []byte(fmt.Sprintf(`#!/bin/sh
. /koolshare/scripts/base.sh
mkdir -p /koolshare/configs/%s
[ ! -f /koolshare/configs/%s/active.yaml ] || mv /koolshare/configs/%s/active.yaml /koolshare/configs/%s/migrating.yaml
dbus set %s_config=migration-in-progress
printf incomplete > /koolshare/configs/%s/active.yaml
# This owned fixture makes its intermediate state durable before SIGKILL.
dbus list __fixture_partial_commit__ >/dev/null
sync
touch /tmp/interrupt-install-reached
while :;do sleep 1;done
`, module, module, module, module, module, module))
			h.Size = int64(len(b))
		}
		nrMust(target.WriteHeader(h))
		_, e = target.Write(b)
		nrMust(e)
	}
	nrMust(target.Close())
	nrMust(gz.Close())
	b := out.Bytes()
	sum := md5.Sum(b)
	path := module + "/migration.tar.gz"
	repo.apps["migration"] = onlineApp{module, module, "2.0", hex.EncodeToString(sum[:]), path}
	repo.blobs["/"+path] = b
}
func irqDDNSAlive() {
	client := &http.Client{Timeout: time.Second}
	for i := 0; i < 80; i++ {
		res, e := client.Get("http://127.0.0.1:9876/")
		if e == nil {
			b, _ := io.ReadAll(res.Body)
			res.Body.Close()
			if res.StatusCode == 200 && strings.Contains(strings.ToLower(string(b)), "ddns") {
				return
			}
		}
		time.Sleep(50 * time.Millisecond)
	}
	panic("real DDNS-Go not restored/running")
}
func irqDB(key string) string {
	return strings.TrimSuffix(nrCommand("/usr/bin/dbus", "get", key), "\n")
}
func irqSet(key, value string) { nrCommand("/usr/bin/dbus", "set", key+"="+value) }
func irqWait(path string) {
	for i := 0; i < 1800; i++ {
		if _, e := os.Stat(path); e == nil {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	panic("fault gate not reached: " + path)
}
func irqArm(mode string) {
	nrMust(os.WriteFile("/tmp/txn-fault-mode", []byte(mode), 0600))
	nrMust(os.WriteFile("/tmp/txn-fault-armed", []byte("1"), 0600))
}
func irqPackageOffline(repo *onlineRepo) {
	irqPackageOfflineBlob(repo.blobs["/onlineprobe/migration.tar.gz"])
}
func irqPackageOfflineBlob(blob []byte) {
	// Use the same owned migration files, with the HND marker expected by the UI.
	z, e := gzip.NewReader(bytes.NewReader(blob))
	nrMust(e)
	defer z.Close()
	input := tar.NewReader(z)
	var out bytes.Buffer
	gz := gzip.NewWriter(&out)
	t := tar.NewWriter(gz)
	for {
		h, e := input.Next()
		if e == io.EOF {
			break
		}
		nrMust(e)
		b, e := io.ReadAll(input)
		nrMust(e)
		nrMust(t.WriteHeader(h))
		_, e = t.Write(b)
		nrMust(e)
	}
	nrMust(t.WriteHeader(&tar.Header{Name: "onlineprobe/.valid", Mode: 0644, Size: 3, Typeflag: tar.TypeReg}))
	_, e = t.Write([]byte("hnd"))
	nrMust(e)
	nrMust(t.Close())
	nrMust(gz.Close())
	nrMust(os.WriteFile("/tmp/upload/onlineprobe.tar.gz", out.Bytes(), 0600))
}
func interruptWorker() {
	irqLoad()
	defer func() {
		if e := recover(); e != nil {
			for _, p := range []string{"/tmp/.localmod/bootstrap.log", "/tmp/upload/soft_install_log.txt", "/tmp/upload/soft_log.txt", "/var/log/perpd/current"} {
				b, _ := os.ReadFile(p)
				fmt.Printf("DIAGNOSTIC %s\n%s\n", p, b)
			}
			panic(e)
		}
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 230*time.Second)
	defer cancel()
	repo := onlineRepository()
	defer repo.close()
	irqAddReal(repo)
	s := nrStart(ctx, "interrupt-"+irqPhase.Boot, true)
	defer s.stop()
	s.login()
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	coUUPage(s)
	t := &onlineTest{s: s, repo: repo, uu: u, id: 94000, sentinels: map[string][]byte{}, archive: nrRead("/jffs/cert.tgz")}
	if irqPhase.Initialize {
		t.operation("v1", "", true)
		irqSet("onlineprobe_config", "pre-interruption-user-value")
		irqSet("localmod_userdata_quote", irqQuote)
		irqSet("peer_config", "unrelated-preserved")
		nrMust(os.MkdirAll("/koolshare/configs/onlineprobe", 0700))
		nrMust(os.WriteFile("/koolshare/configs/onlineprobe/active.yaml", irqConfig, 0600))
		nrMust(os.WriteFile("/koolshare/configs/onlineprobe/binary.dat", []byte{0, 1, 2, 255, 128, 10}, 0600))
		t.operation("ddnsgo-old", "", true)
		nrMust(os.WriteFile("/koolshare/configs/ddnsgo/default.yaml", []byte("notallowwanaccess: true\n# retained-real-plugin\n"), 0600))
		t.rpc("ddnsgo_config.sh", "web_submit", map[string]string{"ddnsgo_enable": "1", "ddnsgo_watchdog": "1", "ddnsgo_publicswitch": "0", "ddnsgo_port": "9876", "ddnsgo_localcheck": "300", "ddnsgo_wancheck": "5", "ddnsgo_skipverify": "0"})
		irqDDNSAlive()
		for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-cache/uu.tar.gz.md5", "/jffs/uu-state/user.dat"} {
			nrMust(os.MkdirAll(filepath.Dir(p), 0700))
			nrMust(os.WriteFile(p, []byte("interrupt-uu-preserve:"+p), 0600))
		}
		nrMust(os.WriteFile("/jffs/.fixture-cert.sha", []byte(irqSHA(nrRead("/jffs/cert.tgz"))), 0600))
		nrCommand("/usr/bin/dbus", "list", "__fixture_commit__")
		syscall.Sync()
		irqRecord("foundation_real_plugin_configuration_and_uu_synced")
		irqResult()
		return
	}
	irqUUData("")
	irqOriginal("")
	irqDDNSAlive()
	if irqSHA(nrRead("/jffs/cert.tgz")) != string(nrRead("/jffs/.fixture-cert.sha")) {
		panic("TLS persistent archive changed across VM restart")
	}
	if !bytes.Equal(nrRead("/koolshare/configs/onlineprobe/binary.dat"), []byte{0, 1, 2, 255, 128, 10}) {
		panic("binary plugin configuration changed")
	}
	nrMust(os.WriteFile("/tmp/uu.tar.gz", []byte("owned-uu-temporary-download"), 0600))
	if irqDB("localmod_userdata_quote") != irqQuote || irqDB("peer_config") != "unrelated-preserved" {
		panic("literal database values lost or evaluated")
	}
	if irqPhase.Boot == "verify" {
		committed := irqPhase.Case == "after-commit" || irqPhase.Case == "committed-cleanup"
		want := "1.0"
		if committed {
			want = "2.0"
		}
		if irqDB("softcenter_module_onlineprobe_version") != want {
			panic("wrong version after reboot: " + irqDB("softcenter_module_onlineprobe_version"))
		}
		if irqDB("onlineprobe_config") != "pre-interruption-user-value" {
			panic("plugin database configuration not restored")
		}
		if _, e := os.Stat("/jffs/.localmod/plugin-txn/active"); !os.IsNotExist(e) {
			panic("recovery still blocks writes")
		}
		if _, e := os.Stat("/tmp/should-never-run"); !os.IsNotExist(e) {
			panic("snapshot data was evaluated")
		}
		irqRecord("fresh_vm_restores_exact_config_files_literal_database_and_version")
		if !committed && irqPhase.Case != "download" && irqPhase.Case != "checkpoint" {
			histories, e := filepath.Glob("/jffs/.localmod/plugin-txn/recovered-*")
			nrMust(e)
			if len(histories) != 1 {
				panic("interrupted state history missing")
			}
			if irqPhase.Case == "kill-parent" || irqPhase.Case == "kill-tree" || irqPhase.Case == "offline" {
				if string(nrRead(histories[0]+"/failed-center/configs/onlineprobe/active.yaml")) != "incomplete" {
					panic("interrupted config not retained")
				}
			}
			if irqPhase.Case == "fresh" {
				if irqDB("freshprobe_config") != "" || irqDB("softcenter_module_freshprobe_install") != "" {
					panic("partial new plugin registration survived rollback")
				}
				if _, e := os.Stat("/koolshare/configs/freshprobe"); !os.IsNotExist(e) {
					panic("partial fresh plugin still active")
				}
				if string(nrRead(histories[0]+"/failed-center/configs/freshprobe/active.yaml")) != "incomplete" {
					panic("new uncommitted data lost")
				}
			}
			irqRecord("interrupted_new_state_retained_in_private_history")
		}
		if irqPhase.Case == "real-ddnsgo" && irqDB("softcenter_module_ddnsgo_version") != "1.28.0" {
			panic("real plugin did not roll back")
		}
		if !bytes.Equal(nrRead("/koolshare/configs/ddnsgo/default.yaml"), []byte("notallowwanaccess: true\n# retained-real-plugin\n")) {
			panic("real plugin file changed")
		}
		irqRecord("real_ddnsgo_autostart_and_local_page_restored")
		// A retry after recovery must be possible, using the authenticated API.
		if irqPhase.Case == "offline" {
			irqPackageOfflineBlob(onlinePackage("onlineprobe", "2.0", "v2"))
			t.rpc("ks_tar_install.sh", "", map[string]string{"soft_name": "onlineprobe.tar.gz"})
			complete := false
			deadline := time.Now().Add(90 * time.Second)
			for time.Now().Before(deadline) {
				_, e := os.Stat("/tmp/.localmod/plugin-operation.lock")
				b, _ := os.ReadFile("/tmp/upload/soft_log.txt")
				if os.IsNotExist(e) && strings.Contains(string(b), "XU6J03M6") {
					complete = true
					break
				}
				time.Sleep(50 * time.Millisecond)
			}
			if !complete || irqDB("softcenter_installing_result") != "0" || irqDB("softcenter_module_onlineprobe_version") != "0.1" || string(nrRead("/koolshare/onlineprobe/version")) != "2.0" {
				panic("offline retry failed or retained stale version registration")
			}
			if string(nrRead("/tmp/uu.tar.gz")) != "owned-uu-temporary-download" {
				panic("offline retry removed UU temporary archive")
			}
		} else if irqPhase.Case == "real-ddnsgo" {
			t.operation("ddnsgo-current", "", true)
			if irqDB("softcenter_module_ddnsgo_version") != "1.29.0" || !bytes.Equal(nrRead("/koolshare/configs/ddnsgo/default.yaml"), []byte("notallowwanaccess: true\n# retained-real-plugin\n")) {
				panic("real plugin retry lost version or user configuration")
			}
			irqDDNSAlive()
		} else if irqPhase.Case == "fresh" {
			blob := onlinePackage("freshprobe", "1.0", "v1")
			sum := md5.Sum(blob)
			repo.apps["fresh-normal"] = onlineApp{"freshprobe", "Fresh retry", "1.0", hex.EncodeToString(sum[:]), "freshprobe/retry.tar.gz"}
			repo.blobs["/freshprobe/retry.tar.gz"] = blob
			t.operation("fresh-normal", "", true)
			if irqDB("softcenter_module_freshprobe_version") != "1.0" || string(nrRead("/koolshare/freshprobe/version")) != "1.0" {
				panic("fresh plugin retry did not install")
			}
		} else {
			kind, version := "v2", "2.0"
			if committed {
				kind, version = "retry", "3.0"
			}
			t.operation(kind, "", true)
			if irqDB("softcenter_module_onlineprobe_version") != version || string(nrRead("/koolshare/onlineprobe/version")) != version {
				panic("retry did not commit a changed version")
			}
		}
		irqOriginal("")
		if irqDB("onlineprobe_config") != "pre-interruption-user-value" || irqDB("localmod_userdata_quote") != irqQuote {
			panic("retry changed user configuration")
		}
		irqUUData("")
		coUUAlive(u.pid)
		coPrivateDenied()
		irqRecord("retry_after_recovery_commits_and_keeps_uu_data_and_private_api")
		irqResult()
		return
	}
	if irqPhase.Case == "no-space" {
		irqArm("no-space")
		t.operation("v2", "", false)
		irqOriginal("")
		irqUUData("")
		if irqDB("softcenter_module_onlineprobe_version") != "1.0" {
			panic("out-of-space checkpoint ran installer")
		}
		if _, e := os.Stat("/jffs/.localmod/plugin-txn/active"); !os.IsNotExist(e) {
			panic("preparation failure retained active transaction")
		}
		irqRecord("checkpoint_write_enospc_aborts_before_mutation_and_preserves_data")
		os.Remove("/tmp/txn-fault-armed")
		t.operation("v2", "", true)
		irqOriginal("")
		irqUUData("")
		irqRecord("retry_after_preparation_failure_succeeds")
		irqResult()
		return
	}
	switch irqPhase.Case {
	case "download":
		t.begin("hold", "")
		select {
		case <-repo.holding:
		case <-time.After(5 * time.Second):
			panic("download not held")
		}
		irqRecord("download_interrupted_before_mutation")
		irqResult()
		nrMust(os.WriteFile("/tmp/txn-fault-gate", []byte("download-held"), 0600))
	case "checkpoint", "before-commit", "after-commit", "committed-cleanup":
		irqArm(irqPhase.Case)
		t.begin("v2", "")
	case "real-ddnsgo":
		// Keep the authentic package unchanged; pause the real cp boundary after
		// its new ARM binary has been copied, before scripts/version registration.
		nrMust(os.WriteFile("/tmp/real-cp-fault-armed", []byte("1"), 0600))
		t.begin("ddnsgo-current", "")
	default:
		irqMigration(repo, irqPhase.Case == "fresh")
		if irqPhase.Case == "offline" {
			irqPackageOffline(repo)
			t.rpc("ks_tar_install.sh", "", map[string]string{"soft_name": "onlineprobe.tar.gz"})
		} else {
			t.begin("migration", "")
		}
		irqWait("/tmp/interrupt-install-reached")
		pid, e := strconv.Atoi(strings.TrimSpace(string(nrRead("/tmp/.localmod/plugin-operation.lock/pid"))))
		nrMust(e)
		if irqPhase.Case == "kill-parent" {
			nrMust(syscall.Kill(pid, syscall.SIGKILL))
		} else {
			interruptKillTree(pid)
		}
		logPath := "/tmp/upload/soft_install_log.txt"
		if irqPhase.Case == "offline" {
			logPath = "/tmp/upload/soft_log.txt"
		}
		reported := false
		for i := 0; i < 80; i++ {
			b, _ := os.ReadFile(logPath)
			if strings.Contains(string(b), "XU6J03M6") {
				reported = true
				break
			}
			time.Sleep(50 * time.Millisecond)
		}
		if !reported {
			panic("owner death was not reported in the active installation log")
		}
		payload := `{"id":99999,"method":"coexist_probe.sh","params":[],"fields":{"peer_config":"must-not-change"}}`
		code, _ := s.request("POST", "/_api/", payload)
		if code != 423 || irqDB("peer_config") != "unrelated-preserved" {
			panic("interrupted transaction did not block new writes")
		}
		irqUUData("")
		coUUAlive(u.pid)
		coUUPage(s)
		if string(nrRead("/tmp/uu.tar.gz")) != "owned-uu-temporary-download" {
			panic("installer removed UU temporary download")
		}
		irqRecord("killed_installer_blocks_writes_without_changing_uu_or_peer_data")
		irqResult()
		nrMust(os.WriteFile("/tmp/txn-fault-gate", []byte("killed-mutation"), 0600))
	}
	for {
		time.Sleep(time.Second)
	}
}
func interruptController() {
	irqLoad()
	mode := irqPhase.Case
	if irqPhase.Boot == "recover-cut" {
		mode = "recover-center"
	}
	if irqPhase.Boot == "recover-db-cut" {
		mode = "recover-database"
	}
	nrMust(os.WriteFile("/router/tmp/txn-fault-mode", []byte(mode), 0600))
	if strings.HasPrefix(irqPhase.Boot, "recover-") {
		nrMust(os.WriteFile("/router/tmp/txn-fault-armed", []byte("1"), 0600))
	}
	// Real package scripts are untouched; this is a guest-only command boundary.
	wrapper := `#!/bin/sh
/bin/busybox cp "$@"
status=$?
if [ "$status" = 0 ] && [ -f /tmp/real-cp-fault-armed ]; then
 case "$*" in *'/tmp/ddnsgo/bin/'*) printf real-ddnsgo-binary-copied > /tmp/txn-fault-gate; while :;do sleep 1;done;; esac
fi
exit "$status"
`
	nrMust(os.Remove("/router/bin/cp"))
	nrMust(os.WriteFile("/router/bin/cp", []byte(wrapper), 0755))
	cmd := exec.Command("/bin/chroot", "/router", "/bin/sh", "/work/build/real_plugins_setup.sh")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	nrMust(cmd.Start())
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	for {
		select {
		case e := <-done:
			nrMust(e)
			return
		case <-time.After(50 * time.Millisecond):
			if b, e := os.ReadFile("/router/tmp/txn-fault-gate"); e == nil && len(b) > 0 {
				irqUUData("/router")
				irqRecord("abrupt_vm_cut_keeps_synced_uu_files")
				if irqSHA(nrRead("/router/jffs/cert.tgz")) != string(nrRead("/router/jffs/.fixture-cert.sha")) {
					panic("TLS archive changed at interruption boundary")
				}
				if irqPhase.Boot == "cut" {
					pid, e := strconv.Atoi(strings.TrimSpace(string(nrRead("/router/tmp/owned-uu-worker.pid"))))
					nrMust(e)
					nrMust(syscall.Kill(pid, 0))
					before := len(nrRead("/router/tmp/owned-uu-heartbeat"))
					alive := false
					for i := 0; i < 40; i++ {
						time.Sleep(50 * time.Millisecond)
						if len(nrRead("/router/tmp/owned-uu-heartbeat")) > before {
							alive = true
							break
						}
					}
					if !alive || string(nrRead("/router/tmp/owned-uu-launches")) != "start\n" {
						panic("UU stopped or restarted during installation")
					}
					irqRecord("uu_heartbeat_continues_with_one_launch_at_fault_boundary")
				}
				if irqPhase.Boot == "recover-cut" {
					if _, e := os.Stat("/router/jffs/.localmod/plugin-txn/active/center/configs/onlineprobe/active.yaml"); e != nil {
						panic("checkpoint disappeared during interrupted recovery")
					}
					irqRecord("recovery_can_be_interrupted_after_quarantine_with_checkpoint_retained")
				}
				if irqPhase.Boot == "recover-db-cut" {
					irqOriginal("/router")
					if _, e := os.Stat("/router/jffs/.localmod/plugin-txn/active/database/values.bin"); e != nil {
						panic("logical checkpoint lost during partial replay")
					}
					before, e := os.Stat("/router/jffs/.localmod/ksdb")
					nrMust(e)
					probe := exec.Command("/bin/chroot", "/router", "/usr/libexec/localmod/plugin-txn", "recover")
					out, err := probe.CombinedOutput()
					after, e := os.Stat("/router/jffs/.localmod/ksdb")
					nrMust(e)
					if err == nil || before.Sys().(*syscall.Stat_t).Ino != after.Sys().(*syscall.Stat_t).Ino {
						panic(fmt.Sprintf("same-boot recovery accepted/moved a live database: exit=%v before=%d after=%d output=%s", err, before.Sys().(*syscall.Stat_t).Ino, after.Sys().(*syscall.Stat_t).Ino, out))
					}
					irqRecord("duplicate_same_boot_recovery_refused_without_moving_live_database")
					irqRecord("partial_database_replay_keeps_original_checkpoint_and_restored_files")
				}
				fmt.Printf("FAULT_BOUNDARY %s\n", b)
				irqResult()
				fmt.Println("INTERRUPT_CUT_READY")
				for {
					time.Sleep(time.Second)
				}
			}
		}
	}
}
