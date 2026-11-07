package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
)

// This runs with authentic Fancyss3.5.28 already installed and its real schema2
// node/config populated. Only the managed center is replaced; UU stays live.
func softcenterUpgrade(t *onlineTest, record func(string)) {
	checks := map[string]bool{}
	pass := func(name string) { checks[name] = true; record("sc1960_" + name) }
	var old struct {
		CoreID              string `json:"core_id"`
		BaselineImageSHA256 string `json:"baseline_image_sha256"`
	}
	nrMust(json.Unmarshal(nrRead("/work/build/softcenter-old-inputs.json"), &old))
	if old.BaselineImageSHA256 != "02ae38a3c0a4fc0942a0608512dd0ab2a9609d2dcf97641e486d9741febd1e50" {
		panic("Unpinned old core")
	}
	retained := map[string]string{}
	for _, key := range []string{"ss_basic_enable", "ss_basic_interval", "fss_node_1", "fss_node_order", "fss_node_current", "fss_data_schema", "ssid_owned", "ssserver_owned", "ddnsgo_localcheck", "ddnsto_owned"} {
		retained[key] = fancyDB(key)
	}
	config := nrRead("/koolshare/configs/fancyss/owned-retained.conf")
	verify := func() {
		for key, value := range retained {
			if fancyDB(key) != value {
				panic("Core/plugin operation changed Fancyss/peer key: " + key)
			}
		}
		if !bytes.Equal(config, nrRead("/koolshare/configs/fancyss/owned-retained.conf")) {
			panic("Core/plugin operation changed Fancyss config")
		}
	}
	fancySet("softcenter_version", "1.9.50")
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "stop-backend")
	nrCommand("/bin/cp", "-a", "/work/build/softcenter-old-core/.", "/jffs/.koolshare/")
	nrMust(os.WriteFile("/jffs/.localmod/core-version", []byte(old.CoreID+"\n"), 0600))
	if strings.TrimSpace(string(nrRead("/koolshare/.soft_ver"))) != "1.9.50" {
		panic("Old1.9.50 runtime fixture not installed")
	}
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "start")
	coBackendReady()
	if fancyDB("softcenter_version") != "1.9.60" || strings.TrimSpace(string(nrRead("/koolshare/.soft_ver"))) != "1.9.60" {
		panic("Actual managed core did not upgrade to1.9.60")
	}
	if !bytes.Equal(nrRead("/jffs/.localmod/core-version"), nrRead("/rom/etc/localmod-core-id")) {
		panic("Core marker does not match new ROM core")
	}
	verify()
	pass("managed_1_9_50_to_1_9_60_preserves_real_fancyss_schema2_config_peers_and_uu")

	code, page := t.s.request("GET", "/Module_Softcenter.asp", "")
	if code != 200 || !strings.Contains(page, "v2 release assets") || strings.Contains(page, "<% nvram_get") || !strings.Contains(page, `R="/Module_Localmod.asp"`) {
		panic(fmt.Sprintf("Native1.9.60 page incomplete or unrendered: %d bytes%d", code, len(page)))
	}
	marker := `<script type="module">`
	body := func(text string) string {
		begin := strings.Index(text, marker)
		if begin < 0 {
			panic("No frontend module")
		}
		text = text[begin+len(marker):]
		end := strings.Index(text, "</script>")
		if end < 0 {
			panic("Unterminated frontend module")
		}
		return text[:end]
	}
	if body(page) != body(string(nrRead("/rom/etc/koolshare/webs/Module_Softcenter.asp"))) {
		panic("Original HTTPS truncated/changed inline frontend")
	}
	pass("original_https_renders_complete_large_inline_frontend_with_same_origin_status_entry")
	assets := regexp.MustCompile(`/res/soft-v19/assets/[A-Za-z0-9_.-]+\.(?:css|js|png|jpg)`).FindAllString(page, -1)
	assets = append(assets, "/res/soft-v19/assets/index-DhXhkv_Y.js")
	seen := map[string]bool{}
	for _, asset := range assets {
		if seen[asset] {
			continue
		}
		seen[asset] = true
		c, b := t.s.request("GET", asset, "")
		if c != 200 || !bytes.Equal([]byte(b), nrRead("/rom/etc/koolshare"+asset)) {
			panic(fmt.Sprintf("New frontend asset missing/truncated: %s code%d bytes%d", asset, c, len(b)))
		}
	}
	if len(seen) != 5 {
		panic(fmt.Sprintf("Unexpected frontend asset coverage%d", len(seen)))
	}
	pass("all_five_pinned_frontend_assets_served_byte_exact_through_original_https")
	code, meta := t.s.request("GET", "/_api/soft", "")
	if code != 200 || !strings.Contains(meta, "1.9.60") {
		panic("Frontend metadata API does not expose new version")
	}
	pass("new_frontend_metadata_api_reports_1_9_60")

	var payloads map[string]json.RawMessage
	nrMust(json.Unmarshal(nrRead("/work/build/softcenter_frontend_payloads.json"), &payloads))
	send := func(kind string, app onlineApp) {
		var payload struct {
			ID     int               `json:"id"`
			Method string            `json:"method"`
			Params []string          `json:"params"`
			Fields map[string]string `json:"fields"`
		}
		nrMust(json.Unmarshal(payloads[kind], &payload))
		t.id++
		payload.ID = t.id
		replacements := map[string]string{"@VERSION@": app.Version, "@MD5@": app.MD5, "@TAR_URL@": app.TarURL, "@HOME_URL@": "https://repo.fixture.test:35001"}
		for key, value := range payload.Fields {
			if replacement, ok := replacements[value]; ok {
				payload.Fields[key] = replacement
			}
		}
		if kind == "update" {
			if _, ok := payload.Fields["softcenter_home_url"]; ok {
				panic("New update payload incorrectly supplied source field")
			}
		}
		blob, e := json.Marshal(payload)
		nrMust(e)
		c, b := t.s.request("POST", "/_api/", string(blob))
		if c != 200 || !strings.Contains(b, strconv.Itoa(t.id)) {
			panic(fmt.Sprintf("Distributed frontend %s RPC failed%d", kind, c))
		}
	}
	fancySet("onlineprobe_config", "user-retained")
	send("install", t.repo.catalog("v1"))
	t.wait(true)
	t.plugin("1.0")
	verify()
	pass("actual_v2_frontend_install_payload_runs_native_backend_with_fancyss_and_uu")
	send("update", t.repo.catalog("v2"))
	t.wait(true)
	t.plugin("2.0")
	verify()
	pass("actual_v2_frontend_update_without_source_field_updates_ordinary_plugin_preserving_config_fancyss_uu")
	app := t.repo.catalog("v2")
	t.repo.mu.Lock()
	before := t.repo.requests["/"+app.TarURL]
	t.repo.mu.Unlock()
	send("update", app)
	t.wait(true)
	t.plugin("2.0")
	verify()
	t.repo.mu.Lock()
	after := t.repo.requests["/"+app.TarURL]
	t.repo.mu.Unlock()
	if before != after {
		panic("Same-version skip unexpectedly downloaded/executed package")
	}
	pass("same_version_skip_is_explicit_and_does_not_block_real_newer_updates")
	t.stopPlugin()
	send("uninstall", app)
	t.wait(true)
	verify()
	if fancyDB("softcenter_module_onlineprobe_version") != "" {
		panic("V2 uninstall registration left")
	}
	if _, e := os.Stat("/koolshare/webs/Module_onlineprobe.asp"); !os.IsNotExist(e) {
		panic("V2 uninstall page left")
	}
	pass("actual_v2_frontend_uninstall_removes_only_owned_plugin_preserving_real_fancyss_uu")
	nrCommand("/bin/sh", "/usr/libexec/localmod/bootstrap.sh", "restart")
	coBackendReady()
	verify()
	if fancyDB("softcenter_version") != "1.9.60" {
		panic("Center restart lost core version")
	}
	pass("center_restart_after_plugin_lifecycle_keeps_1_9_60_fancyss_and_uu")
	// The lifecycle itself exercises and reports authentic Fancyss upgrades,
	// uninstall and shared-JQ retention after this core transition.
	fmt.Printf("SOFTCENTER_RESULT %s\n", mustFancyJSON(map[string]any{"checks": checks, "version": fancyDB("softcenter_version"), "frontend_assets": len(seen), "native_page_bytes": len(page), "baseline_image_sha256": old.BaselineImageSHA256, "uu_api_requests": t.uu.calls.Load(), "uu_downloads": t.uu.downloads.Load(), "fancyss_config_sha256": fancySHA(config), "configs_path": filepath.Base("/koolshare/configs/fancyss")}))
}
