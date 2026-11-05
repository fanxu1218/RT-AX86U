package main

import (
	"fmt"
	"net/http"
	"strings"
	"time"
)

type memoryCycleSchedule struct {
	WarmupSeconds    int `json:"warmup_seconds"`
	LoadSeconds      int `json:"load_seconds"`
	IdleSeconds      int `json:"idle_seconds"`
	Rounds           int `json:"rounds"`
	FinalIdleSeconds int `json:"final_idle_seconds"`
}

func cycleSchedule(phase string) (memoryCycleSchedule, bool) {
	switch phase {
	case "soak-memory-cycles-no-thp":
		return memoryCycleSchedule{120, 120, 240, 8, 600}, true
	case "soak-memory-cycles-probe-no-thp":
		return memoryCycleSchedule{10, 10, 20, 2, 20}, true
	}
	return memoryCycleSchedule{}, false
}

func (p memoryCycleSchedule) seconds() int {
	return p.WarmupSeconds + p.Rounds*(p.LoadSeconds+p.IdleSeconds) + p.FinalIdleSeconds
}

func memorySeconds(phase string) int {
	if p, ok := cycleSchedule(phase); ok {
		return p.seconds()
	}
	switch phase {
	case "soak-memory-probe":
		return 10
	case "soak-memory-reuse", "soak-memory-no-thp":
		return 660
	default:
		return 720
	}
}

type memoryCycleStage struct {
	name  string
	round int
}

func (p memoryCycleSchedule) stage(elapsed time.Duration) memoryCycleStage {
	seconds := elapsed.Seconds()
	if seconds < float64(p.WarmupSeconds) {
		return memoryCycleStage{"warmup", 0}
	}
	t := seconds - float64(p.WarmupSeconds)
	i := int(t / float64(p.LoadSeconds+p.IdleSeconds))
	if i >= p.Rounds {
		return memoryCycleStage{"final_idle", p.Rounds}
	}
	if t-float64(i*(p.LoadSeconds+p.IdleSeconds)) < float64(p.LoadSeconds) {
		return memoryCycleStage{fmt.Sprintf("load%d", i+1), i + 1}
	}
	return memoryCycleStage{fmt.Sprintf("idle%d", i+1), i + 1}
}

type memoryCycleObservation struct {
	samples, boundaries []map[string]any
	pageRequests        int
	pageCounts          map[string]int
	stageStarts         map[string]float64
	initialPIDs         map[string]int
}

func observeMemoryCycles(x *soak, target int, started time.Time, plan memoryCycleSchedule) memoryCycleObservation {
	o := memoryCycleObservation{pageCounts: map[string]int{}, stageStarts: map[string]float64{},
		initialPIDs: map[string]int{"httpd": x.s.cmd.Process.Pid, "httpdb": pid("httpdb"), "skipd": pid("skipd"), "uu": x.u.pid}}
	take := func(role string, stage memoryCycleStage) map[string]any {
		if pid("ddnsgo") != target {
			panic("DDNS-Go changed PID during repeated memory workload")
		}
		live := map[string]int{"httpd": x.s.cmd.Process.Pid, "httpdb": pid("httpdb"), "skipd": pid("skipd"), "uu": x.u.pid}
		processes := map[string]any{}
		for name, p := range live {
			if p != o.initialPIDs[name] {
				panic("unexpected coexistence process restart: " + name)
			}
			r, f := rss(p), fds(p)
			if r <= 0 || f <= 0 {
				panic("invalid coexistence resource sample: " + name)
			}
			processes[name] = map[string]int{"pid": p, "rss_kib": r, "fds": f}
		}
		coUUAlive(x.u.pid)
		row := memSample(target, started, map[string]any{"role": role, "stage": stage.name, "round": stage.round,
			"coexist_processes": processes, "coexist_rss_scope": "Linux user-mode QEMU process, target plus emulator"})
		o.samples = append(o.samples, row)
		return row
	}
	current := plan.stage(0)
	take("initial", current)
	o.stageStarts[current.name] = time.Since(started).Seconds()
	fmt.Printf("MEMORY_STAGE elapsed_seconds=%.3f name=%s round=%d\n", time.Since(started).Seconds(), current.name, current.round)
	client := &http.Client{Timeout: 3 * time.Second, Transport: &http.Transport{DisableKeepAlives: true}}
	next := started.Add(20 * time.Second)
	for time.Since(started) < time.Duration(plan.seconds())*time.Second {
		at := time.Now()
		stage := plan.stage(time.Since(started))
		if stage != current {
			role := "idle_end"
			if current.name == "warmup" {
				role = "warmup_end"
			} else if strings.HasPrefix(current.name, "load") {
				role = "load_end"
			}
			o.boundaries = append(o.boundaries, take(role, current))
			// Capture the quiet baseline before this integrity check reads a page.
			x.data()
			current = stage
			o.stageStarts[current.name] = time.Since(started).Seconds()
			fmt.Printf("MEMORY_STAGE elapsed_seconds=%.3f name=%s round=%d\n", time.Since(started).Seconds(), current.name, current.round)
		}
		x.query([]string{"status", "version"}[x.queries%2])
		if strings.HasPrefix(current.name, "load") {
			for i := 0; i < 5; i++ {
				memoryPage(client)
				o.pageRequests++
				o.pageCounts[current.name]++
			}
		}
		if time.Now().After(next) {
			if current.name == "warmup" || strings.HasPrefix(current.name, "load") {
				x.data()
			} else {
				coUUAlive(x.u.pid)
			}
			take("periodic", current)
			next = next.Add(20 * time.Second)
		}
		if d := time.Until(at.Add(time.Second)); d > 0 {
			time.Sleep(d)
		}
	}
	// No page read or forced GC before the final quiet observation.
	o.boundaries = append(o.boundaries, take("final_idle_end", current))
	return o
}
