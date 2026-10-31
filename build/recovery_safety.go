package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

const safeActive = "/router/jffs/.localmod/plugin-txn/active"

func safetyValue(i int) string {
	return fmt.Sprintf("synthetic-config-%03d:", i) + strings.Repeat("0123456789abcdef", 256)
}
func safetyRead(c net.Conn) []byte {
	nrMust(c.SetReadDeadline(time.Now().Add(10 * time.Second)))
	h := make([]byte, 16)
	_, e := io.ReadFull(c, h)
	nrMust(e)
	if string(h[:8]) != "magicv1 " {
		panic("bad native skipd frame")
	}
	n, e := strconv.Atoi(string(h[8:15]))
	nrMust(e)
	if n < 1 || n > 8000000 {
		panic("unbounded native skipd response")
	}
	b := make([]byte, n)
	_, e = io.ReadFull(c, b)
	nrMust(e)
	return b
}
func safetyFrame(c net.Conn, body []byte) []byte {
	nrMust(c.SetWriteDeadline(time.Now().Add(10 * time.Second)))
	_, e := fmt.Fprintf(c, "magicv1 %07d ", len(body))
	nrMust(e)
	_, e = c.Write(body)
	nrMust(e)
	return safetyRead(c)
}
func safetyLargeSet() {
	c, e := net.Dial("unix", "/tmp/.skipd_server_sock")
	nrMust(e)
	defer c.Close()
	for i := 0; i < 256; i++ {
		key := fmt.Sprintf("zzzz_recovery_%03d", i)
		b := safetyFrame(c, []byte("set "+key+" "+safetyValue(i)+"\n"))
		if string(b) != "set "+key+" ok\n" {
			panic("native state seed rejected")
		}
	}
	nrCommand("/usr/bin/dbus", "list", "__safety_commit__")
	irqRecord("one_mib_of_native_plugin_records_synced_before_checkpoint")
}
func safetyLargeCheck() {
	c, e := net.Dial("unix", "/tmp/.skipd_server_sock")
	nrMust(e)
	defer c.Close()
	b := safetyFrame(c, []byte("list zzzz_recovery_\n"))
	seen := map[int]bool{}
	for string(b) != "list zzzz_recovery_ __end__\n" {
		pair := strings.SplitN(strings.TrimPrefix(string(b), "list "), " ", 2)
		if len(pair) != 2 {
			panic("invalid recovered record frame")
		}
		i, e := strconv.Atoi(strings.TrimPrefix(pair[0], "zzzz_recovery_"))
		nrMust(e)
		if i < 0 || i >= 256 || seen[i] || pair[1] != safetyValue(i) {
			panic("recovered plugin record lost: " + pair[0])
		}
		seen[i] = true
		b = safetyRead(c)
	}
	if len(seen) != 256 {
		panic("recovered state is incomplete")
	}
}
func safetyTree(p string) string {
	var rows []string
	e := filepath.Walk(p, func(path string, st os.FileInfo, e error) error {
		if e != nil {
			return e
		}
		r, e := filepath.Rel(p, path)
		if e != nil {
			return e
		}
		if r == "perp/.control" && st.IsDir() {
			return filepath.SkipDir
		}
		value := ""
		if st.Mode().IsRegular() {
			b, e := os.ReadFile(path)
			if e != nil {
				return e
			}
			value = irqSHA(b)
		} else if st.Mode()&os.ModeSymlink != 0 {
			v, e := os.Readlink(path)
			if e != nil {
				return e
			}
			value = v
		} else if !st.IsDir() {
			return nil
		}
		rows = append(rows, fmt.Sprintf("%s|%o|%s", r, st.Mode(), value))
		return nil
	})
	if os.IsNotExist(e) {
		return "absent"
	}
	nrMust(e)
	return irqSHA([]byte(strings.Join(rows, "\n")))
}
func safetyAlive(name string) bool {
	return exec.Command("/bin/chroot", "/router", "/bin/pidof", name).Run() == nil
}
func safetyFill(leave uint64) {
	p := "/router/jffs/.safety-fill"
	f, e := os.OpenFile(p, os.O_CREATE|os.O_RDWR|os.O_EXCL, 0600)
	nrMust(e)
	defer f.Close()
	var at int64
	for i := 0; i < 30000; i++ {
		var s syscall.Statfs_t
		nrMust(syscall.Statfs("/router/jffs", &s))
		free := s.Bfree * uint64(s.Bsize)
		if free <= leave+4096 {
			break
		}
		amount := free - leave
		if amount > 1024*1024 {
			amount = 1024 * 1024
		}
		amount -= amount % 4096
		if amount < 4096 {
			break
		}
		e = syscall.Fallocate(int(f.Fd()), 0, at, int64(amount))
		if e == syscall.ENOSPC {
			if amount > 4096 {
				e = syscall.Fallocate(int(f.Fd()), 0, at, 4096)
				if e == nil {
					at += 4096
					continue
				}
			}
			break
		}
		nrMust(e)
		at += int64(amount)
	}
	nrMust(f.Sync())
	syscall.Sync()
	var s syscall.Statfs_t
	nrMust(syscall.Statfs("/router/jffs", &s))
	fmt.Printf("OWNED_JFFS_FREE bytes=%d\n", s.Bfree*uint64(s.Bsize))
}
func safetyClient() {
	irqLoad()
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Second)
	defer cancel()
	repo := onlineRepository()
	defer repo.close()
	s := nrStart(ctx, "safety", true)
	defer s.stop()
	s.login()
	u := onlineUUStart(ctx)
	defer u.close()
	irqUUData("")
	coUUAlive(u.pid)
	coUUPage(s)
	if irqSHA(nrRead("/jffs/cert.tgz")) != string(nrRead("/jffs/.fixture-cert.sha")) {
		panic("failed recovery modified TLS archive")
	}
	code, _ := s.request("POST", "/_api/", `{"id":99601,"method":"coexist_probe.sh","params":[],"fields":{}}`)
	if !irqPhase.Baseline && code != 423 {
		panic(fmt.Sprintf("pending/invalid journal allowed API writes: %d", code))
	}
	nrMust(os.WriteFile("/tmp/safety-client.json", []byte(fmt.Sprintf(`{"api_status":%d,"uu_native_control_alive":true,"uu_data_preserved":true,"tls_archive_preserved":true}`, code)), 0600))
	fmt.Println("PASS native_login_tls_uu_control_and_persistent_uu_files_survive_failed_recovery")
}
func safetyController() {
	c := irqPhase.Case
	var repair func()
	dataActive := safeActive
	switch c {
	case "damage-tree":
		p := safeActive + "/center/configs/onlineprobe/active.yaml"
		b := nrRead(p)
		bad := append([]byte(nil), b...)
		bad[0] ^= 1
		nrMust(os.WriteFile(p, bad, 0600))
		repair = func() { nrMust(os.WriteFile(p, b, 0600)) }
	case "damage-database":
		p := safeActive + "/database/values.bin"
		b := nrRead(p)
		nrMust(os.WriteFile(p, b[:len(b)/2], 0600))
		repair = func() { nrMust(os.WriteFile(p, b, 0600)) }
	case "damage-ready":
		p := safeActive + "/ready"
		b := nrRead(p)
		nrMust(os.Remove(p))
		repair = func() { nrMust(os.WriteFile(p, b, 0600)) }
	case "damage-commit":
		p := safeActive + "/committed"
		nrMust(os.WriteFile(p, []byte("invalid-commit"), 0600))
		repair = func() { nrMust(os.Remove(p)) }
	case "damage-manifest":
		p := safeActive + "/manifest.bin"
		b := nrRead(p)
		bad := append([]byte(nil), b...)
		bad[len(b)/2] ^= 1
		nrMust(os.WriteFile(p, bad, 0600))
		repair = func() { nrMust(os.WriteFile(p, b, 0600)) }
	case "damage-meta":
		p := safeActive + "/boot"
		b := nrRead(p)
		nrMust(os.WriteFile(p, []byte("invalid-boot"), 0600))
		repair = func() { nrMust(os.WriteFile(p, b, 0600)) }
	case "damage-active-link":
		dataActive = safeActive + ".preserved"
		nrMust(os.Rename(safeActive, dataActive))
		nrMust(os.Symlink("/jffs/.safety-no-such-target", safeActive))
		repair = func() { nrMust(os.Remove(safeActive)); nrMust(os.Rename(dataActive, safeActive)) }
	case "legacy-r5":
	case "space-full":
		safetyFill(0)
		repair = func() { nrMust(os.Remove("/router/jffs/.safety-fill")) }
	case "space-low":
		safetyFill(1024 * 1024)
		repair = func() { nrMust(os.Remove("/router/jffs/.safety-fill")) }
	case "space-replay":
		nrMust(os.WriteFile("/router/tmp/txn-fault-mode", []byte("space-replay"), 0600))
		nrMust(os.WriteFile("/router/tmp/txn-fault-armed", []byte("1"), 0600))
		repair = func() { nrMust(os.Remove("/router/jffs/.safety-fill")) }
	default:
		panic("unknown safety case: " + c)
	}
	syscall.Sync()
	before := map[string]string{"center": safetyTree("/router/jffs/.koolshare"), "checkpoint": safetyTree(dataActive + "/center"), "records": safetyTree(dataActive + "/database"), "database": safetyTree("/router/jffs/.localmod/ksdb")}
	ctx, cancel := context.WithTimeout(context.Background(), 170*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "/bin/chroot", "/router", "/bin/sh", "/work/build/real_plugins_setup.sh")
	var console bytes.Buffer
	cmd.Stdout = &console
	cmd.Stderr = &console
	nrMust(cmd.Start())
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	var result error
	released := false
running:
	for {
		select {
		case result = <-done:
			break running
		case <-time.After(50 * time.Millisecond):
			if c == "space-replay" && !released {
				if _, e := os.Stat("/router/tmp/txn-fault-gate"); e == nil {
					safetyFill(64 * 1024)
					nrMust(os.WriteFile("/router/tmp/safety-release", []byte("1"), 0600))
					released = true
				}
			}
		}
	}
	fmt.Print(console.String())
	if c == "space-replay" && !released {
		panic("space fault did not reach native database replay write gate")
	}
	alive := map[string]bool{}
	for _, n := range []string{"skipd", "httpdb", "perpd", "localmod-event"} {
		alive[n] = safetyAlive(n)
	}
	journal := true
	if _, e := os.Lstat(safeActive); os.IsNotExist(e) {
		journal = false
	}
	after := map[string]string{"center": safetyTree("/router/jffs/.koolshare"), "checkpoint": safetyTree(dataActive + "/center"), "records": safetyTree(dataActive + "/database"), "database": safetyTree("/router/jffs/.localmod/ksdb")}
	retained := after["records"] == before["records"] && (after["checkpoint"] == before["checkpoint"] || after["center"] == before["checkpoint"]) && (after["database"] == before["database"] || safetyTree(safeActive+"/failed-database") == before["database"])
	retained = retained && (after["center"] == before["center"] || safetyTree(dataActive+"/failed-center") == before["center"])
	blocked := result != nil && journal && !alive["skipd"] && !alive["httpdb"] && !alive["perpd"] && !alive["localmod-event"]
	check := exec.CommandContext(ctx, "/bin/chroot", "/router", "/work/build/test-interrupt", "safety-client")
	check.Stdout = os.Stdout
	check.Stderr = os.Stderr
	nrMust(check.Run())
	client := map[string]any{}
	nrMust(json.Unmarshal(nrRead("/router/tmp/safety-client.json"), &client))
	irqUUData("/router")
	if irqPhase.Baseline {
		fmt.Printf("R5_SAFETY_BASELINE case=%s blocked=%t retained=%t processes=%v\n", c, blocked, retained, alive)
	} else {
		if !blocked || !retained {
			panic(fmt.Sprintf("unsafe recovery: blocked=%t retained=%t processes=%v before=%v after=%v", blocked, retained, alive, before, after))
		}
		fmt.Println("PASS failed_recovery_stops_center_and_database_with_all_usable_copies_retained")
		again := exec.Command("/bin/chroot", "/router", "/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "prepare")
		if again.Run() == nil {
			panic("same-boot preparation retried failed recovery")
		}
		if safetyTree(dataActive+"/database") != before["records"] {
			panic("failed retry changed logical checkpoint")
		}
		if safetyTree("/router/jffs/.koolshare") != after["center"] || safetyTree("/router/jffs/.localmod/ksdb") != after["database"] {
			panic("failed same-boot retry modified current data")
		}
		fmt.Println("PASS same_boot_retry_remains_blocked_and_keeps_checkpoint")
		if repair != nil {
			repair()
			syscall.Sync()
			fmt.Println("PASS fixture_repair_or_space_release_preserves_uu_and_enables_next_boot_validation")
		} else {
			fmt.Println("PASS legacy_checkpoint_requires_manual_review_without_adopting_unsealed_bytes")
		}
	}
	b, e := json.Marshal(map[string]any{"case": c, "baseline": irqPhase.Baseline, "blocked": blocked, "retained": retained, "processes": alive, "client": client})
	nrMust(e)
	fmt.Printf("SAFETY_RESULT %s\n", b)
}
