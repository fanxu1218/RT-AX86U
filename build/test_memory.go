package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

type memMap struct {
	Start, End                               uint64
	Perm, Path                               string
	RSS, PrivateDirty, Anonymous, Swap, Huge int
}

func smaps(p int) []memMap {
	b := nrRead(fmt.Sprintf("/proc/%d/smaps", p))
	var out []memMap
	for _, line := range strings.Split(string(b), "\n") {
		f := strings.Fields(line)
		if len(f) >= 5 && strings.Contains(f[0], "-") {
			a := strings.SplitN(f[0], "-", 2)
			lo, e := strconv.ParseUint(a[0], 16, 64)
			if e != nil {
				continue
			}
			hi, e := strconv.ParseUint(a[1], 16, 64)
			nrMust(e)
			path := ""
			if len(f) > 5 {
				path = strings.Join(f[5:], " ")
			}
			out = append(out, memMap{Start: lo, End: hi, Perm: f[1], Path: path})
			continue
		}
		if len(out) == 0 || len(f) < 2 {
			continue
		}
		n, _ := strconv.Atoi(f[1])
		r := &out[len(out)-1]
		switch f[0] {
		case "Rss:":
			r.RSS = n
		case "Private_Dirty:":
			r.PrivateDirty = n
		case "Anonymous:":
			r.Anonymous = n
		case "Swap:":
			r.Swap = n
		case "AnonHugePages:":
			r.Huge = n
		}
	}
	return out
}
func perfStats(p int, maps []memMap) map[string]any {
	b, e := os.ReadFile(fmt.Sprintf("/tmp/perf-%d.map", p))
	if e != nil {
		return map[string]any{"available": false}
	}
	if len(b) > 32*1024*1024 {
		panic("perf map exceeded diagnostic bound")
	}
	type interval struct{ lo, hi uint64 }
	var spans []interval
	entries, matched := 0, 0
	for _, line := range strings.Split(string(b), "\n") {
		f := strings.Fields(line)
		if len(f) < 3 {
			continue
		}
		lo, e := strconv.ParseUint(f[0], 16, 64)
		if e != nil {
			continue
		}
		n, e := strconv.ParseUint(f[1], 16, 64)
		if e != nil || n == 0 {
			continue
		}
		entries++
		for _, m := range maps {
			if lo >= m.Start && lo+n <= m.End && strings.Contains(m.Perm, "x") && m.Start >= 0x200000000 {
				matched++
				spans = append(spans, interval{lo, lo + n})
				break
			}
		}
	}
	sort.Slice(spans, func(i, j int) bool { return spans[i].lo < spans[j].lo })
	var covered, start, end uint64
	for i, r := range spans {
		if i == 0 {
			start, end = r.lo, r.hi
			continue
		}
		if r.lo > end {
			covered += end - start
			start, end = r.lo, r.hi
		} else if r.hi > end {
			end = r.hi
		}
	}
	if len(spans) > 0 {
		covered += end - start
	}
	return map[string]any{"available": true, "file_bytes": len(b), "entries": entries, "entries_in_host_executable_maps": matched, "host_executable_address_union_bytes": covered}
}
func memSample(p int, started time.Time) map[string]any {
	maps := smaps(p)
	guest, host, total := 0, 0, 0
	groups := map[string]int{}
	hugeGroups := map[string]int{}
	for _, m := range maps {
		total += m.RSS
		bucket := "host"
		if m.Start >= 0x100000000 && m.End <= 0x200000000 {
			guest += m.RSS
			bucket = "guest"
		} else {
			host += m.RSS
		}
		name := m.Path
		if name == "" {
			name = "anonymous"
		}
		groups[bucket+" "+m.Perm+" "+name] += m.RSS
		hugeGroups[bucket+" "+m.Perm+" "+name] += m.Huge
	}
	status := nrRead(fmt.Sprintf("/proc/%d/status", p))
	threads, thp := 0, -1
	scan := bufio.NewScanner(bytes.NewReader(status))
	for scan.Scan() {
		f := strings.Fields(scan.Text())
		if len(f) > 1 && f[0] == "Threads:" {
			threads, _ = strconv.Atoi(f[1])
		}
		if len(f) > 1 && f[0] == "THP_enabled:" {
			thp, _ = strconv.Atoi(f[1])
		}
	}
	if guest < 4000 || host < 1000 || guest+host != total {
		panic(fmt.Sprintf("invalid address separation guest=%d host=%d", guest, host))
	}
	row := map[string]any{"elapsed_seconds": time.Since(started).Seconds(), "pid": p, "status_rss_kib": rss(p), "smaps_rss_kib": total, "target_mapping_rss_kib": guest, "qemu_host_mapping_rss_kib": host, "fds": fds(p), "threads": threads, "mapping_groups_rss_kib": groups, "perfmap": perfStats(p, maps)}
	gcCount, lastGC := 0, ""
	for _, line := range strings.Split(string(nrRead("/tmp/ddnsgo-memory-runtime.log")), "\n") {
		if strings.HasPrefix(line, "gc ") {
			gcCount++
			lastGC = line
		}
	}
	row["gc_cycles_seen"], row["latest_gc_trace"] = gcCount, lastGC
	row["mapping_groups_anon_huge_pages_kib"] = hugeGroups
	row["thp_enabled"] = thp
	b, _ := json.Marshal(row)
	fmt.Printf("MEMORY_SAMPLE %s\n", b)
	return row
}

func memoryPage(client *http.Client) {
	r, e := client.Get("http://127.0.0.1:9876/")
	nrMust(e)
	defer r.Body.Close()
	b, e := io.ReadAll(r.Body)
	nrMust(e)
	if r.StatusCode != 200 || !bytes.Contains(bytes.ToLower(b), []byte("ddns")) {
		panic("memory workload received an incomplete DDNS page")
	}
}

func memoryStage(reuse bool, elapsed time.Duration) string {
	if !reuse {
		return "continuous"
	}
	switch {
	case elapsed < 60*time.Second:
		return "warmup"
	case elapsed < 180*time.Second:
		return "load1"
	case elapsed < 360*time.Second:
		return "idle1"
	case elapsed < 480*time.Second:
		return "load2"
	default:
		return "idle2"
	}
}

func memoryRun(x *soak) {
	noTHP := os.Args[1] == "soak-memory-no-thp"
	binarySHA := fmt.Sprintf("%x", sha256.Sum256(nrRead("/koolshare/bin/ddnsgo")))
	fmt.Printf("MEMORY_EXECUTABLE sha256=%s\n", binarySHA)
	fmt.Printf("QEMU_MEMORY_VERSION %s\n", nrCommand("/usr/bin/qemu-arm", "-version"))
	fmt.Printf("MEMORY_KERNEL_PAGE_POLICY\n%s\n", nrCommand("/bin/sh", "-c", "grep '^KernelPageSize:' /proc/self/smaps | head -1; for f in enabled defrag; do cat /sys/kernel/mm/transparent_hugepage/$f; done"))
	help := nrCommand("/usr/bin/qemu-arm", "-h")
	fmt.Printf("QEMU_MEMORY_OPTIONS\n%s\n", help)
	old := pid("ddnsgo")
	nrCommand("/bin/sh", "-c", ". /koolshare/scripts/base.sh; perpctl d ddnsgo")
	waitGone(old)
	path := "/koolshare/perp/ddnsgo/rc.main"
	original := nrRead(path)
	if strings.Count(string(original), "exec ddnsgo ") != 1 {
		panic("unexpected original supervisor script")
	}
	lines := strings.Split(string(original), "\n")
	launch := "exec env QEMU_GUEST_BASE=0x100000000 QEMU_PERFMAP=1 GODEBUG=gctrace=1,scavtrace=1 "
	if noTHP {
		launch += "/work/build/memory-exec-fixture /koolshare/bin/ddnsgo "
	} else {
		launch += "ddnsgo "
	}
	for i, line := range lines {
		if strings.Contains(line, "exec ddnsgo ") {
			lines[i] = strings.Replace(line, "exec ddnsgo ", launch, 1) + " >/tmp/ddnsgo-memory-runtime.log 2>&1"
		}
	}
	nrMust(os.WriteFile(path, []byte(strings.Join(lines, "\n")), 0755))
	nrCommand("/bin/sh", "-c", ". /koolshare/scripts/base.sh; perpctl u ddnsgo")
	for i := 0; i < 100; i++ {
		if n := strings.TrimSpace(nrCommand("/bin/sh", "-c", "pidof ddnsgo || true")); n != "" {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	target := pid("ddnsgo")
	if target == old {
		panic("diagnostic launch did not replace PID")
	}
	// A PID exists while UPX is still unpacking, before the HTTP listener binds.
	// Readiness is outside the measured window and does not retry any RPC.
	ready := false
	for deadline := time.Now().Add(10 * time.Second); time.Now().Before(deadline); {
		conn, e := net.DialTimeout("tcp", "127.0.0.1:9876", 100*time.Millisecond)
		if e == nil {
			conn.Close()
			ready = true
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	if !ready {
		panic("diagnostic DDNS-Go listener not ready within 10 seconds")
	}
	fmt.Printf("MEMORY_PROCESS pid=%d original_pid=%d executable_sha256_checked_by_host=true flags=GODEBUG:gctrace,scavtrace QEMU_GUEST_BASE:0x100000000\n", target, old)
	fmt.Printf("MEMORY_MAPS_BEGIN\n%s\nMEMORY_MAPS_END\n", nrRead(fmt.Sprintf("/proc/%d/maps", target)))
	seconds := 720
	reuse := os.Args[1] == "soak-memory-reuse" || noTHP
	if reuse {
		seconds = 660
	}
	if os.Args[1] == "soak-memory-probe" {
		seconds = 10
	}
	started := time.Now()
	startedUTC := started.UTC().Format(time.RFC3339Nano)
	pageClient := &http.Client{Timeout: 3 * time.Second, Transport: &http.Transport{DisableKeepAlives: true}}
	pageRequests := 0
	pageCounts := map[string]int{}
	stageStarts := map[string]float64{}
	stage := "continuous"
	var samples []map[string]any
	samples = append(samples, memSample(target, started))
	next := started.Add(20 * time.Second)
	for time.Since(started) < time.Duration(seconds)*time.Second {
		at := time.Now()
		current := memoryStage(reuse, time.Since(started))
		if reuse && current != stage {
			stage = current
			x.data()
			stageStarts[stage] = time.Since(started).Seconds()
			fmt.Printf("MEMORY_STAGE elapsed_seconds=%.3f name=%s\n", time.Since(started).Seconds(), stage)
		}
		x.query([]string{"status", "version"}[x.queries%2])
		if strings.HasPrefix(stage, "load") {
			for i := 0; i < 5; i++ {
				memoryPage(pageClient)
				pageRequests++
				pageCounts[stage]++
			}
		}
		if time.Now().After(next) {
			if pid("ddnsgo") != target {
				panic("diagnostic process unexpectedly restarted")
			}
			if !strings.HasPrefix(stage, "idle") {
				x.data()
			} else {
				coUUAlive(x.u.pid)
			}
			row := memSample(target, started)
			row["stage"] = stage
			samples = append(samples, row)
			next = next.Add(20 * time.Second)
		}
		if d := time.Until(at.Add(time.Second)); d > 0 {
			time.Sleep(d)
		}
	}
	x.data()
	samples = append(samples, memSample(target, started))
	runtimeLog := nrRead("/tmp/ddnsgo-memory-runtime.log")
	var gcLines []string
	for _, line := range strings.Split(string(runtimeLog), "\n") {
		if strings.HasPrefix(line, "gc ") || strings.HasPrefix(line, "scav ") {
			gcLines = append(gcLines, line)
		}
	}
	fmt.Printf("GO_MEMORY_RUNTIME_LOG\n%s\nGO_MEMORY_RUNTIME_LOG_END\n", strings.Join(gcLines, "\n"))
	nrCommand("/bin/sh", "-c", ". /koolshare/scripts/base.sh; perpctl d ddnsgo")
	waitGone(target)
	nrMust(os.WriteFile(path, original, 0755))
	nrCommand("/bin/sh", "-c", ". /koolshare/scripts/base.sh; perpctl u ddnsgo")
	time.Sleep(time.Second)
	for i := 0; i < 3; i++ {
		x.query([]string{"status", "version"}[i%2])
	}
	x.data()
	result := map[string]any{"duration_seconds": time.Since(started).Seconds(), "requested_seconds": seconds, "healthy_queries": x.queries, "samples": samples, "gc_lines": gcLines, "runtime_script_restored": bytes.Equal(original, nrRead(path)), "data_preserved": true, "uu_launches": x.launches, "pressure_page_requests": pageRequests, "pressure_page_counts": pageCounts, "stage_start_seconds": stageStarts, "started_utc": startedUTC, "finished_utc": time.Now().UTC().Format(time.RFC3339Nano), "packaged_binary_sha256": binarySHA, "diagnostic_process_thp_disabled": noTHP}
	b, e := json.Marshal(result)
	nrMust(e)
	fmt.Printf("MEMORY_RESULT %s\n", b)
}
