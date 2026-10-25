# localmod2 adapter

This experimental RT-AX86U firmware retains the exact ASUS 24437 kernel, modules, vendor rc, HTTPd and xtables-multi binaries. Small launchers relocate rc and HTTPd and preload narrowly scoped adapters. It is not device tested. See `../../output/官改候选版说明.md` and the machine-readable test reports.

## Event contract

- `rc_bridge.c` observes imported vendor APIs: WAN state writes, service-queue parsing, init's `sigwaitinfo` boundary, USB mount/unmount calls, and dnsmasq execution. Pending WAN notifications flush after the native handler reaches idle or a helper exits; forked helpers discard inherited pending events.
- `runtime.c` and `event.c` provide a root-only queue in `/tmp/.localmod`, ordered asynchronous execution, blocking pre-operation hooks, 120-second script limits and process-group cleanup. Before unmount and services-stop, a queue barrier finishes earlier asynchronous work. Unmount retries emit one stop hook per mount lifetime.
- `dispatch.sh` runs existing `/jffs/scripts` hooks, then the appropriate software-center S/V/T/N/M/U helper. Per-event context prevents a legacy user hook and the dispatcher from running the same center helper twice. User hook files are not rewritten.
- Native NVRAM reads/writes outside the observed contract pass through. The script-enable flag is read by a fresh `/bin/nvram` process, avoiding a second getter that could overwrite the vendor getter's shared buffer or a borrowed argument. Both the adapter and dispatcher honor `jffs2_scripts=0`.
- `restore.c` preserves the vendor restore program and exit status. It inserts the private API chain into the same filter-table COMMIT, emits NAT/firewall events only after successful application, and handles stdin, file input, dry-run and noflush. Explicit administration through other iptables entry points can still alter those rules.
- DNS compatibility provides `dnsmasq.conf`, `.add`, `/jffs/configs/dnsmasq.d` and `dnsmasq.postconf` before daemon launch. A generated baseline prevents repeated additions from accumulating. `helper.sh` supplies the common postconf editing helpers.

`bootstrap.sh prepare` runs when JFFS mounts and performs a managed-core migration without copying old Alpha-3 plugins into the new center. Upgrades from an existing localmod installation retain current plugins, the database and user hooks. `start` runs at the native init idle boundary. Database shutdown first uses a bounded read barrier to commit pending writes, then waits for the old skipd process to exit; rapid service restarts retain immediately written values. Compatibility entries include `jffsinit.sh`, `kscore.sh` and `service start/stop/restart_skipd`. A recovery marker stops the private backend and allows the launchers to run the unmodified vendor binaries.

The HTTPd adapter still relies on the real vendor login boundary, whose test is a fixture. It also supports encoded query values and upload query parameters without permitting encoded path traversal. Native model-specific kernel modules, arbitrary Merlin Addons APIs, every VPN/QoS hook and all third-party plugins are outside the verified compatibility set.

## Local build

The prepared macOS Apple Silicon workspace needs Zig 0.15.2, Go, Python with `ubi-reader==0.8.16` and `pyelftools==0.32`, the signed Apple Virtualization builder, pinned Alpine packages and the case-sensitive source extractions.

```sh
# Run from the repository root. Attach only if the volume is currently detached.
hdiutil attach -nobrowse -mountpoint "$PWD/build/casefs" "$PWD/build/RTAX86UBuild.sparseimage"
python3 build/build_candidate.py
```

A fresh mounted volume can be populated with `analysis/.venv/bin/python build/extract_casefs.py`. The scripts require the downloaded official and donor inputs and prepared toolchain; this is not a one-command build from a fresh clone. `--compile-only` builds the adapters and fixtures without assembling an image.

The build runs the existing API/file mapping tests, rc lifecycle fixtures, live legacy-netfilter reload probes and a controlled offline installation through packaged httpdb/skipd/dbus. Alpine curl, xtables and the process-launch helper are used inside the ARM64 guest; the target's old proc/iptables ABI cannot be fully exercised through user-mode QEMU. QEMU executables are given skipd/httpdb names in the lifecycle fixture so pidof/killall see the same names as on the router. No third-party plugin installation, external service or router is exercised.

Offline CRC and filesystem checks do not establish flash acceptance, real boot, vendor TLS/login integration, wireless stability or UU acceleration.
