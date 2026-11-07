#!/bin/sh
# Test-only CPU wrappers for Alpine-root model jobs (no binfmt registration).
# Full-root read-only jobs execute the actual staged helpers directly.
mkdir -p /usr/libexec/localmod
cp /work/sources/localmod/plugin-compat.sh /work/sources/localmod/fancyss-packages.sha256 /usr/libexec/localmod/
for helper in archive-guard plugin-run log-limit localmod-status; do
 printf '#!/bin/sh\nexec /usr/bin/qemu-arm -L /work/build/casefs/official_rootfs /work/build/%s "$@"\n' "$helper" > "/usr/libexec/localmod/$helper"
 chmod 755 "/usr/libexec/localmod/$helper"
done
