# localmod1 adapter

This is an experimental, locally assembled RT-AX86U official-base firmware candidate. See `../../output/官改候选版说明.md` for the verified scope and unresolved device, authentication, firewall-lifecycle, and plugin-compatibility limits.

`launcher.c` builds an ARM32 HTTPd wrapper and a PID-1 init wrapper. The original vendor HTTPd and rc remain intact. `httpd_bridge.c` handles only software-center APIs and file fallbacks. It replays API access through the stock authenticated index handler and checks exported authentication state before forwarding. Its preload variable is removed before vendor child programs execute. `bootstrap.sh` starts the separate software-center state after JFFS appears. `Module_Localmod.asp` is an authenticated static information page under the vendor ASP handler.

## Local rebuild

Run in the existing workspace with the downloaded Zig 0.15.2, Go, Python ubi-reader virtual environment, signed Apple Virtualization builder, Alpine kernel/initramfs and mtd-utils already prepared:

```sh
# Only needed if the dedicated build volume has been detached.
hdiutil attach -nobrowse -mountpoint /Users/apple/Desktop/RT-AX86U/build/casefs /Users/apple/Desktop/RT-AX86U/build/RTAX86UBuild.sparseimage
python3 /Users/apple/Desktop/RT-AX86U/build/build_candidate.py
```

The case-sensitive canonical official and donor extractions must already exist inside `build/casefs`. A fresh volume can be populated using `analysis/.venv/bin/python build/extract_casefs.py` after mounting it. The sparse image creation command used was `hdiutil create -size 2g -type SPARSE -fs 'Case-sensitive APFS' -volname RTAX86UBuild -nospotlight build/RTAX86UBuild`.

The build script compiles the adapter and fixtures, stages the overlay, creates UBIFS in a temporary networkless Linux guest, runs ARM adapter/backend/file-mapping fixtures, repacks the official pure-UBI container, and verifies a round-trip extraction. It does not contact or flash a router. Do not use case-insensitive extracted trees or copy host xattrs into mkfs input.

The authentication fixture models the vendor boundary; it is not an end-to-end test of the real vendor HTTPd. Offline filesystem and CRC checks cannot establish flash acceptance, actual boot, wireless stability, or UU acceleration.
