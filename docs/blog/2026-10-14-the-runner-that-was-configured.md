# The runner that was configured

*2026-10-14*

A fresh `co rem init` on a machine without Codex stopped after the map and said
the page was not written because "Codex is not installed". The person reading
that line had expected Claude Code — the docs talk about it as the fallback —
and had no idea which runner the notebook had actually saved, or that one
command would switch it.

The problem string already named Codex. What it did not say was the configured
runner and the switch. The skip line now includes both: `configured runner:
codex`, the install fix, and `co rem config set runner claude-code`. The map
still finishes; only the model-spending stages stay off until a runner can run.

