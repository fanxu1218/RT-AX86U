#!/bin/sh
# SPDX-License-Identifier: MIT
# Narrow, hash-pinned adaptations after archive validation, before checkpoint.
# Unknown scripts keep their upstream behavior; no heuristic code rewriting.
set -eu
module=$1
stage=$2
[ "$stage" = "/tmp/$module" ] && [ -d "$stage" ] && [ ! -L "$stage" ] || exit 1
case "$module" in
 frpc) target=$stage/install.sh; kind=frpc;;
 pushplus) target=$stage/scripts/pushplus_config.sh; kind=pushplus;;
 *) exit 0;;
esac
[ -f "$target" ] && [ ! -L "$target" ] || exit 0
digest=$(/usr/sbin/openssl dgst -sha256 "$target") || exit 1
digest=${digest##* }
case "$kind:$digest" in
 frpc:42164ef46201d0fa33805196818fd01666ce46638f0e74d8b7e340fa01127a3e)
  expected=9cbecaf7af1525c6c1c79395e0c8887b07eadb60bcd8b48bb7b697b759fdabc5;;
 pushplus:e1ff1be042266bce1f5e73b5a69cd82da2b9c72f278aef3c5e3a78d3fb743d21)
  expected=0c5c059fd38886c40f20acf9d48665aa92cd4fa5fb523dd76c696b91580322b5;;
 *) exit 0;;
esac
temporary=$target.localmod-compat
(umask 077;set -C; : > "$temporary") || exit 1
trap 'rm -f "$temporary"' EXIT HUP INT TERM
case "$kind" in
 frpc)
  sed 's@^rm -rf "/tmp/${module}"\* @rm -rf "/tmp/${module}" @' "$target" > "$temporary";;
 pushplus)
  cat "$target" > "$temporary"
  printf '\n# localmod: complete native HTTPS RPCs; boot/stop hooks have no numeric ID.\ncase "$1" in ""|*[!0-9]*) ;; *) http_response "$1";; esac\n' >> "$temporary";;
esac
digest=$(/usr/sbin/openssl dgst -sha256 "$temporary") || exit 1
[ "${digest##* }" = "$expected" ] || { echo 'localmod: compatibility output mismatch; installer not run';exit 1; }
chmod 755 "$temporary"
mv -f "$temporary" "$target"
