#!/usr/bin/env bash
# Read ~/.claude/state/caveman.on flag. If present, print caveman-rules.md
# to stdout — Claude Code injects stdout as additionalContext for this session.
# If absent or any read fails, exit 0 silently so caveman can never block a session.

set -uo pipefail

flag="${HOME}/.claude/state/caveman.on"
rules_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rules="${rules_dir}/references/caveman-rules.md"

if [[ -f "$flag" ]] && [[ -f "$rules" ]]; then
  cat "$rules"
fi

exit 0
