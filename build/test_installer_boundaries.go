package main

import (
	"bytes"
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"
)

func boundaryExit(command ...string) (int, string) {
	b, e := exec.Command(command[0], command[1:]...).CombinedOutput()
	if e == nil {
		return 0, string(b)
	}
	if x, ok := e.(*exec.ExitError); ok {
		return x.ExitCode(), string(b)
	}
	panic(e)
}

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Second)
	defer cancel()
	var cases []struct {
		Name, Path, Module string
		Accepted           bool
	}
	nrMust(json.Unmarshal(nrRead("/work/build/installer-boundary-inputs/cases.json"), &cases))
	results := map[string]bool{}
	checks := map[string]bool{}
	for _, c := range cases {
		code, out := boundaryExit("/usr/libexec/localmod/archive-guard", "/work/"+c.Path, c.Module)
		if (code == 0) != c.Accepted || code == 0 && strings.TrimSpace(out) != c.Module {
			panic(fmt.Sprintf("archive case %s got %d %q expected %v", c.Name, code, out, c.Accepted))
		}
		results[c.Name] = true
	}
	checks["safe_relative_links_and_all_six_pinned_hnd_archives_accepted"] = true
	checks["escaping_links_special_files_duplicates_limits_crc_and_truncation_rejected"] = true
	// The old name-only guard accepts this archive: metadata is the missing boundary.
	text := nrCommand("/bin/tar", "-tzf", "/work/build/installer-boundary-inputs/symlink_escape.tar.gz")
	for _, name := range strings.Fields(text) {
		if !strings.HasPrefix(name, "onlineprobe/") || strings.Contains(name, "..") {
			panic("baseline no longer reproduces")
		}
	}
	checks["r7_name_only_guard_accepts_escaping_link_metadata"] = true
	// Oversized output must fail even when the producer exits between polling ticks.
	code, _ := boundaryExit("/usr/libexec/localmod/plugin-run", "2", "/tmp/limit-download", "1024", "/bin/sh", "-c", "dd if=/dev/zero of=/tmp/limit-download bs=2048 count=1 2>/dev/null")
	if code != 125 {
		panic(fmt.Sprintf("download guard result %d", code))
	}
	checks["completed_oversized_download_rejected"] = true
	code, _ = boundaryExit("/usr/libexec/localmod/plugin-run", "2", "-", "0", "/bin/sh", "-c", "exit 9")
	if code != 9 {
		panic("script exit status not preserved")
	}
	checks["script_exit_status_preserved"] = true
	start := time.Now()
	code, _ = boundaryExit("/usr/libexec/localmod/plugin-run", "1", "-", "0", "/bin/sh", "-c", "trap '' TERM; (trap '' TERM; while :;do sleep 1;done) & echo $! > /tmp/boundary-child; wait")
	if code != 124 || time.Since(start) > 4*time.Second {
		panic("script timeout not bounded")
	}
	child, e := strconv.Atoi(strings.TrimSpace(string(nrRead("/tmp/boundary-child"))))
	nrMust(e)
	for i := 0; i < 50; i++ {
		b, _ := os.ReadFile(fmt.Sprintf("/proc/%d/stat", child))
		if len(b) == 0 || bytes.Contains(b, []byte(") Z ")) {
			break
		}
		if i == 49 {
			panic("timeout left owned descendant running")
		}
		time.Sleep(20 * time.Millisecond)
	}
	checks["timeout_kills_owned_process_group_including_term_resistant_child"] = true
	repo := onlineRepository()
	defer repo.close()
	s := nrStart(ctx, "installer-boundaries", true)
	defer s.stop()
	s.login()
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	t := &onlineTest{s: s, repo: repo, uu: u, id: 97000, sentinels: map[string][]byte{}, archive: nrRead("/jffs/cert.tgz")}
	for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-cache/uu.tar.gz.md5", "/jffs/uu-state/user.dat", "/tmp/uu.tar.gz"} {
		nrMust(os.MkdirAll(p[:strings.LastIndex(p, "/")], 0700))
		b := []byte("boundary-owned:" + p)
		nrMust(os.WriteFile(p, b, 0600))
		t.sentinels[p] = b
	}
	t.operation("v1", "", true)
	nrCommand("/usr/bin/dbus", "set", "onlineprobe_config=user-retained")
	t.plugin("1.0")
	t.record("initial_install_with_guard")
	for _, name := range []string{"symlink_escape", "link_parent", "hardlink_escape", "device", "declared_large", "corrupt_crc"} {
		blob := nrRead("/work/build/installer-boundary-inputs/" + name + ".tar.gz")
		sum := md5.Sum(blob)
		repo.mu.Lock()
		repo.apps[name] = onlineApp{"onlineprobe", "Owned Boundary", "2.0", hex.EncodeToString(sum[:]), "onlineprobe/" + name + ".tar.gz"}
		repo.blobs["/onlineprobe/"+name+".tar.gz"] = blob
		repo.mu.Unlock()
		t.operation(name, "", false)
		t.plugin("1.0")
		t.record("online_reject_" + name)
		if _, e := os.Stat("/jffs/.localmod/plugin-txn/active"); !os.IsNotExist(e) {
			panic("rejected archive created mutation checkpoint")
		}
		checks["online_reject_"+name+"_preserves_plugin_and_uu"] = true
	}
	for _, name := range []string{"symlink_escape", "link_parent", "device"} {
		nrMust(os.WriteFile("/tmp/upload/"+name+".tar.gz", nrRead("/work/build/installer-boundary-inputs/"+name+".tar.gz"), 0600))
		os.Remove("/tmp/upload/soft_log.txt")
		t.rpc("ks_tar_install.sh", "install", map[string]string{"soft_name": name + ".tar.gz"})
		finished := false
		for i := 0; i < 200; i++ {
			b, _ := os.ReadFile("/tmp/upload/soft_log.txt")
			_, e := os.Stat("/tmp/.localmod/plugin-operation.lock")
			if bytes.Contains(b, []byte("XU6J03M6")) && os.IsNotExist(e) {
				finished = true
				break
			}
			time.Sleep(30 * time.Millisecond)
		}
		if !finished || strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "softcenter_installing_result")) == "0" {
			panic("offline rejection did not finish safely")
		}
		t.plugin("1.0")
		t.record("offline_reject_" + name)
		checks["offline_reject_"+name+"_preserves_plugin_and_uu"] = true
	}
	if _, e := os.Stat("/tmp/unsafe-installer-ran"); !os.IsNotExist(e) {
		panic("invalid package executed installer")
	}
	checks["invalid_archives_never_execute_install_script"] = true
	t.operation("v2", "", true)
	t.plugin("2.0")
	t.record("valid_update_after_rejections")
	checks["valid_update_after_rejections"] = true
	// The exact production supervisor is tested with a one-second budget above.
	// This owned install invokes it so the ordinary failure/checkpoint path runs.
	nrMust(os.MkdirAll("/tmp/boundary-src/onlineprobe", 0700))
	nrMust(os.WriteFile("/tmp/boundary-src/onlineprobe/install.sh", []byte("#!/bin/sh\nexec /usr/libexec/localmod/plugin-run 1 - 0 /bin/sh -c 'trap \"\" TERM; sleep 30'\n"), 0755))
	nrMust(os.WriteFile("/tmp/boundary-src/onlineprobe/.valid", []byte("hnd\n"), 0644))
	nrCommand("/bin/tar", "-czf", "/tmp/boundary-timeout.tar.gz", "-C", "/tmp/boundary-src", "onlineprobe")
	blob := nrRead("/tmp/boundary-timeout.tar.gz")
	sum := md5.Sum(blob)
	repo.mu.Lock()
	repo.apps["timeout"] = onlineApp{"onlineprobe", "Owned Timeout", "3.0", hex.EncodeToString(sum[:]), "onlineprobe/timeout.tar.gz"}
	repo.blobs["/onlineprobe/timeout.tar.gz"] = blob
	repo.mu.Unlock()
	t.operation("timeout", "", false)
	if _, e := os.Stat("/jffs/.localmod/plugin-txn/active"); e != nil {
		panic("timeout failed to preserve checkpoint")
	}
	if string(nrRead("/koolshare/onlineprobe/version")) != "2.0" || strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "onlineprobe_config")) != "user-retained" {
		panic("timeout damaged existing config")
	}
	t.record("timeout_preserves_checkpoint_config_and_uu")
	checks["timeout_preserves_checkpoint_config_and_uu"] = true
	// Recovery gate must prevent a subsequent write on the same boot.
	t.id++
	payload := fmt.Sprintf(`{"id":%d,"method":"onlineprobe.sh","params":["probe"],"fields":{}}`, t.id)
	status, _ := s.request("POST", "/_api/", payload)
	if status != 423 {
		panic(fmt.Sprintf("pending checkpoint write gate %d", status))
	}
	checks["timeout_recovery_required_blocks_later_writes"] = true
	if u.cmd.Process.Signal(syscall.Signal(0)) != nil {
		panic("UU controller disappeared")
	}
	result := map[string]any{"archive_cases": results, "checks": checks, "uu_launches": strings.Count(string(nrRead("/tmp/owned-uu-launches")), "start\n"), "workflow_records": t.checks}
	b, e := json.Marshal(result)
	nrMust(e)
	fmt.Printf("INSTALLER_BOUNDARY_RESULT %s\n", b)
}
