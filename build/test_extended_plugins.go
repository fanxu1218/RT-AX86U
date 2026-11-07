package main

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"sync/atomic"
	"syscall"
	"time"
)

type extendedPackage struct {
	Module, Phase, Version, Path, MD5, SHA256 string
	Files                                     map[string]string
	RuntimeFiles                              map[string]string `json:"runtime_files"`
}

func fancyExtended(t *onlineTest, record func(string), fresh bool) func() {
	var input struct{ Packages []extendedPackage }
	nrMust(json.Unmarshal(nrRead("/work/build/extended_plugin_inputs.json"), &input))
	installed := map[string]extendedPackage{}
	jq := fancySHA(nrRead("/koolshare/bin/jq"))
	peerValues := map[string]string{"frpc_server_addr": "retained.invalid", "frpc_server_port": "7000", "pushplus_check_custom": "b3duZWQgbm9uc2VjcmV0"}
	allFiles := func() {
		for mod, p := range installed {
			if fancyDB("softcenter_module_"+mod+"_version") != p.Version {
				panic("extended registration differs: " + mod)
			}
			for name, expected := range p.RuntimeFiles {
				if !(strings.HasPrefix(name, "bin/") || strings.HasPrefix(name, "scripts/")) {
					continue
				}
				if name == "bin/jq" {
					expected = jq
				}
				if fancySHA(nrRead("/koolshare/"+name)) != expected {
					panic("extended installed file differs: " + name)
				}
			}
		}
	}
	for _, p := range input.Packages {
		blob := nrRead("/work/" + p.Path)
		sum := md5.Sum(blob)
		if fancySHA(blob) != p.SHA256 || hex.EncodeToString(sum[:]) != p.MD5 {
			panic("extended input digest differs")
		}
		key := "extended-" + p.Module + "-" + p.Phase
		url := p.Module + "/" + p.Phase + ".tar.gz"
		t.repo.mu.Lock()
		t.repo.apps[key] = onlineApp{p.Module, p.Module, p.Version, p.MD5, url}
		t.repo.blobs["/"+url] = blob
		t.repo.mu.Unlock()
	}
	for _, mod := range []string{"frpc", "pushplus"} {
		fancySet(mod+"_enable", "0")
		for _, phase := range []string{"old", "current"} {
			if fresh && phase == "old" {
				continue
			}
			var p extendedPackage
			for _, candidate := range input.Packages {
				if candidate.Module == mod && candidate.Phase == phase {
					p = candidate
				}
			}
			// The upstream 2.4 installer deletes /tmp/frpc* after success. Its
			// reviewed package adaptation must preserve a similarly named peer.
			if mod == "frpc" && phase == "current" {
				path := "/tmp/frpc-unrelated-user-file"
				data := []byte("owned unrelated runtime")
				nrMust(os.WriteFile(path, data, 0600))
				t.sentinels[path] = data
			}
			if !fresh && mod == "frpc" && phase == "current" {
				func() {
					cleanup := fancyPressure()
					defer cleanup()
					t.operation("extended-"+mod+"-"+phase, "", false)
					allFiles()
					for k, v := range peerValues {
						if fancyDB(k) != v {
							panic("low-space failure changed config")
						}
					}
					record("low_checkpoint_space_refuses_real_frpc_update_before_mutation_and_preserves_fancyss_config_uu")
				}()
			}
			t.operation("extended-"+mod+"-"+phase, "", true)
			installed[mod] = p
			allFiles()
			code, body := t.s.request("GET", "/Module_"+mod+".asp", "")
			if code != 200 || !strings.Contains(body, "dbus") {
				panic("extended native page unavailable: " + mod)
			}
			if phase == "old" {
				for k, v := range peerValues {
					fancySet(k, v)
				}
			} else if !fresh {
				for k, v := range peerValues {
					if fancyDB(k) != v {
						panic("extended upgrade lost config: " + k)
					}
				}
			}
			label := phase
			if fresh {
				label = "fresh_current_after_uninstall"
			}
			record(mod + "_" + label + "_authentic_version_install_original_binaries_peers_config_uu_retained")
		}
	}
	if version := nrCommand("/koolshare/bin/frpc", "-v"); strings.TrimSpace(version) != "0.65.0" {
		panic("actual FRPC version differs: " + version)
	}
	record("actual_frpc_0_65_0_binary_runs_with_fancyss_and_uu")
	t.rpc("frpc_config.sh", "1", map[string]string{"frpc_enable": "0"})
	completed := false
	for i := 0; i < 450; i++ {
		b, _ := os.ReadFile("/tmp/upload/frpc_submit_log.txt")
		if strings.Contains(string(b), "FRPC_RESULT=OK") {
			completed = true
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if !completed {
		b, _ := os.ReadFile("/tmp/upload/frpc_submit_log.txt")
		panic("real FRPC disabled callback did not settle: " + string(b))
	}
	// PushPlus's original config script never acknowledges its request. The
	// adapted current package must return the real callback ID promptly.
	started := time.Now()
	t.rpc("pushplus_config.sh", "1", map[string]string{"pushplus_enable": "0"})
	if time.Since(started) > 5*time.Second {
		panic("PushPlus callback failed to complete promptly")
	}
	record("disabled_frpc_and_pushplus_real_native_https_callbacks_do_not_stall_or_restart_uu")
	return func() {
		// Called after Fancyss uninstall: PushPlus still needs its shared JQ.
		if fancySHA(nrRead("/koolshare/bin/jq")) != jq {
			panic("Fancyss uninstall lost shared JQ")
		}
		if strings.TrimSpace(nrCommand("/koolshare/bin/jq", "-n", "--arg", "owned", "coexist", `$owned`)) != `"coexist"` {
			panic("shared JQ no longer executes")
		}
		allFiles()
		record("shared_jq_executes_with_installed_frpc_and_pushplus_binaries_and_configuration")
		for _, mod := range []string{"frpc", "pushplus"} {
			t.rpc("ks_app_remove.sh", "ks_app_remove", map[string]string{"softcenter_installing_todo": mod, "softcenter_installing_title": mod})
			t.wait(true)
			delete(installed, mod)
			allFiles()
			for _, path := range []string{"/koolshare/webs/Module_" + mod + ".asp", "/koolshare/scripts/uninstall_" + mod + ".sh"} {
				if _, e := os.Lstat(path); !os.IsNotExist(e) {
					panic("extended uninstall left " + path)
				}
			}
			if fancyDB("softcenter_module_"+mod+"_version") != "" {
				panic("extended registration left")
			}
			record(mod + "_authentic_uninstaller_preserves_remaining_peers_and_uu")
		}
	}
}

func fancyPressure() func() {
	var fs syscall.Statfs_t
	nrMust(syscall.Statfs("/jffs", &fs))
	free := int64(fs.Bavail) * fs.Bsize
	leave := int64(1024 * 1024) // Below the checkpoint's minimum 2 MiB reserve.
	if free <= leave {
		panic("fixture has no space for controlled checkpoint test")
	}
	path := "/jffs/owned-fancyss-pressure"
	f, e := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	nrMust(e)
	chunk := make([]byte, 1024*1024)
	for left := free - leave; left > 0; {
		n := int64(len(chunk))
		if left < n {
			n = left
		}
		written, e := f.Write(chunk[:n])
		nrMust(e)
		if int64(written) != n {
			panic("short pressure write")
		}
		left -= n
	}
	nrMust(f.Close())
	return func() { nrMust(os.Remove(path)) }
}

func fancyCompat(t *onlineTest, record func(string)) {
	for _, c := range []struct{ mod, name, input, output string }{
		{"frpc", "install.sh", "42164ef46201d0fa33805196818fd01666ce46638f0e74d8b7e340fa01127a3e", "9cbecaf7af1525c6c1c79395e0c8887b07eadb60bcd8b48bb7b697b759fdabc5"},
		{"pushplus", "scripts/pushplus_config.sh", "e1ff1be042266bce1f5e73b5a69cd82da2b9c72f278aef3c5e3a78d3fb743d21", "0c5c059fd38886c40f20acf9d48665aa92cd4fa5fb523dd76c696b91580322b5"},
	} {
		func() {
			stage := "/tmp/" + c.mod
			nrMust(os.Mkdir(stage, 0700))
			defer os.RemoveAll(stage)
			path := stage + "/" + c.name
			nrMust(os.MkdirAll(path[:strings.LastIndex(path, "/")], 0700))
			data := nrRead("/work/sources/extended-plugin-tree/" + c.mod + "/" + c.mod + "/" + c.name)
			if fancySHA(data) != c.input {
				panic("compatibility probe source changed")
			}
			nrMust(os.WriteFile(path, data, 0755))
			temp := path + ".localmod-compat"
			nrMust(os.WriteFile(temp, []byte("owned-preexisting-conflict"), 0600))
			cmd := exec.Command("/bin/sh", "/usr/libexec/localmod/plugin-compat.sh", c.mod, stage)
			if e := cmd.Run(); e == nil || fancySHA(nrRead(path)) != c.input || string(nrRead(temp)) != "owned-preexisting-conflict" {
				panic("compatibility temp collision was not preserved")
			}
			nrMust(os.Remove(temp))
			nrCommand("/bin/sh", "/usr/libexec/localmod/plugin-compat.sh", c.mod, stage)
			if fancySHA(nrRead(path)) != c.output {
				panic("pinned compatibility output differs")
			}
			nrCommand("/bin/sh", "/usr/libexec/localmod/plugin-compat.sh", c.mod, stage)
			if fancySHA(nrRead(path)) != c.output {
				panic("compatibility was not idempotent")
			}
			unknown := []byte("#!/bin/sh\n# unknown owned source fixture\n")
			nrMust(os.WriteFile(path, unknown, 0755))
			nrCommand("/bin/sh", "/usr/libexec/localmod/plugin-compat.sh", c.mod, stage)
			if string(nrRead(path)) != string(unknown) {
				panic("unknown script was heuristically modified")
			}
		}()
	}
	record("hash_pinned_compat_refuses_temp_collision_is_idempotent_and_preserves_unknown_scripts")
}

func fancyProxy(ctx context.Context, record func(string)) {
	passed := false
	defer func() {
		if !passed {
			for i := 0; i < 2; i++ {
				p := fmt.Sprintf("/tmp/fancyss-owned-xray-%d.json.log", i)
				if b, e := os.ReadFile(p); e == nil {
					fmt.Printf("XRAY_DIAGNOSTIC %d\n%s\n", i, b)
				}
			}
		}
	}()
	var hits atomic.Int32
	l, e := net.Listen("tcp4", "127.0.0.1:35017")
	nrMust(e)
	h := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { hits.Add(1); fmt.Fprint(w, "owned-loopback-xray-route") })}
	go h.Serve(l)
	defer h.Close()
	l2, e := net.Listen("tcp4", "127.0.0.1:35018")
	nrMust(e)
	go h.Serve(l2)
	uuid := "55f681c1-90d8-4a3e-97a1-0488498fe021"
	// Xray 26.5.9 deliberately blocks private targets from VLESS inbounds.
	// Permit only this owned fixture port; leave its default protection intact.
	freedom := map[string]any{"protocol": "freedom", "settings": map[string]any{"finalRules": []any{map[string]any{"action": "allow", "network": "tcp", "ip": []string{"127.0.0.1/32"}, "port": "35017"}}}}
	configs := []any{
		map[string]any{"log": map[string]string{"loglevel": "debug"}, "inbounds": []any{map[string]any{"listen": "127.0.0.1", "port": 35015, "protocol": "vless", "settings": map[string]any{"clients": []any{map[string]string{"id": uuid}}, "decryption": "none"}}}, "outbounds": []any{freedom}},
		map[string]any{"log": map[string]string{"loglevel": "debug"}, "inbounds": []any{map[string]any{"listen": "127.0.0.1", "port": 35016, "protocol": "socks", "settings": map[string]any{"auth": "noauth", "udp": false}}}, "outbounds": []any{map[string]any{"protocol": "vless", "settings": map[string]any{"vnext": []any{map[string]any{"address": "127.0.0.1", "port": 35015, "users": []any{map[string]string{"id": uuid, "encryption": "none"}}}}}}}},
	}
	var cmds []*exec.Cmd
	for i, c := range configs {
		path := fmt.Sprintf("/tmp/fancyss-owned-xray-%d.json", i)
		nrMust(os.WriteFile(path, []byte(mustFancyJSON(c)), 0600))
		log, e := os.Create(path + ".log")
		nrMust(e)
		defer log.Close()
		cmd := exec.CommandContext(ctx, "/koolshare/bin/xray", "run", "-c", path)
		cmd.Stdout = log
		cmd.Stderr = log
		nrMust(cmd.Start())
		cmds = append(cmds, cmd)
		defer func() { _ = cmd.Process.Kill(); _ = cmd.Wait() }()
		ready := false
		for j := 0; j < 100; j++ {
			c, e := net.DialTimeout("tcp4", fmt.Sprintf("127.0.0.1:%d", 35015+i), 100*time.Millisecond)
			if e == nil {
				c.Close()
				ready = true
				break
			}
			time.Sleep(50 * time.Millisecond)
		}
		if !ready {
			panic("actual Xray fixture did not listen: " + string(nrRead(path+".log")))
		}
	}
	query := func(port int) string {
		c, e := net.DialTimeout("tcp4", "127.0.0.1:35016", time.Second)
		nrMust(e)
		defer c.Close()
		nrMust(c.SetDeadline(time.Now().Add(4 * time.Second)))
		_, e = c.Write([]byte{5, 1, 0})
		nrMust(e)
		b := make([]byte, 2)
		_, e = io.ReadFull(c, b)
		nrMust(e)
		if b[0] != 5 || b[1] != 0 {
			panic("SOCKS method differs")
		}
		_, e = c.Write([]byte{5, 1, 0, 1, 127, 0, 0, 1, byte(port >> 8), byte(port)})
		nrMust(e)
		b = make([]byte, 10)
		if _, e = io.ReadFull(c, b); e != nil || b[1] != 0 {
			return ""
		}
		_, _ = io.WriteString(c, "GET /owned HTTP/1.0\r\nHost: localhost\r\n\r\n")
		data, _ := io.ReadAll(c)
		return string(data)
	}
	response := query(35017)
	if !strings.Contains(response, "owned-loopback-xray-route") || hits.Load() != 1 {
		fmt.Printf("XRAY_RESPONSE %q hits=%d\n", response, hits.Load())
		panic("actual Xray SOCKS/VLESS loopback forwarding failed")
	}
	if strings.Contains(query(35018), "owned-loopback-xray-route") || hits.Load() != 1 {
		panic("Xray private target protection was disabled")
	}
	_ = cmds[0].Process.Kill()
	_ = cmds[0].Wait()
	if strings.Contains(query(35017), "owned-loopback-xray-route") || hits.Load() != 1 {
		panic("Xray client bypassed stopped VLESS server")
	}
	record("actual_xray_socks_vless_forwarding_private_guard_and_upstream_failure_without_direct_bypass")
	passed = true
}
