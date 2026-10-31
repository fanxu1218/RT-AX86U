#!/bin/sh
set -eu
. /work/build/native_lifecycle_setup.sh
/work/build/test-cert-lifecycle restore
