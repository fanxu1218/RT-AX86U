package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

func syncCall(event, timeout string) map[string]any {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	b, e := exec.CommandContext(ctx, "/usr/bin/qemu-arm", "-L", "/", "-E", "LD_PRELOAD=/usr/lib/localmod/native_boot_bridge.so:/work/build/native_hw_fixture.so", "/work/build/native-sync-aux/hook-probe", event, timeout).CombinedOutput()
	if e != nil || !strings.Contains(string(b), "NATIVE_HOOK_CALL_RETURNED") {
		panic(fmt.Sprintf("native sync entry: %v %s", e, b))
	}
	for _, line := range strings.Split(string(b), "\n") {
		if strings.HasPrefix(line, "SYNC_NATIVE_RETURN ") {
			var r map[string]any
			nrMust(json.Unmarshal([]byte(strings.TrimPrefix(line, "SYNC_NATIVE_RETURN ")), &r))
			return r
		}
	}
	panic("native return observation missing: " + string(b))
}
func main() {
	defer func() {
		if e := recover(); e != nil {
			for _, p := range []string{"/tmp/.localmod/native-hooks.log", "/tmp/.localmod/bootstrap.log", "/tmp/owned-sync-user", "/tmp/owned-native-aux-debug", "/tmp/owned-sync-helper-body"} {
				b, _ := os.ReadFile(p)
				fmt.Printf("SYNC_DIAGNOSTIC %s\n%s\n", p, b)
			}
			b, _ := exec.Command("/bin/ps", "w").CombinedOutput()
			fmt.Printf("SYNC_PROCESSES\n%s\n", b)
			panic(e)
		}
	}()
	syncCall("init-start", "0")
	syncCall("services-start", "0")
	coBackendReady()
	auxPath := "/usr/libexec/localmod/native-center-event.sh"
	auxOriginal := nrRead(auxPath)
	defer os.WriteFile(auxPath, auxOriginal, 0755)
	nrMust(os.WriteFile(auxPath, []byte(strings.Replace(string(auxOriginal), "#!/bin/sh", "#!/bin/sh\nexec 2>>/tmp/owned-native-aux-debug\nset -x\nprintf 'AUX_ENTRY\\n' >> /tmp/owned-native-aux-debug", 1)), 0755))
	nrCommand("/bin/nvram", "set", "owned_native_hook_arg=/tmp/owned-mount")
	p := "/koolshare/bin/ks-unmount.sh"
	original := nrRead(p)
	defer os.WriteFile(p, original, 0755)
	text := string(original)
	at := strings.Index(text, "\nfi\n")
	if at < 0 || !strings.Contains(text[:at], "localmod-event-dedup") {
		panic("missing dedup prefix")
	}
	prefix := text[:at+len("\nfi\n")]
	nrMust(os.WriteFile("/jffs/scripts/unmount", []byte("#!/bin/sh\n[ -z \"$LD_PRELOAD\" ] || exit 19\nprintf user >> /tmp/owned-sync-user\n"), 0755))
	defer os.Remove("/jffs/scripts/unmount")
	rows := []map[string]any{}
	for _, timeout := range []string{"2", "0"} {
		os.Remove("/tmp/owned-sync-finished")
		body := strings.Replace(prefix, "#!/bin/sh", "#!/bin/sh\nexec 2>>/tmp/owned-native-aux-debug\nset -x", 1) + "sleep 1\nprintf finished > /tmp/owned-sync-marker\nmv /tmp/owned-sync-marker /tmp/owned-sync-finished\n"
		nrMust(os.WriteFile(p, []byte(body), 0755))
		nrMust(os.WriteFile("/tmp/owned-sync-helper-body", []byte(body), 0600))
		started := time.Now()
		observation := syncCall("unmount", timeout)
		fmt.Printf("SYNC_NATIVE_BOUNDARY %v\n", observation)
		returned := time.Since(started).Milliseconds()
		finishedAtReturn := observation["helper_finished"].(bool)
		end := time.Now().Add(4 * time.Second)
		for time.Now().Before(end) {
			if _, e := os.Stat("/tmp/owned-sync-finished"); e == nil {
				break
			}
			time.Sleep(20 * time.Millisecond)
		}
		b, e := os.ReadFile("/tmp/owned-sync-finished")
		if e != nil || string(b) != "finished" {
			panic(fmt.Sprintf("added helper never finished: %v %q", e, b))
		}
		rows = append(rows, map[string]any{"timeout_seconds": timeout, "elapsed_ms": returned, "native_return": observation, "helper_finished_at_return": finishedAtReturn, "helper_eventually_finished": true, "contract_matches": finishedAtReturn == (timeout != "0")})
		fmt.Printf("SYNC_AUX_OBSERVATION timeout=%s elapsed_ms=%d finished_at_return=%v\n", timeout, returned, finishedAtReturn)
	}
	// A native user hook that consumes its budget must not turn the added
	// helper into timeout=0/background work or receive a fresh full budget.
	os.Remove("/tmp/owned-sync-finished")
	nrMust(os.WriteFile("/jffs/scripts/unmount", []byte("#!/bin/sh\nsleep 2\n"), 0755))
	observation := syncCall("unmount", "1")
	time.Sleep(1500 * time.Millisecond)
	_, err := os.Stat("/tmp/owned-sync-finished")
	skipped := os.IsNotExist(err)
	rows = append(rows, map[string]any{"timeout_seconds": "1", "native_return": observation, "helper_finished_at_return": observation["helper_finished"], "helper_eventually_finished": !skipped, "contract_matches": skipped, "case": "exhausted_native_budget"})
	result := map[string]any{"checks": []string{"native_blocking_and_async_observations_recorded"}, "online": map[string]any{"checks": []string{}}, "cases": rows, "full_upgrade_complete": false}
	b, e := json.Marshal(result)
	nrMust(e)
	fmt.Println("SYNC_AUX_RESULT", string(b))
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "stop")
}
