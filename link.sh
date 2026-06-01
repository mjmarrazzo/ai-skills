#!/usr/bin/env bash
# Symlink every skill under plugins/<group>/skills/<name> into ~/.claude/skills/<name>
# for local development. (For normal use, install via the marketplace instead:
#   /plugin marketplace add mjmarrazzo/ai-skills )
set -euo pipefail

dest="$HOME/.claude/skills"
mkdir -p "$dest"

# Prune broken symlinks in the dest that point back into this repo.
for link in "$dest"/*; do
  [ -L "$link" ] || continue
  target="$(readlink "$link")"
  case "$target" in
    "$PWD"/*) [ -e "$link" ] || { rm "$link" && echo "pruned stale $link"; } ;;
  esac
done

for s in ./plugins/*/skills/*/; do
  name="$(basename "$s")"
  target="$dest/$name"
  if [ -d "$target" ] && [ ! -L "$target" ]; then
    echo "skip $name — exists as real dir at $target"
  else
    ln -sfn "$PWD/${s%/}" "$target" && echo "linked $name"
  fi
done
