#!/bin/bash
# Symlink all useful_skills into ~/.claude/skills/ so they work in Claude Code.
# Run this once after adding new skills, or re-run to pick up additions.

SKILLS_DIR="$(cd "$(dirname "$0")" && pwd)"

for skill_dir in "$SKILLS_DIR"/*/; do
  skill_name=$(basename "$skill_dir")
  target="$HOME/.claude/skills/$skill_name"

  if [ -L "$target" ]; then
    echo "already linked: $skill_name"
  elif [ -e "$target" ]; then
    echo "exists (not a symlink): $skill_name — skipping"
  else
    ln -s "$skill_dir" "$target"
    echo "linked: $skill_name"
  fi
done
