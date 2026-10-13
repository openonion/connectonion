#!/bin/sh
# Install ConnectOnion and set it up, in one line:
#
#   curl -fsSL https://raw.githubusercontent.com/openonion/connectonion/main/install.sh | sh
#
# 1. installs co in its own environment with uv (installing uv first if needed),
#    never into your system Python; uv fetches a Python if you have none
# 2. co init: your agent identity, an OpenOnion key with starter credit, and the
#    co skills and command index for Codex and Claude Code
# A preview instead of the stable release:  ... | CO_VERSION=1.9.2b10 sh
set -eu

spec="connectonion${CO_VERSION:+==$CO_VERSION}"
your_path="$PATH"   # before this script adds to it

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv (https://docs.astral.sh/uv), which keeps co out of your system Python..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
fi

echo "Installing $spec..."
# A version released minutes ago can be missing from PyPI's index, which uv reads, for a few
# minutes: wait for it rather than fail the handoff that pinned it (#2457).
tries=0 refresh=""
until uv tool install --force --quiet $refresh "$spec"; do
  tries=$((tries + 1)) refresh="--refresh"
  if [ -z "${CO_VERSION:-}" ] || [ "$tries" -ge 10 ]; then exit 1; fi
  echo "$CO_VERSION may have been released minutes ago and not be on PyPI's index yet; trying again in ${CO_INSTALL_WAIT:-30}s ($tries/9)..."
  sleep "${CO_INSTALL_WAIT:-30}"
done
bin="$(uv tool dir --bin)"
uv tool update-shell >/dev/null 2>&1 || true

"$bin/co" init --yes

echo
echo "✓ $("$bin/co" --version) is installed in $bin"
case ":$your_path:" in
  *":$bin:"*) ;;
  *) echo "  Open a new terminal, or run: export PATH=\"$bin:\$PATH\"" ;;
esac
echo
echo "Try:"
echo "  co status           what is set up"
echo "  co auth google      connect Gmail and Google Calendar"
echo "  co auth microsoft   connect Outlook"
echo "  co commands         everything else; add --help to any command"
if grep -qs "co:begin" "$HOME/.codex/AGENTS.md" "$HOME/.claude/CLAUDE.md"; then
  echo
  echo "Codex and Claude Code know about co now: ask them to use it."
fi
