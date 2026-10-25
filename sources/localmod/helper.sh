#!/bin/sh
# SPDX-License-Identifier: MIT
# Merlin-style postconf editing helpers; callers control their regular expressions.
pc_replace(){ sed -i "s|$1|$2|g" "$3"; }
pc_insert(){ sed -i "\|$1|a\\$2" "$3"; }
pc_append(){ printf '%s\n' "$1" >> "$2"; }
pc_delete(){ sed -i "\|$1|d" "$2"; }
