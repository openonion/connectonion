---
title: The backup you were told to destroy
date: 2026-09-15
---

# The backup you were told to destroy

`co auth lark` could not create an application on a data-residency tenant, and
`co env set LARK_APP_SECRET` refused the hand-typed value, pointing back at
`co auth lark`. Two correct rules, pointing at each other.

Opening the door was easy — `--from-console`, one flag, one honest sentence about
why the usual refusal exists. The harder question came right after it: if people
are now going to paste an app secret into a file, should that file really be
plain text?

## What lark-cli does, and why we can't copy it

The reference implementation is `lark-cli`. It generates an AES-256 master key,
puts it in the macOS keychain, and writes AES-GCM ciphertext next to it. Sound
design. It has to invent a master key because it has nothing else to start from.

We can't copy it, because a keychain is a thing a *logged-in human* has. An agent
under launchd, over ssh, on a `co deploy --to` box has no login keychain at all.
This is the same wall the browser licence gate hit over SSH last month. A store
that only opens when someone is sitting at the machine is not a store an agent
can use.

But we do have something lark-cli doesn't: `derive.py`, which turns a secret into
a whole tree of keys. So the encryption key doesn't have to be *kept* anywhere.
It can be derived at a path, on demand, and thrown away. There is no master key
to store, so there is nothing to put in a keychain, and `slip13_path` already
takes a rotation index — so "rotate" is "derive at index+1 and re-encrypt", with
no key-wrapping scheme to invent.

That much was right. The root was wrong.

## The root was wrong

I rooted the tree at `.co/keys/recovery.txt` — the twelve words. It gave the
store a property a keychain can never have: carry the ciphertext to a new
machine, type the words, and it opens.

Aaron stopped it with one question: why go through the mnemonic?

Because `recovery.txt` is **optional**. `co keys` prints "missing" for it without
complaint. It is a disaster-recovery backup, and the correct thing to do with a
recovery phrase is write the words on paper and delete the file. I had just made
doing the right thing with your backup silently destroy every stored secret —
and made a routine `co env get` open the most sensitive file on the machine, on
every single lookup.

The fix is one level down. `.co/keys/agent.key` is 32 bytes, which is exactly
what a SLIP-0010 master key takes, and `address.load()` already opens it on every
command. Root the subtree there instead:

```
.co/keys/agent.key ──SLIP-0013──▶ m/13'/…'  (secret://lark_app_secret, index 0)
```

## Nothing was given up

The reflex is to assume that dropping the phrase drops recoverability. It
doesn't, and the reason is worth stating plainly: `agent.key` is *itself*
`derive_path(bip39_seed, slip13_path(ACCOUNT_URI))`. The twelve words derive the
agent key, and the agent key derives the secret keys. The chain is one link
longer and the endpoint is identical:

```
twelve words ──BIP-39──▶ seed ──SLIP-0013──▶ agent.key ──SLIP-0013──▶ secret key
```

So the store still opens on a new machine from the words alone. It just no
longer *reads* them to do ordinary work. The test that says so deletes
`recovery.txt` before decrypting, and it fails on the previous implementation —
which is the only reason it means anything.

## What it does not claim

`agent.key` is a `0600` file sitting next to the ciphertext. Anyone who can read
it can decrypt everything in the store, and the module says so in its own
docstring rather than implying otherwise. But that person can already sign as the
agent — the secret store is not what they would be attacking.

What it buys is narrower and real: an app secret is no longer sitting in
plaintext in a file people `cat` in a screen share, paste into an issue, and read
aloud on a call.

## The shape of the mistake

Both versions worked. Both had sixteen passing tests. The first one would have
kept working for months, right up until someone did exactly what our own
documentation tells them to do with their recovery phrase — and then every stored
secret on that machine would have been gone, with no error that pointed anywhere
near the cause.

The tell wasn't in the crypto. It was that I had taken a file the product
describes as optional and quietly made it required, without noticing that I'd
changed what it was.
