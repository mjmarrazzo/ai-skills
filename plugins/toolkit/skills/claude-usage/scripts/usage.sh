#!/bin/sh
# usage.sh — print Claude subscription usage (5h / 7d windows) from the OAuth usage endpoint.
#
# Usage: usage.sh [--json] | -h | --help
#   stdout: one summary line, or the raw response body with --json
#   exit:   0 ok · 1 fetch failed · 2 bad usage · 3 setup problem · 4 rate limited
set -eu

usage() { echo "usage: usage.sh [--json] | -h | --help"; }

json=0
case $# in
  0) ;;
  1) case $1 in
       -h|--help) usage; exit 0 ;;
       --json) json=1 ;;
       *) usage >&2; exit 2 ;;
     esac ;;
  *) usage >&2; exit 2 ;;
esac

for dep in curl jq; do
  command -v "$dep" >/dev/null 2>&1 || { echo "claude-usage: missing dependency: $dep" >&2; exit 3; }
done
