#!/usr/bin/env python3
"""Observe the exact ARM plugin: target mappings, QEMU mappings and Go GC.

No diagnostic flag, supervisor edit or memory limit enters the firmware.
"""
from device_config import compiler_flags
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from prepare_real_plugins import prepare
from run_readonly_linux import run

ROOT = Path(__file__).resolve().parent.parent
PHASES = {"continuous": ("soak-memory", 720),
          "reuse": ("soak-memory-reuse", 660),
          "no-thp": ("soak-memory-no-thp", 660),
          "cycles-no-thp": ("soak-memory-cycles-no-thp", 3600),
          "cycles-probe-no-thp": ("soak-memory-cycles-probe-no-thp", 90),
          "probe": ("soak-memory-probe", 10)}
CYCLES = {"cycles-no-thp": dict(warmup_seconds=120, load_seconds=120, idle_seconds=240, rounds=8, final_idle_seconds=600),
          "cycles-probe-no-thp": dict(warmup_seconds=10, load_seconds=10, idle_seconds=20, rounds=2, final_idle_seconds=20)}
PATHS = ["usr/lib/localmod/httpd_bridge.so", "usr/libexec/localmod/httpd",
         "usr/libexec/localmod/rc.vendor", "usr/libexec/localmod/plugin-txn",
         "usr/libexec/localmod/bootstrap.sh", "rom/etc/koolshare/scripts/base.sh",
         "usr/sbin/curl", "usr/sbin/wget"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate():
    v = json.loads((ROOT / "output/verification.json").read_text())
    assert sha(ROOT / v["image"]) == v["sha256"]
    assert all(v["checks"].values()) and not v["errors"]
    stage, back = ROOT / "build/casefs/rootfs", ROOT / "build/casefs/roundtrip"
    assert all((stage / p).read_bytes() == (back / p).read_bytes() for p in PATHS)
    assert (ROOT / "build/httpd_bridge.so").read_bytes() == (stage / PATHS[0]).read_bytes()
    return v, {p: sha(stage / p) for p in PATHS}


def parse_gc(lines):
    cycles = []
    for line in lines:
        if not line.startswith("gc "):
            continue
        match = re.search(r"gc (\d+) @([\d.]+)s .*? (\d+)->(\d+)->(\d+) MB, (\d+) MB goal", line)
        assert match, line
        number, elapsed, before, after, live, goal = match.groups()
        cycles.append(dict(number=int(number), elapsed_seconds=float(elapsed),
                           heap_start_mib_integer=int(before), heap_end_mib_integer=int(after),
                           live_heap_mib_integer=int(live), goal_mib_integer=int(goal)))
    return cycles


def analyze_cycles(mode, result):
    plan=CYCLES[mode]
    assert result["cycle_schedule"]==plan
    initial=result["coexist_initial_pids"]
    assert set(initial)=={"httpd","httpdb","skipd","uu"}
    for sample in result["samples"]:
        assert {k:p["pid"] for k,p in sample["coexist_processes"].items()}==initial
        assert all(p["rss_kib"]>0 and p["fds"]>0 for p in sample["coexist_processes"].values())
        maps=sample["target_writable_maps"]
        assert maps and sum(m["virtual_kib"] for m in maps)==sample["target_virtual_writable_kib"]
        assert all(m["swap_kib"]==0 for m in maps)
    boundaries=result["phase_boundaries"]
    warm=[s for s in boundaries if s["role"]=="warmup_end"]
    idle=[s for s in boundaries if s["role"]=="idle_end"]
    load=[s for s in boundaries if s["role"]=="load_end"]
    final=[s for s in boundaries if s["role"]=="final_idle_end"]
    assert len(warm)==len(final)==1
    assert [s["round"] for s in idle]==[s["round"] for s in load]==list(range(1,plan["rounds"]+1))
    for s in warm+load+idle+final:
        if s["role"]=="warmup_end": expected=plan["warmup_seconds"]
        elif s["role"]=="final_idle_end": expected=PHASES[mode][1]
        else:
            expected=plan["warmup_seconds"]+s["round"]*(plan["load_seconds"]+plan["idle_seconds"])
            if s["role"]=="load_end":expected-=plan["idle_seconds"]
        assert expected<=s["elapsed_seconds"]<expected+10,(s["role"],s["elapsed_seconds"],expected)
    assert all(result["pressure_page_counts"].get(f"load{i}",0)>=plan["load_seconds"]*3 for i in range(1,plan["rounds"]+1))
    quiet=warm+idle+final
    values=[s["target_mapping_rss_kib"] for s in quiet]
    late=idle[-4:]
    ys=[s["target_mapping_rss_kib"] for s in late]
    mean_x=(len(ys)-1)/2;mean_y=sum(ys)/len(ys)
    slope=sum((i-mean_x)*(y-mean_y) for i,y in enumerate(ys))/sum((i-mean_x)**2 for i in range(len(ys)))
    def map_by_range(sample):return {(m["start_hex"],m["end_hex"]):m for m in sample["target_writable_maps"]}
    first,last=map_by_range(warm[0]),map_by_range(final[0])
    changes=[]
    for key in sorted(first.keys()|last.keys()):
        a,b=first.get(key),last.get(key)
        changes.append(dict(start_hex=key[0],end_hex=key[1],first_rss_kib=a["rss_kib"] if a else None,
                            last_rss_kib=b["rss_kib"] if b else None,
                            rss_delta_kib=b["rss_kib"]-a["rss_kib"] if a and b else None,
                            first_virtual_kib=a["virtual_kib"] if a else None,last_virtual_kib=b["virtual_kib"] if b else None))
    return dict(quiet_baselines=[{k:s[k] for k in ["role","stage","round","elapsed_seconds","target_mapping_rss_kib","qemu_host_mapping_rss_kib","fds","threads","gc_cycles_seen","latest_gc_trace","latest_scav_trace","target_virtual_writable_kib"]} for s in quiet],
                quiet_target_deltas_kib=[b-a for a,b in zip(values,values[1:])],
                late_four_idle_target_span_kib=max(ys)-min(ys),late_four_idle_target_slope_kib_per_round=slope,
                final_idle_target_delta_kib=values[-1]-values[-2],
                writable_mapping_changes_after_warmup=changes,
                interpretation_limit="Finite-window baseline/slope observations only; no RSS threshold is treated as proof of leak freedom.")


def analyze(mode, log, fixture):
    phase, seconds = PHASES[mode]
    text = log.read_text()
    rows = [json.loads(l.removeprefix("MEMORY_RESULT ")) for l in text.splitlines()
            if l.startswith("MEMORY_RESULT ")]
    assert len(rows) == 1 and "SOAK_FAILURE" not in text
    r = rows[0]
    assert r["duration_seconds"] >= r["requested_seconds"] == seconds
    assert r["healthy_queries"] >= (5 if mode == "probe" else seconds * .8)
    assert r["runtime_script_restored"] and r["data_preserved"] and r["uu_launches"] == 1
    assert "SOAK_REAPER orphans_reaped=" in text and "LINUX_READONLY_JOB_STATUS=0" in text
    assert not (ROOT / "build/readonly-guest-write-probe").exists()
    samples = r["samples"]
    assert samples[-1]["elapsed_seconds"] >= seconds
    assert len(samples) >= (2 if mode == "probe" else seconds // 20)
    assert len({s["pid"] for s in samples}) == 1
    for s in samples:
        assert s["target_mapping_rss_kib"] + s["qemu_host_mapping_rss_kib"] == s["smaps_rss_kib"]
        assert s["smaps_rss_kib"] == sum(s["mapping_groups_rss_kib"].values())
        assert s["fds"] > 0 and s["threads"] > 0
        p = s["perfmap"]
        assert p["available"] and p["entries"] > 0
        assert p["entries_in_host_executable_maps"] == p["entries"]
    cycles = parse_gc(r["gc_lines"] or [])
    if mode in CYCLES:
        cycle_observation=analyze_cycles(mode,r)
        if mode=="cycles-no-thp":assert len(cycles)>=CYCLES[mode]["rounds"]*2
    elif mode != "probe":
        assert len(cycles) >= (3 if mode in ("reuse", "no-thp") else 1)
    if mode in ("reuse", "no-thp"):
        assert r["pressure_page_requests"] >= 1000
        assert all(f"name={k}" in text for k in ["warmup", "load1", "idle1", "load2", "idle2"])
    if mode.endswith("no-thp"):
        assert r["diagnostic_process_thp_disabled"]
        assert all(s["thp_enabled"] == 0 and not any(s["mapping_groups_anon_huge_pages_kib"].values()) for s in samples)
    warm = [s for s in samples if s["elapsed_seconds"] >= 60]
    ranges = {}
    for k in ["target_mapping_rss_kib", "qemu_host_mapping_rss_kib", "smaps_rss_kib", "fds", "threads"]:
        if warm:
            ranges[k] = dict(min=min(s[k] for s in warm), max=max(s[k] for s in warm),
                             first=warm[0][k], last=warm[-1][k], delta=warm[-1][k]-warm[0][k])
    report={"mode": mode, "phase": phase, "fixture": fixture, "log_sha256": sha(log),
            "result": r, "gc_cycles": cycles, "post_60s_ranges": ranges,
            "interpretation_limit": "Mapping RSS is not live heap; Go trace values are integer MiB. "
                                    "Perf address union is cumulative JIT addresses, not live allocations. "
                                    "Passing these checks does not assert leak freedom."}
    if mode in CYCLES:report["cycle_observation"]=cycle_observation
    return report


def summary():
    v, production = candidate()
    reports = {}
    for mode in ("continuous", "reuse", "no-thp"):
        path = ROOT / f"output/ddnsgo_memory_{mode}_tests.json"
        report = json.loads(path.read_text())
        assert all(report["checks"].values())
        assert report["candidate_sha256"] == v["sha256"] and report["production_files"] == production
        assert sha(ROOT / f"output/ddnsgo_memory_{mode}.log") == report["log_sha256"]
        assert report["result"]["samples"][-1]["elapsed_seconds"] >= PHASES[mode][1]
        reports[mode] = report
    assert len({r["packaged_binary_sha256"] for r in reports.values()}) == 1
    control = reports["no-thp"]["result"]
    assert all(s["thp_enabled"] == 0 and not any(s["mapping_groups_anon_huge_pages_kib"].values()) for s in control["samples"])
    steps = []
    samples = reports["reuse"]["result"]["samples"]
    for a, b in zip(samples, samples[1:]):
        huge = lambda s: s["mapping_groups_anon_huge_pages_kib"].get("guest rw-p anonymous", 0)
        if b["target_mapping_rss_kib"]-a["target_mapping_rss_kib"] == huge(b)-huge(a) == 2048 and a["gc_cycles_seen"] == b["gc_cycles_seen"]:
            steps.append({"from_seconds": a["elapsed_seconds"], "to_seconds": b["elapsed_seconds"],
                          "target_rss_delta_kib": 2048, "target_anon_huge_pages_delta_kib": 2048,
                          "gc_cycles_between": 0})
    assert steps, "No exact 2 MiB THP/RSS step observed; reassess the interpretation"
    result = {"status": "LOCAL_RSS_DIAGNOSTICS_COMPLETE", "candidate_image": v["image"],
              "candidate_sha256": v["sha256"], "firmware_changed": False,
              "requested_observation_seconds": sum(r["result"]["requested_seconds"] for r in reports.values()),
              "completed_https_queries_including_three_restore_checks_per_run": sum(r["result"]["healthy_queries"] for r in reports.values()),
              "extra_direct_ddns_page_requests": sum(r["result"].get("pressure_page_requests", 0) for r in reports.values()),
              "gc_cycles": sum(len(r["gc_cycles"]) for r in reports.values()),
              "gc_live_heap_mib_integer_values": sorted({g["live_heap_mib_integer"] for r in reports.values() for g in r["gc_cycles"]}),
              "observed_exact_thp_steps": steps,
              "run_reports": {m: {"path": f"output/ddnsgo_memory_{m}_tests.json", "sha256": sha(ROOT / f"output/ddnsgo_memory_{m}_tests.json"), "post_60s_ranges": r["post_60s_ranges"]} for m, r in reports.items()},
              "limits": ["RSS includes program mappings, retained runtime pages and QEMU overhead; it is not live heap",
                         "THP counts are already part of RSS; perf address unions are not active allocations",
                         "Integer Go traces cannot exclude retention below 1 MiB or untested workloads",
                         "No stock kernel, physical router, real UU monitor/account, WAN provider or multiday validation"],
              "checks": {k: True for k in ["three_completed_owned_vm_runs", "candidate_and_production_files_unchanged",
                          "all_raw_logs_and_run_reports_bound_by_hash", "all_requested_windows_measured",
                          "exact_thp_rss_step_observed_without_gc", "process_only_no_thp_control_verified",
                          "configuration_database_certificate_and_owned_uu_data_preserved_in_each_run"]}}
    path = ROOT / "output/ddnsgo_memory_summary_tests.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: val for k, val in result.items() if k not in ("run_reports", "limits", "checks")}), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=PHASES, default="continuous")
    ap.add_argument("--probe", action="store_true", help="ten-second address-separation preflight")
    ap.add_argument("--analyze-log", type=Path, help="analyze an already completed owned-VM log; do not start a VM")
    ap.add_argument("--fixture-identity", type=Path, help="identity saved for an earlier completed run")
    ap.add_argument("--summary", action="store_true", help="validate and combine the three completed runs; do not start a VM")
    a = ap.parse_args()
    mode = "probe" if a.probe else a.mode
    os.chdir(ROOT)
    if a.summary:
        summary()
        return
    v, production = candidate()
    manifest = prepare()
    package = next(p for p in manifest["packages"] if p["module"] == "ddnsgo" and p["phase"] == "current")
    log = ROOT / f"output/ddnsgo_memory_{mode}.log"
    if a.analyze_log:
        assert a.fixture_identity, "Earlier logs require their saved fixture identity"
        fixture = json.loads(a.fixture_identity.read_text())
        source = a.analyze_log.read_bytes()
        analyze(mode, a.analyze_log, fixture)
        log.write_bytes(source)
    else:
        flags = ["sources/zig-aarch64-macos-0.15.2/zig", "cc", "-O2"]
        subprocess.run(flags + ["-target", "aarch64-linux-musl", "-static", "-s", "-o",
                               "build/soak-init-fixture", "build/soak_init_fixture.c"], check=True)
        subprocess.run(flags + ["-target", "aarch64-linux-musl", "-static", "-s", "-o",
                               "build/memory-exec-fixture", "build/memory_exec_fixture.c"], check=True)
        subprocess.run(flags + [*compiler_flags(), "-shared", "-fPIC",
                               "-o", "build/https_trace_fixture.so", "build/https_trace_fixture.c", "-ldl"], check=True)
        sources = ["build/test_soak.go", "build/test_memory.go", "build/memory_cycles.go", "build/httpd_memory.go", "build/native_runtime_client.go",
                   "build/test_online.go", "build/coexist_helpers.go"]
        subprocess.run(["go", "build", "-trimpath", "-o", "build/test-soak"] + sources, check=True,
                       env=dict(os.environ, GOOS="linux", GOARCH="arm64", CGO_ENABLED="0"))
        fixture = {"fixture_executable_sha256": sha(ROOT / "build/test-soak"),
                   "source_sha256": {p: sha(ROOT / p) for p in sources + [
                       "build/memory_exec_fixture.c", "build/soak_init_fixture.c", "build/https_trace_fixture.c"]},
                   "native_fixture_sha256": {p: sha(ROOT / p) for p in [
                       "build/memory-exec-fixture", "build/soak-init-fixture", "build/https_trace_fixture.so"]}}
        (ROOT / "build/real-plugin-phase").write_text(PHASES[mode][0] + "\n")
        print("Running", PHASES[mode][0], flush=True)
        run(log, timeout=300 if mode == "probe" else PHASES[mode][1] + 240)
    capture = log.read_bytes()
    capture_sha = hashlib.sha256(capture).hexdigest()
    (ROOT / f"build/ddnsgo_memory_{mode}.lf_capture.log").write_bytes(capture)
    log.write_text("\n".join(line.rstrip(" \t") for line in capture.decode().splitlines()) + "\n")
    report = analyze(mode, log, fixture)
    report["lf_capture_sha256"] = capture_sha
    report["log_normalization"] = "Runner converts CRLF to LF; published logs also trim trailing spaces/tabs per line. lf_capture_sha256 is before whitespace trimming."
    if mode in ("reuse", "no-thp") or mode in CYCLES:
        assert report["result"]["packaged_binary_sha256"] == package["files"]["bin/ddnsgo"]
        if mode not in CYCLES:assert all(report["result"]["pressure_page_counts"].get(k, 0) >= 400 for k in ["load1", "load2"])
    assert candidate() == (v, production)
    report.update(candidate_image=v["image"], candidate_sha256=v["sha256"], production_files=production,
                  packaged_binary_sha256=package["files"]["bin/ddnsgo"], package_sha256=package["sha256"],
                  status="LOCAL_RSS_DIAGNOSTIC_COMPLETE",
                  checks={key: True for key in [
                      "pinned_archive_and_candidate_readback_hashes_match",
                      "requested_real_elapsed_time_observed",
                      "strict_authenticated_queries_complete_without_retry",
                      "single_ddns_pid_during_observation",
                      "target_plus_qemu_mapping_rss_equals_total",
                      "all_perfmap_addresses_belong_to_qemu_host_executable_mappings",
                      "go_gc_cycles_observed" if mode != "probe" else "address_separation_preflight_only",
                      "original_supervisor_restored_and_normal_queries_pass",
                      "plugin_config_native_db_certificate_and_owned_uu_data_preserved",
                      "uu_heartbeat_and_only_expected_launch",
                      "readonly_workspace_no_guest_nic_no_router",
                      "candidate_and_production_files_unchanged"]})
    if mode in CYCLES:
        report["checks"].update({k:True for k in ["all_rounds_complete_with_real_load_and_idle_windows",
                              "quiet_baselines_captured_before_boundary_page_reads_or_forced_gc",
                              "all_coexistence_service_pids_unchanged",
                              "no_swap_or_transparent_hugepages_in_target_writable_maps",
                              "writable_mapping_totals_match_samples"]})
    (ROOT / f"output/ddnsgo_memory_{mode}_tests.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "mode": mode,
                      "seconds": report["result"]["duration_seconds"],
                      "queries": report["result"]["healthy_queries"],
                      "gc_cycles": len(report["gc_cycles"]), "ranges": report["post_60s_ranges"]}), flush=True)


if __name__ == "__main__":
    main()
