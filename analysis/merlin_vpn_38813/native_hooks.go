package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"
)

func hookCall(name string, timeout string) {
	c := exec.Command("/usr/bin/qemu-arm", "-L", "/", "-E", "LD_PRELOAD=/work/build/merlin38813-native-hooks/native_boot_bridge.so:/work/build/native_hw_fixture.so", "/work/build/merlin38813-native-hooks/hook-probe", name, timeout)
	b, e := c.CombinedOutput()
	if e != nil || !strings.Contains(string(b), "NATIVE_HOOK_CALL_RETURNED") {
		panic(fmt.Sprintf("native hook %s: %v %s", name, e, b))
	}
}
func countLines(path string) int { b, _ := os.ReadFile(path); return strings.Count(string(b), "\n") }
func hookCounts(user, center int) {
	end := time.Now().Add(5 * time.Second)
	for time.Now().Before(end) {
		if countLines("/tmp/native-user-hooks") == user && countLines("/tmp/native-center-hooks") == center {
			time.Sleep(300 * time.Millisecond)
			if countLines("/tmp/native-user-hooks") == user && countLines("/tmp/native-center-hooks") == center {
				return
			}
		}
		time.Sleep(30 * time.Millisecond)
	}
	panic(fmt.Sprintf("hook counts user=%d/%d center=%d/%d", countLines("/tmp/native-user-hooks"), user, countLines("/tmp/native-center-hooks"), center))
}
func main() {
	checks := []string{}
	record := func(s string) { checks = append(checks, s); fmt.Println("PASS", s) }
	set := func(k, v string) { nrCommand("/bin/nvram", "set", k+"="+v) }
	set("rc_support", "https jffs2 openvpnd")
	set("owned_native_hook_arg", "native-argument-with-spaces")
	hookCall("init-start", "0")
	if strings.TrimSpace(nrCommand("/usr/bin/dbus", "get", "softcenter_version")) != "1.9.60" {
		panic("native init hook did not prepare center")
	}
	flags := strings.Fields(nrCommand("/bin/nvram", "get", "rc_support"))
	if strings.Join(flags, " ") != "https jffs2 openvpnd uu_accel" {
		panic(fmt.Sprintf("native UU capability changed other flags: %v", flags))
	}
	record("native_init_start_prepares_center_and_appends_only_supported_uu_capability")
	mappings := []struct{ event, helper, call string }{
		{"services-start", "ks-services-start.sh", ""},
		{"services-stop", "ks-services-stop.sh", ""},
		{"wan-start", "ks-wan-start.sh", "start"},
		{"nat-start", "ks-nat-start.sh", "start_nat"},
		{"post-mount", "ks-mount-start.sh", "start \"$1\""},
		{"unmount", "ks-unmount.sh", "\"$1\""},
	}
	originals := map[string][]byte{}
	for i, m := range mappings {
		path := "/koolshare/bin/" + m.helper
		original := nrRead(path)
		originals[path] = original
		text := string(original)
		at := strings.Index(text, "\nfi\n")
		if at < 0 || !strings.Contains(text[:at], "localmod-event-dedup") {
			panic("missing center dedup contract")
		}
		at += len("\nfi\n")
		text = text[:at] + "printf '" + m.event + "\\n' >> /tmp/native-center-hooks\n" + text[at:]
		nrMust(os.WriteFile(path, []byte(text), 0755))
		user := "#!/bin/sh\n[ -z \"$LD_PRELOAD\" ] || exit 19\nprintf '%s:%s:%s\\n' '" + m.event + "' \"$1\" \"$2\" >> /tmp/native-user-hooks\nusleep 150000\n/koolshare/bin/" + m.helper + " " + m.call + "\n"
		nrMust(os.WriteFile("/jffs/scripts/"+m.event, []byte(user), 0755))
		hookCall(m.event, "0")
		hookCounts(i+1, i+1)
		if !strings.Contains(string(nrRead("/tmp/native-user-hooks")), m.event+":native-argument-with-spaces:native-second\n") {
			panic("native hook arguments changed")
		}
		record("native_user_and_center_exactly_once_" + m.event)
	}
	coBackendReady()
	coPrivateDenied()
	record("native_services_start_starts_center_with_private_backend_guard")
	// Three separate notifications remain separate events, while each user's
	// explicit helper invocation is deduplicated against our added helper.
	for i := 0; i < 3; i++ {
		hookCall("services-start", "0")
		hookCounts(7+i, 7+i)
	}
	record("repeated_native_notifications_are_not_coalesced_or_duplicated")
	nrMust(os.WriteFile("/jffs/scripts/owned-unmanaged-hook", []byte("#!/bin/sh\nprintf unmanaged >> /tmp/native-unmanaged\n"), 0755))
	hookCall("owned-unmanaged-hook", "2")
	if string(nrRead("/tmp/native-unmanaged")) != "unmanaged" {
		panic("unmanaged native hook not forwarded")
	}
	record("unmanaged_native_hook_and_blocking_timeout_forwarded")
	set("jffs2_scripts", "0")
	hookCall("services-start", "0")
	time.Sleep(400 * time.Millisecond)
	hookCounts(9, 9)
	set("jffs2_scripts", "1")
	record("native_custom_script_disable_flag_preserved")
	set("territory_code", "US/01")
	set("rc_support", "https jffs2 openvpnd")
	hookCall("init-start", "0")
	if strings.Contains(nrCommand("/bin/nvram", "get", "rc_support"), "uu_accel") {
		panic("UU advertised for non-China fixture")
	}
	set("territory_code", "CN/01")
	hookCall("init-start", "0")
	record("uu_advertisement_territory_gate_preserves_merlin_features")
	nrMust(os.WriteFile("/etc/dnsmasq.conf", []byte("port=0\n# retained-native-config\n"), 0644))
	nrMust(os.WriteFile("/jffs/scripts/dnsmasq.postconf", []byte("#!/bin/sh\n[ -z \"$LD_PRELOAD\" ] || exit 19\ngrep -qx 'conf-dir=/jffs/configs/dnsmasq.d' \"$1\" || exit 18\nprintf '# user-postconf-last\\n' >> \"$1\"\n"), 0755))
	set("owned_native_hook_arg", "/etc/dnsmasq.conf")
	for i := 0; i < 2; i++ {
		hookCall("__dnsmasq_postconf", "2")
	}
	config := string(nrRead("/etc/dnsmasq.conf"))
	if strings.Count(config, "conf-dir=/jffs/configs/dnsmasq.d") != 1 || strings.Count(config, "# user-postconf-last") != 2 || !strings.Contains(config, "# retained-native-config") {
		panic("native DNS/postconf ordering or idempotence lost")
	}
	record("native_postconf_adds_plugin_dns_directory_once_before_user_edit")
	nrMust(os.Remove("/jffs/scripts/dnsmasq.postconf"))
	for p, b := range originals {
		nrMust(os.WriteFile(p, b, 0755))
	}
	for _, m := range mappings {
		nrMust(os.Remove("/jffs/scripts/" + m.event))
	}
	nrMust(os.Remove("/jffs/scripts/owned-unmanaged-hook"))
	// Run the established online lifecycle with the native Merlin UU callback
	// and the new native boot bridge; all worker/repository endpoints are owned.
	onlineFixtureMain()
	var online map[string]any
	nrMust(json.Unmarshal(nrRead(nrOutput("online_success_result.json")), &online))
	b, e := json.Marshal(map[string]any{"checks": checks, "online": online, "full_upgrade_complete": false, "target_pid1_boot_tested": false})
	nrMust(e)
	fmt.Println("NATIVE_HOOKS_RESULT", string(b))
}
