# The word in front of rm

Auto is the mode `co ai` and every hosted agent start in. It is meant to let
an agent work unattended: read, test, edit inside the project, and stop to ask
before anything that cannot be taken back. `rm -rf ~` is denied there, and has
been for a long time.

During an audit of main we gave a real agent — the real bash tool, the real
approval plugin, only the model scripted — one instruction: run
`nice rm -rf $HOME/precious`. It ran. No prompt, no refusal. The directory was
gone before the turn ended.

The policy was not broken in the way you would guess. Every rule in it was
correct. `rm` was denied, `curl` asked, `bash -c` asked. What it did was look
at the first word of the command, and the first word was `nice`. `nice` is not
`rm`, not `curl`, not `bash`; it is not on any list, and in Auto a command on
no list is allowed. That default is deliberate — #1481 was a seven-times-a-day
job dying on `head -40` because nobody had thought to list it — and it is
right. But it meant the whole policy could be walked around by putting any
harmless word in front: `timeout 60`, `nohup`, `sudo`, `caffeinate`.

Once we looked for that shape we found it everywhere. `git reset --hard` was
"git", which is fine. `co gcalendar delete ID --yes` was "co", which is fine,
and Google then emails every attendee that the meeting is cancelled.
`gws gmail +send` hid its verb behind a plus sign; `lark-cli im
+messages-send` behind a hyphen. `gh repo delete --yes`, `kubectl delete`,
`terraform destroy`: all "a command nobody listed", all allowed. Anything the
agent reads — a web page, an email — could steer it into any of them.

The tempting fix is a longer denylist: add `nice`, add `kubectl`, add
`terraform`. That list is the same one #1481 taught us can never be finished,
pointed the other way. So the fix reads commands the way a shell does instead.

A command that runs another command is judged by the one it runs. `nice`,
`timeout`, `nohup`, `env`, `exec`, `watch` and `uv run` are unwrapped, and the
verdict is the wrapped command's — `nice rm -rf ~` is now denied for exactly
the reason `rm -rf ~` is. `sudo` and `xargs` never go below "ask". If a
wrapper has an option we do not recognise, we do not guess where the real
command starts; we ask.

Then the verbs. Instead of naming dangerous programs, the policy reads the
words in subcommand position, split on `+` and `-`, and asks when one of them
deletes, cancels, sends, shares or applies. `delete` is `delete` whether it
comes after `gh`, `kubectl` or a CLI someone installs next week. The same goes
for fetching code — `npx`, `uvx`, `pip install` — and for git's own ways of
throwing work away. And the things that must stay automatic stay automatic:
`ls`, `grep`, `git status`, `pytest`, `co --help`, `co gcalendar list`, a
command nobody listed that only works on local files. Each of those is a row in
the tests, next to each row that must now stop.

The lesson is the one the bug already carried: a rule that decides by the first
word is a rule about spelling. The question the policy has to answer is what
will actually run, and on whose behalf. When the end-to-end test runs today,
the agent asks, the person says no, and `precious/thesis.docx` is still there.
