---
description: The approval policy refused a LinkedIn comment as credential access because the sentence said "keys". The check now looks at what a command opens, not the words it carries.
tags: [Approval, Security, Agent]
---

# Idempotency keys are not keys

At 18:00 on 2026-09-11 our LinkedIn round ran unattended and reported
success. Seven comments were planned. Three were missing, and nobody noticed
until someone read the log line by line. One of them was this:

```
co browser -t lidaily-1800 type_text_by_selector div.tiptap.ProseMirror \
  Idempotency keys catch replays, but two-phase commit with strict rollback hooks ...

-> Tool 'bash' denied by connectonion.auto: credential access is never auto-approved
```

The command typed a sentence into a web page and opened no files. The
policy denied it because the sentence contained the word `keys`.

## How a word became a credential

The credential check had two parts. One looked for `.env`, `secret` or
`credential` anywhere in any word of the command. The other asked whether an
argument named key material, and the list of key-material names included the
directory `keys`, because `.co/keys/` holds the agent's own signing key. Both
parts read every word in the same way, whether the word was a path that
`cat` would open or part of a sentence on its way to a text box.

Quoting the sentence did not help. `"keys matters"` got through, because
the key-material rule compared whole words. `"secret matters"` was still
denied, because the substring rule matched inside it. So people in the domain
this tool works in, writing about "primary keys", "the secret is" or
"rotating credentials", were refused for ordinary vocabulary.

The two kinds of mistake are also noticed very differently. If the check
misses a real credential read, a secret leaks and somebody sees it. If it
blocks a harmless sentence, the agent gets a deterministic "do not retry",
drops the comment and carries on, and the report just has an empty slot.

## What it checks now

The question is what the command opens, not which letters it contains. A
word counts in three cases:

- it is shaped like a path (`a/b`, `~/x`, `.env`, `secrets.yaml`) and names
  key material, a `.env` file, or something called secret or credential;
- it is a bare name passed to a command that opens its arguments, like
  `cat credentials` inside `~/.aws` or `ls keys` inside `.co`;
- it sits in subcommand position as a secret store: `kubectl get secret`,
  `gh secret list`, `aws secretsmanager`.

A sentence has spaces, so it is never path-shaped. A word typed by
`co browser` or carried by `git commit -m` is not an argument of `cat`. Both
are data again.

The tests cover both sides of the change. Five ordinary words, bare and
quoted, are typed through `co browser` and must not be classed as credential
access. Thirteen real reads, from `cat .env` to `kubectl get secret` to
`security find-generic-password`, must still be denied as credentials. Before
the patch, all thirteen reads were already denied and twelve of the data cases
were wrongly denied too. After it, the reads are still denied and the data
gets through.
