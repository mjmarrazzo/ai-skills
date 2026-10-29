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

dir="${CLAUDE_USAGE_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/claude-usage}"
cache="$dir/usage.json"
backoff="$dir/backoff-until"

umask 077
if [ -e "$dir" ]; then
  if [ ! -d "$dir" ] || [ ! -O "$dir" ]; then
    echo "claude-usage: unsafe cache dir $dir: not a directory owned by you" >&2; exit 3
  fi
  if [ -n "$(find "$dir" -prune \( -perm -020 -o -perm -002 \) 2>/dev/null)" ]; then
    echo "claude-usage: unsafe cache dir $dir: group- or world-writable" >&2; exit 3
  fi
else
  mkdir -p "$(dirname "$dir")"
  mkdir -m 700 "$dir"
fi

# backoff check

summary_filter='
def epoch: sub("\\.[0-9]+"; "") | capture("^(?<b>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?<z>Z|[+-][0-9]{2}:[0-9]{2})$") | (.b + "Z" | strptime("%Y-%m-%dT%H:%M:%SZ") | mktime) - (if .z == "Z" then 0 else (.z[0:1] + "1" | tonumber) * ((.z[1:3]|tonumber)*3600 + (.z[4:6]|tonumber)*60) end);
def pct: if type == "number" then ((. + 0.5 | floor) | tostring) + "%" else "?%" end;
def when: . as $raw
  | (if type == "string" then ([epoch][0] // null) else null end) as $e
  | if $raw == null then ""
    elif $e == null then " (resets \($raw))"
    else (($e - now) | floor) as $d
      | if $d <= 0 then " (resets now)"
        elif $d >= 86400 then " (resets in \($d / 86400 | floor)d\(($d % 86400) / 3600 | floor)h)"
        else " (resets in \($d / 3600 | floor)h\(($d % 3600) / 60 | floor)m)" end
    end;
def seg($label; $key; $always):
  .[$key] as $b
  | if ($b | type) == "object" then "\($label) \($b.utilization | pct)" + (if $always then ($b.resets_at | when) else "" end)
    elif $always then "\($label) n/a"
    else empty end;
[seg("5h"; "five_hour"; true), seg("7d"; "seven_day"; true), seg("opus"; "seven_day_opus"; false), seg("sonnet"; "seven_day_sonnet"; false)] | join(" · ")
'

emit() {
  if [ "$json" -eq 1 ]; then cat "$cache"; else jq -r "$summary_filter" "$cache"; fi
}

if [ -f "$cache" ]; then
  mtime=$(stat -c %Y "$cache" 2>/dev/null || stat -f %m "$cache" 2>/dev/null || true)
  case $mtime in ''|*[!0-9]*) mtime= ;; esac
  if [ -n "$mtime" ]; then
    age=$(( $(date +%s) - mtime ))
    if [ "$age" -ge 0 ] && [ "$age" -lt 180 ] && jq -e 'type=="object"' "$cache" >/dev/null 2>&1; then
      emit
      exit 0
    fi
  fi
fi

exit 1
