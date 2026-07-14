#!/bin/sh
# slug.sh — compute a knowledge-capture entry slug per references/entry-format.md.
#
# Usage: slug.sh "<title>" < body
#   stdin: the entry body used for the content hash, exactly
#          context + "\n" + lesson + "\n" + source_block
#   stdout: <YYYY-MM-DD>-<kebab(title)>-<6char-content-hash>
set -eu

[ $# -eq 1 ] || { echo "usage: slug.sh \"<title>\" < body" >&2; exit 2; }

# kebab(title): lowercase, ASCII letters/digits only, runs of others -> '-',
# collapse '-' runs, trim leading/trailing '-', max 60 chars at a word boundary.
kebab=$(printf '%s' "$1" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -e 's/[^a-z0-9]/-/g' -e 's/--*/-/g' -e 's/^-//' -e 's/-$//')
if [ "${#kebab}" -gt 60 ]; then
  kebab=$(printf '%s' "$kebab" | cut -c1-60 | sed -e 's/-[a-z0-9]*$//' -e 's/-$//')
fi

# 6-char content hash: first 6 hex chars of sha256(stdin).
if command -v shasum >/dev/null 2>&1; then
  hash=$(shasum -a 256 | cut -c1-6)
else
  hash=$(sha256sum | cut -c1-6)
fi

printf '%s-%s-%s\n' "$(date +%Y-%m-%d)" "$kebab" "$hash"
