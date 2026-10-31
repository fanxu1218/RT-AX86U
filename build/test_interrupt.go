package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"io"
	"net"
	"os"
	"strconv"
	"strings"
	"syscall"
	"time"
)

func interruptPackage() []byte {
	original := onlinePackage("onlineprobe", "2.0", "v2")
	z, e := gzip.NewReader(bytes.NewReader(original))
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
		if h.Name == "onlineprobe/install.sh" {
			b = []byte(`#!/bin/sh
. /koolshare/scripts/base.sh
mv /koolshare/configs/onlineprobe/active.yaml /koolshare/configs/onlineprobe/migrating.yaml
dbus set onlineprobe_config=migration-in-progress
printf incomplete > /koolshare/configs/onlineprobe/active.yaml
touch /tmp/interrupt-install-reached
while :;do sleep 1;done
`)
			h.Size = int64(len(b))
		}
		nrMust(target.WriteHeader(h))
		_, e = target.Write(b)
		nrMust(e)
	}
	nrMust(target.Close())
	nrMust(gz.Close())
	return out.Bytes()
}
func interruptKillTree(pid int) {
	nrMust(syscall.Kill(pid, syscall.SIGSTOP))
	all := map[int]bool{pid: true}
	for changed := true; changed; {
		changed = false
		entries, e := os.ReadDir("/proc")
		nrMust(e)
		for _, entry := range entries {
			id, e := strconv.Atoi(entry.Name())
			if e != nil || all[id] {
				continue
			}
			b, e := os.ReadFile("/proc/" + entry.Name() + "/stat")
			if e != nil {
				continue
			}
			at := strings.LastIndex(string(b), ") ")
			if at < 0 {
				continue
			}
			f := strings.Fields(string(b)[at+2:])
			if len(f) < 2 {
				continue
			}
			parent, _ := strconv.Atoi(f[1])
			if all[parent] {
				syscall.Kill(id, syscall.SIGSTOP)
				all[id] = true
				changed = true
			}
		}
	}
	for id := range all {
		if id != pid {
			syscall.Kill(id, syscall.SIGKILL)
		}
	}
	nrMust(syscall.Kill(pid, syscall.SIGKILL))
}
func interruptLegacyMain() {
	defer func() {
		if e := recover(); e != nil {
			for _, p := range []string{"/tmp/.localmod/bootstrap.log", "/tmp/upload/soft_install_log.txt", "/var/log/perpd/current"} {
				b, _ := os.ReadFile(p)
				fmt.Printf("DIAGNOSTIC %s\n%s\n", p, b)
			}
			panic(e)
		}
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 150*time.Second)
	defer cancel()
	repo := onlineRepository()
	defer repo.close()
	s := nrStart(ctx, "interrupt-baseline", true)
	defer s.stop()
	s.login()
	coBackendReady()
	u := onlineUUStart(ctx)
	defer u.close()
	t := &onlineTest{s: s, repo: repo, uu: u, id: 93000, sentinels: map[string][]byte{}, archive: nrRead("/jffs/cert.tgz")}
	for _, p := range []string{"/jffs/uu-cache/uu.tar.gz", "/jffs/uu-cache/uu.tar.gz.md5", "/tmp/uu.tar.gz"} {
		nrMust(os.MkdirAll(p[:strings.LastIndex(p, "/")], 0700))
		b := []byte("interrupt-uu-preserve:" + p)
		nrMust(os.WriteFile(p, b, 0600))
		t.sentinels[p] = b
	}
	t.operation("v1", "", true)
	nrCommand("/usr/bin/dbus", "set", "onlineprobe_config=pre-interruption-user-value")
	nrMust(os.MkdirAll("/koolshare/configs/onlineprobe", 0700))
	original := []byte("token: synthetic-only\nlist: [one, two]\n")
	nrMust(os.WriteFile("/koolshare/configs/onlineprobe/active.yaml", original, 0600))
	if os.Args[1] == "interrupt-smoke" {
		t.operation("v2", "", true)
		if !bytes.Equal(nrRead("/koolshare/configs/onlineprobe/active.yaml"), original) {
			panic("normal update changed retained file")
		}
		if _, e := os.Stat("/jffs/.localmod/plugin-txn/active"); !os.IsNotExist(e) {
			panic("committed transaction not cleaned")
		}
		t.record("normal_checkpoint_update_preserves_configuration_and_uu")
		fmt.Println("PASS normal checkpoint update preserves configuration and UU")
		return
	}
	blob := interruptPackage()
	sum := md5.Sum(blob)
	a := onlineApp{"onlineprobe", "Owned interrupted migration", "2.0", hex.EncodeToString(sum[:]), "onlineprobe/interrupted.tar.gz"}
	repo.apps["interrupted"] = a
	repo.blobs["/"+a.TarURL] = blob
	t.begin("interrupted", "")
	for i := 0; i < 200; i++ {
		if _, e := os.Stat("/tmp/interrupt-install-reached"); e == nil {
			break
		}
		time.Sleep(40 * time.Millisecond)
	}
	if _, e := os.Stat("/tmp/interrupt-install-reached"); e != nil {
		panic("installer never reached mutation gate")
	}
	p, e := strconv.Atoi(strings.TrimSpace(string(nrRead("/tmp/.localmod/plugin-operation.lock/pid"))))
	nrMust(e)
	interruptKillTree(p)
	time.Sleep(100 * time.Millisecond)
	if string(nrRead("/koolshare/configs/onlineprobe/active.yaml")) != "incomplete" {
		panic("baseline mutation missing")
	}
	if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "onlineprobe_config")) != "migration-in-progress" {
		panic("baseline database mutation missing")
	}
	fmt.Println("REPRO r4 killed installer leaves migrated/incomplete active config; no persistent rollback journal")
	t.begin("v2", "")
	time.Sleep(100 * time.Millisecond)
	if !strings.Contains(string(nrRead("/tmp/upload/soft_install_log.txt")), "已有插件操作") {
		panic("baseline stale lock did not block next attempt")
	}
	t.record("r4_interruption_leaves_stale_lock_while_uu_and_certificate_data_remain_intact")
	// Inspect the packaged skipd framing without changing its implementation.
	c, e := net.DialTimeout("unix", "/tmp/.skipd_server_sock", time.Second)
	nrMust(e)
	defer c.Close()
	c.SetDeadline(time.Now().Add(time.Second))
	command := "list onlineprobe_"
	fmt.Fprintf(c, "magicv1 %07d %s", len(command), command)
	buf := make([]byte, 4096)
	n, e := c.Read(buf)
	fmt.Printf("SKIPD_WIRE %q error=%v\n", buf[:n], e)
	fmt.Println("INTERRUPT_BASELINE_COMPLETE")
}
