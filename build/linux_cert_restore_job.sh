#!/bin/sh
set -eu
. /work/build/native_lifecycle_setup.sh
export LOCALMOD_TLS_START_TIMEOUT=60s
/work/build/test-cert-lifecycle restore
