# co approvals

Your agent mostly acts rather than asks: a contact's request is done, not held
for you. The record is how you find out what was done. Design: [#2408](https://github.com/openonion/connectonion/issues/2408).

```bash
co approvals                       # the newest 50 entries, oldest first
co approvals --who 0x3f5a...c9e1   # one requester
co approvals --who feishu:ou_123   # a chat sender
co approvals --class money         # one special class (once classes are set)
co approvals -n 200 --json         # more, as JSON
```

## What is recorded

One JSON line per event in the agent's `.co/approvals.jsonl`:

| `path` | When |
|---|---|
| `turn` | every tool call in an agent turn, done or declined, including calls made inside Codex or Claude Code |
| `exec` | every network EXEC, allowed or refused |
| `browser` | every Remote Browser request |
| `trust` | every change to contacts, the whitelist, the blocklist or admins, with the block reason |

Each line has `ts`, `who` (`key:0x…`, `email:…`, `chat:<provider>:<sender>`, or
`local`), `tool`, `args` (cut to 300 characters), `decision` (`done` or
`declined`), `outcome`, `reason` and, for turns, `session` and `via`.

## What it is not

- **Not editable by the agent.** `approvals.jsonl` is a control file, like
  `host.yaml`: the write and edit tools refuse it in every mode. A shell command
  that reaches it indirectly (`cd .co && …`) is not caught; the operator's own
  `Bash(...)` grants bound that.
- **Not a store of results.** Results stay in the session; the record says what
  ran, for whom, and whether it was allowed.
- **Never rewritten.** Lines are only appended. An agent with no `.co/` keeps no
  record.
