#!/usr/bin/env python3
"""`claude -p --output-format stream-json` as the real one prints, replayed from a recorded run.

claude_stream_accept_edits.jsonl is a real Claude Code 2.1.319 run ("add one
line to README.md"), with paths made fictional. Claude Code's child gets only an
allow-listed environment, so this fake takes its instructions from argv.

In `--permission-mode manual` (what co's "default" becomes) nobody can approve
an edit in a headless run: it replays claude_stream_default_denied.jsonl, the
real run whose Bash and Edit were refused, and changes nothing. In any other
mode it writes `claude-was-here.md` in its cwd (after the SessionStart Hook, when
`--settings` passes one), and when the prompt names a
`Deliverable: <path>` it writes a result there plus argv.json and cwd.txt beside it.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
args = sys.argv[1:]
RECORDED_SESSION = 'bf1b715f-3272-4573-b78d-359571db650a'
resumed = args[args.index('--resume') + 1] if '--resume' in args else None
if '--settings' in args:
    # `co claude run` passes scoped Hooks; Claude Code fires SessionStart first.
    settings = json.loads(pathlib.Path(args[args.index('--settings') + 1]).read_text())
    hook = settings['hooks']['SessionStart'][0]['hooks'][0]
    # A resumed run starts the session it was given, as the real `claude --resume <id>` does.
    subprocess.run([hook['command'], *hook['args']], text=True, check=True, input=json.dumps({
        'hook_event_name': 'SessionStart', 'session_id': resumed or RECORDED_SESSION,
        'transcript_path': str(pathlib.Path.cwd() / 'transcript.jsonl'), 'cwd': os.getcwd(),
        'source': 'resume' if resumed else 'startup'}))
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
sys.stdout.write((HERE / 'claude_stream_accept_edits.jsonl').read_text().replace(RECORDED_SESSION, resumed or RECORDED_SESSION))
