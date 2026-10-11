# co approvals

Your agent mostly acts rather than asks: a contact's request is done, not held
for you. The record is how you find out what was done. Design: [#2408](https://github.com/openonion/connectonion/issues/2408).

```bash
co approvals                       # the newest 50 entries, oldest first
co approvals --who 0x3f5a...c9e1   # one requester
co approvals --who feishu:ou_123   # a chat sender
co approvals --class money         # one special class
co approvals -n 200 --json         # more, as JSON
```

## What is recorded

One JSON line per event in the agent's `.co/approvals.jsonl` (its `state_dir`
if it has one). `co ai` keeps its record in `~/.co`, beside its identity;
`co approvals` reads the project's record, or `~/.co`'s when the project has
none, and prints which file it read.

| `path` | When |
|---|---|
| `turn` | every tool call in an agent turn, done or declined, including calls made inside Codex or Claude Code |
| `exec` | every network EXEC, allowed or refused |
| `browser` | every Remote Browser request |
| `trust` | every change to contacts, the whitelist, the blocklist or admins, with the block reason. `subject` is whom it is about; `--who` matches it too |

Each line has `ts`, `who` (`key:0x…`, `email:…`, `chat:<provider>:<sender>`, or
`local`), `tool`, `args` (cut to 300 characters), `decision` (`done` or
`declined`), `outcome`, `reason` and, for turns, `session` and `via`. Tokens
(`sk-…`, `ghp_…`, `Bearer …`) and values assigned to names containing KEY,
TOKEN, SECRET or PASSWORD are replaced with `***` before the line is written.

## The three things that need the owner

Code, not the model, puts a call in one of these classes, from the tool and
its arguments, and every such call is recorded with its class. Where it stops:

- **Someone other than the owner asked, and nobody is connected to ask**: a
  chat message, an inbox turn, a contact's unattended run. The call is
  declined with a pointer to the agent's own terminal, in every mode, Full
  access included, with or without the approval plugin.
- **Network EXEC** from anyone but an admin, whatever `host.yaml` whitelists:
  the shipped `Bash(co *)` no longer lets a contact run `co env get`.

The owner is a local caller (the agent's terminal, its schedules) or an admin.
With a client connected, as when you use `co ai` in the browser, the approval
flow asks that person as it always did. Asking the owner by email instead is
next (#2408).

| `class` | Examples |
|---|---|
| `credentials` | `co keys`, `co env get`, reading `keys.env` or `.co/keys/` |
| `authority` | `co trust add`, writing `host.yaml`, `admins.txt` or a trust list |
| `money` | `co transfer`, `co server new` |
| `irreversible` | `rm`, `git push --force`, `git reset --hard`, `git clean`. For now every `rm` counts, even of a file git could restore |
| `as_owner` | `co gmail send`, `co outlook reply`, the Gmail/Outlook tools' `send` and `reply`, calendar invites |

Not in any class: mail from the agent's **own** mailbox (`co email send`,
`send_email`), `co server list`, an ordinary `git push`, tests, reads. Those
are done and recorded.

## What it is not

- **Not editable by the agent.** `approvals.jsonl` is a control file, like
  `host.yaml`: the write and edit tools refuse it in every mode. A shell command
  that reaches it indirectly (`cd .co && …`) is not caught; the operator's own
  `Bash(...)` grants bound that.
- **Not a store of results.** Results stay in the session; the record says what
  ran, for whom, and whether it was allowed.
- **Never rewritten.** Lines are only appended. An agent with no writable
  `.co/`, or created with `log=False`, keeps no record.
- **Not complete for delegated coding agents.** A Codex run is recorded only
  when the agent has a client connected, and the calls of a sub-agent are
  recorded as `local`.
