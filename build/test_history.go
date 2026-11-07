package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const historyDir = "/jffs/.localmod/operations"

type historyEvent struct {
	Module, State, Kind string
	Code                int
	Sequence            uint64
	Persisted, Closed   bool
	Inferred            bool `json:"inferred_interruption"`
}
type historyReply struct {
	Schema  int
	Last    *historyEvent `json:"last_operation"`
	History struct {
		Status       string
		Available    bool
		Limit, Count int
		Error        string `json:"last_write_error"`
		Events       []historyEvent
	}
}

func historySHA(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func historyExit(args ...string) (int, string) {
	b, e := exec.Command(args[0], args[1:]...).CombinedOutput()
	if e == nil {
		return 0, string(b)
	}
	if x, ok := e.(*exec.ExitError); ok {
		return x.ExitCode(), string(b)
	}
	panic(e)
}
func historyRecord(module, state, kind string) {
	nrCommand("/usr/libexec/localmod/localmod-status", "record", module, state, "0", kind)
}
func historySlots() map[string]string {
	m := map[string]string{}
	entries, e := os.ReadDir(historyDir)
	nrMust(e)
	for _, x := range entries {
		if x.Name() == "lock" {
			continue
		}
		p := filepath.Join(historyDir, x.Name())
		st, e := os.Lstat(p)
		nrMust(e)
		if st.Mode().IsRegular() {
			m[x.Name()] = historySHA(nrRead(p))
		} else {
			m[x.Name()] = st.Mode().String()
		}
	}
	return m
}
func historySame(a, b map[string]string) bool { return mustHistoryJSON(a) == mustHistoryJSON(b) }
func mustHistoryJSON(v any) string            { b, e := json.Marshal(v); nrMust(e); return string(b) }
func historySnapshot() map[string][]byte {
	m := map[string][]byte{}
	for _, n := range []string{"slot0", "slot1", "lock"} {
		p := historyDir + "/" + n
		if b, e := os.ReadFile(p); e == nil {
			m[n] = b
		}
	}
	return m
}
func historyReset(saved map[string][]byte, name string) {
	// All files here belong to this disposable fixture. Firmware has no reset
	// endpoint: corruption/interrupted writes remain read-only in production.
	nrMust(os.Rename(historyDir, "/jffs/owned-history-"+name))
	nrMust(os.Mkdir(historyDir, 0700))
	for n, b := range saved {
		nrMust(os.WriteFile(historyDir+"/"+n, b, 0600))
	}
}
func historyOffline(t *onlineTest) {
	input := onlinePackage("onlineprobe", "2.1", "v2")
	z, e := gzip.NewReader(bytes.NewReader(input))
	nrMust(e)
	r := tar.NewReader(z)
	var out bytes.Buffer
	g := gzip.NewWriter(&out)
	w := tar.NewWriter(g)
	for {
		h, e := r.Next()
		if e == io.EOF {
			break
		}
		nrMust(e)
		if h.Name == "onlineprobe/install.sh" {
			body, e := io.ReadAll(r)
			nrMust(e)
			body = append(body, []byte("\ndbus set softcenter_module_onlineprobe_version=2.1\ndbus set onlineprobe_version=2.1\n")...)
			h.Size = int64(len(body))
			nrMust(w.WriteHeader(h))
			_, e = w.Write(body)
			nrMust(e)
		} else {
			nrMust(w.WriteHeader(h))
			_, e = io.Copy(w, r)
			nrMust(e)
		}
	}
	b := []byte("hnd\n")
	nrMust(w.WriteHeader(&tar.Header{Name: "onlineprobe/.valid", Size: int64(len(b)), Mode: 0644, Typeflag: tar.TypeReg}))
	_, e = w.Write(b)
	nrMust(e)
	nrMust(w.Close())
	nrMust(g.Close())
	nrMust(z.Close())
	nrMust(os.WriteFile("/tmp/upload/owned-history.tar.gz", out.Bytes(), 0600))
	nrMust(os.WriteFile("/tmp/upload/soft_log.txt", nil, 0600))
	t.rpc("ks_tar_install.sh", "", map[string]string{"soft_name": "owned-history.tar.gz"})
	for i := 0; i < 450; i++ {
		b, _ := os.ReadFile("/tmp/upload/soft_log.txt")
		_, e := os.Stat("/tmp/.localmod/plugin-operation.lock")
		if bytes.Contains(b, []byte("XU6J03M6")) && os.IsNotExist(e) {
			if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "softcenter_installing_result")) != "0" {
				panic(string(b))
			}
			return
		}
		time.Sleep(100 * time.Millisecond)
	}
	panic("history offline fixture timed out")
}
func main() {
	phase := strings.TrimSpace(string(nrRead("/work/build/history-phase")))
	defer func() {
		if v := recover(); v != nil {
			for _, p := range []string{"/tmp/upload/soft_install_log.txt", "/tmp/upload/soft_log.txt", "/tmp/.localmod/bootstrap.log"} {
				if b, e := os.ReadFile(p); e == nil {
					fmt.Printf("DIAGNOSTIC %s\n%s\n", p, b)
				}
			}
			panic(v)
		}
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Second)
	defer cancel()
	repo := onlineRepository()
	defer repo.close()
	s := nrStart(ctx, "history", true)
	defer s.stop()
	checks := map[string]bool{}
	must := func(ok bool, name string) {
		if !ok {
			panic(name)
		}
		checks[name] = true
		fmt.Println("PASS", name)
	}
	for _, p := range []string{"/_localmod/status", "/_localmod/diagnostics"} {
		code, _ := s.request("GET", p, "")
		must(code == 401, "native_auth_required_"+p)
	}
	s.login()
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	cert := nrRead("/jffs/cert.tgz")
	secret := "owned-history-secret-never-export-this"
	if phase == "init" {
		nrCommand("/usr/bin/dbus", "set", "journal_owned_config="+secret)
		for _, p := range []string{"/jffs/history-plugin-config", "/jffs/uu-state/history-account"} {
			nrMust(os.MkdirAll(filepath.Dir(p), 0700))
			f, e := os.OpenFile(p, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
			nrMust(e)
			_, e = f.WriteString(secret)
			nrMust(e)
			nrMust(f.Sync())
			nrMust(f.Close())
		}
	}
	retained := func() {
		for _, p := range []string{"/jffs/history-plugin-config", "/jffs/uu-state/history-account"} {
			must(string(nrRead(p)) == secret, "retained_"+filepath.Base(p))
		}
		must(strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "journal_owned_config")) == secret, "retained_native_database")
		must(bytes.Equal(cert, nrRead("/jffs/cert.tgz")), "certificate_retained_within_boot")
		coUUAlive(u.pid)
		coPrivateDenied()
	}
	query := func() historyReply {
		code, body := s.request("GET", "/_localmod/status", "")
		must(code == 200 && !strings.Contains(body, secret) && !strings.Contains(body, s.token) && !strings.Contains(body, "BEGIN CERTIFICATE"), "authenticated_redacted_summary")
		var r historyReply
		nrMust(json.Unmarshal([]byte(body), &r))
		must(r.Schema == 1 && r.History.Limit == 32 && r.History.Count <= 32, "bounded_compatible_json_schema")
		return r
	}
	if phase == "init" {
		for i := 0; i < 42; i++ {
			historyRecord(fmt.Sprintf("seed%02d", i), "finished", "manual")
		}
		r := query()
		must(r.History.Count == 32 && r.History.Events[0].Module == "seed41" && r.History.Events[31].Module == "seed10", "retention_keeps_latest_32_with_monotonic_sequences")
		for _, name := range []string{"slot0", "slot1"} {
			data := nrRead(historyDir + "/" + name)
			must(len(data) >= 72 && string(data[len(data)-72:len(data)-65]) == "SHA256 " && historySHA(data[:len(data)-72]) == string(data[len(data)-65:len(data)-1]), "independent_go_sha256_matches_"+name)
		}
		// A live owner transitions to inferred interruption after a real SIGKILL.
		owner := exec.Command("/bin/sh", "-c", `export LOCALMOD_OPERATION_OWNER=$$; /usr/libexec/localmod/localmod-status record owned-killed running 0 manual; echo ready > /tmp/history-owner-ready; while :;do sleep 1;done`)
		owner.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
		nrMust(owner.Start())
		for i := 0; i < 100; i++ {
			if _, e := os.Stat("/tmp/history-owner-ready"); e == nil {
				break
			}
			time.Sleep(20 * time.Millisecond)
		}
		r = query()
		must(r.Last != nil && r.Last.Module == "owned-killed" && r.Last.State == "running" && !r.Last.Inferred, "live_owner_remains_running")
		nrMust(syscall.Kill(-owner.Process.Pid, syscall.SIGKILL))
		_ = owner.Wait()
		before := historySlots()
		r = query()
		must(r.Last.State == "interrupted" && r.Last.Inferred, "killed_owner_inferred_without_history_write")
		must(historySame(before, historySlots()), "inference_is_readonly")
		historyRecord("paired", "running", "manual")
		historyRecord("paired", "finished", "manual")
		r = query()
		found := false
		for _, e := range r.History.Events {
			if e.Module == "paired" && e.State == "running" {
				found = e.Closed && !e.Inferred
			}
		}
		must(found, "completed_start_is_not_falsely_reported_interrupted")
		t := &onlineTest{s: s, repo: repo, uu: u, id: 151000, sentinels: map[string][]byte{}, archive: cert}
		t.operation("v1", "", true)
		nrCommand("/usr/bin/dbus", "set", "onlineprobe_config=user-retained")
		t.operation("v2", "", true)
		t.plugin("2.0")
		historyOffline(t)
		t.plugin("2.1")
		t.stopPlugin()
		t.uninstall(true)
		r = query()
		kinds := map[string]bool{}
		for _, e := range r.History.Events {
			if e.Module == "onlineprobe" && e.State == "finished" {
				kinds[e.Kind] = true
			}
		}
		must(kinds["install"] && kinds["update"] && kinds["offline"] && kinds["uninstall"], "actual_online_update_offline_uninstall_record_typed_events")
		baseline := historySnapshot()
		slots := historySlots()
		// Corrupt one/both copies: export only verified records, never truncate.
		nrMust(os.WriteFile(historyDir+"/slot0", []byte("owned-corrupt-slot"), 0600))
		bad := historySlots()
		code, _ := historyExit("/usr/libexec/localmod/localmod-status", "record", "rejected", "finished", "0")
		r = query()
		must(code != 0 && r.History.Status == "corrupt" && r.History.Count > 0 && historySame(bad, historySlots()), "single_corrupt_slot_preserved_and_verified_copy_readonly")
		// Logging failure must not turn a successful plugin install into failure.
		t.operation("v1", "", true)
		nrCommand("/usr/bin/dbus", "set", "onlineprobe_config=user-retained")
		t.plugin("1.0")
		t.stopPlugin()
		t.uninstall(true)
		must(historySame(bad, historySlots()), "history_corruption_does_not_block_plugin_install_or_uu")
		nrMust(os.WriteFile(historyDir+"/slot1", []byte("owned-corrupt-second-slot"), 0600))
		bad = historySlots()
		r = query()
		must(r.History.Count == 0 && r.History.Status == "corrupt" && !r.History.Available, "both_corrupt_slots_export_no_unverified_rows")
		code, _ = historyExit("/usr/libexec/localmod/localmod-status", "record", "rejected", "finished", "0")
		must(code != 0 && historySame(bad, historySlots()), "both_corrupt_slots_never_overwritten")
		historyReset(baseline, "corrupt")
		retained()
		// Parent-directory symlink and hardlink data must not be followed.
		nrMust(os.Rename(historyDir, "/jffs/owned-history-path-original"))
		nrMust(os.Symlink("/jffs/uu-state", historyDir))
		r = query()
		must(r.History.Status == "store-invalid" && r.History.Count == 0, "symlinked_history_store_denied")
		code, _ = historyExit("/usr/libexec/localmod/localmod-status", "record", "rejected", "finished", "0")
		must(code != 0, "symlinked_history_writer_denied")
		nrMust(os.Remove(historyDir))
		nrMust(os.Rename("/jffs/owned-history-path-original", historyDir))
		retained()
		nrMust(os.Remove(historyDir + "/slot0"))
		nrMust(os.Link("/jffs/uu-state/history-account", historyDir+"/slot0"))
		r = query()
		must(r.History.Status == "corrupt" && !strings.Contains(mustHistoryJSON(r), secret), "hardlinked_secret_not_read_or_overwritten")
		code, _ = historyExit("/usr/libexec/localmod/localmod-status", "record", "rejected", "finished", "0")
		must(code != 0, "hardlink_writer_denied")
		historyReset(baseline, "hardlink")
		retained()
		// Fill the actual owned ext4 filesystem, leaving less than the reserve.
		var fs syscall.Statfs_t
		nrMust(syscall.Statfs("/jffs", &fs))
		left := int64(fs.Bavail)*fs.Bsize - 65536
		f, e := os.OpenFile("/jffs/owned-history-pressure", os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		nrMust(e)
		chunk := make([]byte, 1024*1024)
		for left > 0 {
			n := int64(len(chunk))
			if n > left {
				n = left
			}
			_, e = f.Write(chunk[:n])
			nrMust(e)
			left -= n
		}
		nrMust(f.Close())
		code, _ = historyExit("/usr/libexec/localmod/localmod-status", "record", "space-test", "finished", "0")
		r = query()
		must(code != 0 && r.History.Status == "space-low" && historySame(slots, historySlots()) && r.Last != nil && !r.Last.Persisted, "actual_low_space_keeps_committed_history_and_reports_ram_fallback")
		nrMust(os.Remove("/jffs/owned-history-pressure"))
		retained()
		for _, fault := range []string{"partial", "rename-fail"} {
			nrMust(os.WriteFile("/tmp/history-fault-mode", []byte(fault), 0600))
			code, _ = historyExit("/usr/bin/qemu-arm", "-L", "/", "-E", "LD_PRELOAD=/work/build/history_fault_fixture.so", "/usr/libexec/localmod/localmod-status", "record", "fault-test", "finished", "0")
			r = query()
			must(code != 0 && r.History.Status == "write-interrupted", "pending_"+fault+"_retained")
			now := historySlots()
			must(now["slot0"] == slots["slot0"] && now["slot1"] == slots["slot1"] && now["pending"] != "", "good_generations_untouched_after_"+fault)
			historyReset(baseline, fault)
			retained()
		}
		// Real bootstrap failure records a recovery event while retaining its
		// deliberately damaged test checkpoint and every plugin/UU sentinel.
		nrMust(os.MkdirAll("/jffs/.localmod/plugin-txn/active", 0700))
		nrMust(os.WriteFile("/jffs/.localmod/plugin-txn/active/owned-damaged", []byte("preserve"), 0600))
		code, _ = historyExit("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "prepare")
		r = query()
		must(code != 0 && r.Last != nil && r.Last.Kind == "recovery" && r.Last.State == "interrupted" && string(nrRead("/jffs/.localmod/plugin-txn/active/owned-damaged")) == "preserve", "bootstrap_blocked_recovery_recorded_without_clearing_checkpoint")
		nrMust(os.Rename("/jffs/.localmod/plugin-txn/active", "/jffs/owned-history-damaged-checkpoint"))
		retained()
		historyRecord("paired-boot", "running", "manual")
		historyRecord("paired-boot", "finished", "manual")
		historyRecord("stale-boot", "running", "manual")
		// Seed an actual preparation intent; next boot runs the real recovery
		// branch, rather than merely issuing a synthetic "recovery" CLI event.
		nrCommand("/usr/libexec/localmod/plugin-txn", "begin", strconv.Itoa(os.Getpid()), "soft_install_log.txt")
		nrMust(os.WriteFile("/jffs/owned-history-before-reboot.json", []byte(mustHistoryJSON(historySlots())), 0600))
		nrCommand("/bin/sync")
		must(true, "synced_owned_state_for_new_vm_boot")
	} else if phase == "verify" {
		r := query()
		stale, closed, recovered := false, false, false
		for _, e := range r.History.Events {
			if e.Module == "stale-boot" {
				stale = e.State == "interrupted" && e.Inferred && e.Persisted
			}
			if e.Module == "paired-boot" && e.State == "running" {
				closed = e.Closed && !e.Inferred
			}
			if e.Kind == "recovery" && e.State == "finished" {
				recovered = true
			}
		}
		must(stale && closed && recovered, "new_vm_boot_retains_history_infers_stale_owner_and_records_real_recovery")
		before := historySlots()
		for i := 0; i < 100; i++ {
			query()
		}
		must(historySame(before, historySlots()), "one_hundred_authenticated_reads_do_not_write_journal")
		code, body := s.request("GET", "/_localmod/diagnostics", "")
		must(code == 200 && !strings.Contains(body, secret), "diagnostic_export_redacted_after_reboot")
		old := s.token
		code, _ = s.request("GET", "/Logout.asp", "")
		must(code == 200, "logout_completed")
		s.token = old
		code, _ = s.request("GET", "/_localmod/diagnostics", "")
		must(code == 401, "logout_revokes_persistent_history_export")
		s.token = ""
		s.login()
		retained()
	} else if strings.HasPrefix(phase, "cut-") {
		historyRecord("cut-baseline", "finished", "manual")
		nrMust(os.WriteFile("/jffs/owned-history-cut-baseline.json", []byte(mustHistoryJSON(historySlots())), 0600))
		nrCommand("/bin/sync")
		mode := strings.TrimPrefix(phase, "cut-")
		nrMust(os.WriteFile("/tmp/history-fault-mode", []byte("cut-"+mode), 0600))
		cmd := exec.Command("/usr/bin/qemu-arm", "-L", "/", "-E", "LD_PRELOAD=/work/build/history_fault_fixture.so", "/usr/libexec/localmod/localmod-status", "record", "cut-owned", "running", "0")
		nrMust(cmd.Start())
		for i := 0; i < 200; i++ {
			if _, e := os.Stat("/tmp/history-cut-ready"); e == nil {
				retained()
				must(true, "history_writer_paused_at_"+mode)
				fmt.Printf("HISTORY_RESULT %s\n", mustHistoryJSON(map[string]any{"phase": phase, "checks": checks}))
				fmt.Println("INTERRUPT_CUT_READY")
				for {
					time.Sleep(time.Hour)
				}
			}
			time.Sleep(25 * time.Millisecond)
		}
		panic("history cut boundary not reached")
	} else if strings.HasPrefix(phase, "verify-") {
		mode := strings.TrimPrefix(phase, "verify-")
		r := query()
		var before map[string]string
		nrMust(json.Unmarshal(nrRead("/jffs/owned-history-cut-baseline.json"), &before))
		now := historySlots()
		must(before["slot0"] == now["slot0"] || before["slot1"] == now["slot1"], "abrupt_cut_keeps_a_previous_good_generation_"+mode)
		found := false
		for _, e := range r.History.Events {
			if e.Module == "cut-baseline" && e.State == "finished" {
				found = true
			}
		}
		must(found, "acknowledged_history_survives_abrupt_cut_"+mode)
		if mode == "before-rename" {
			must(r.History.Status == "write-interrupted" && now["pending"] != "", "pre_rename_pending_preserved_after_reboot")
			code, _ := historyExit("/usr/libexec/localmod/localmod-status", "record", "blocked-new", "finished", "0")
			must(code != 0 && historySame(now, historySlots()), "incomplete_write_blocks_new_history_without_deleting_evidence")
		} else {
			must(r.History.Status == "ready" || r.History.Status == "write-interrupted", "post_rename_cut_has_verified_generation_or_retained_pending")
		}
		retained()
	} else {
		panic("unknown history phase")
	}
	must(u.calls.Load() == 1 && u.downloads.Load() == 1 && string(nrRead("/tmp/owned-uu-launches")) == "start\n", "uu_never_redownloaded_or_restarted_by_history")
	fmt.Printf("HISTORY_RESULT %s\n", mustHistoryJSON(map[string]any{"phase": phase, "checks": checks, "uu_launches": 1}))
}
