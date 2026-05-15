for s in ./skills/*/; do
  name=$(basename "$s")
  target="$HOME/.claude/skills/$name"
  if [ -d "$target" ] && [ ! -L "$target" ]; then
    echo "skip $name — exists as real dir at $target"
  else
    ln -sfn "$PWD/$s" "$target" && echo "linked $name"
  fi
done