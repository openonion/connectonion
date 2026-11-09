#!/usr/bin/env python3
"""`claude -p --output-format stream-json` as the real one prints, replayed from a recorded run.

claude_stream_accept_edits.jsonl is a real Claude Code 2.1.319 run ("add one
line to README.md"), with paths made fictional. Claude Code's child gets only an
allow-listed environment, so this fake takes its instructions from argv.

In `--permission-mode manual` (what co's "default" becomes) nobody can approve
an edit in a headless run: it replays claude_stream_default_denied.jsonl, the
real run whose Bash and Edit were refused, and changes nothing. In any other
mode it writes `claude-was-here.md` in its cwd, and when the prompt names a
`Deliverable: <path>` it writes a result there plus argv.json and cwd.txt beside it.
"""
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
args = sys.argv[1:]
prompt = args[args.index('--') + 1]
if args[args.index('--permission-mode') + 1] == 'manual':
    sys.stdout.write((HERE / 'claude_stream_default_denied.jsonl').read_text())
    sys.exit(0)
pathlib.Path('claude-was-here.md').write_text('Pilot notes\n')
found = re.search(r'Deliverable: (\S+)', prompt)
if found:
    deliverable = pathlib.Path(found.group(1))
    (deliverable.parent / 'argv.json').write_text(json.dumps(args))
    (deliverable.parent / 'cwd.txt').write_text(os.getcwd())
    deliverable.write_text('# Pilot review\nReady for owner review.\n')
sys.stdout.write((HERE / 'claude_stream_accept_edits.jsonl').read_text())
