---
title: "Global unless you name a project"
date: "2026-09-02"
description: "An empty-directory regression revealed that credential setup was also making a project."
---

The release was already building when the requirement became precise:
`co init` should set up global keys. If someone wanted a project in the current
directory, they should have to say `co init ./`.

We had just fixed a related problem: running a command from a subdirectory
could select a different environment from the project's identity. That fix made
runtime loading consistent. It did not answer the earlier question of where
setup was allowed to write.

So the next regression started with an empty temporary directory and a fake
home. It ran `co init --yes`, checked that global credentials existed, and
compared the working directory with its original empty state. The comparison
failed with more than 250 new files. They were project configuration and bundled
documentation, not evidence of a damaged production checkout. But they made the
mismatch concrete: a command intended to set up the machine had also made a
project wherever it happened to run.

Running the same test inside an existing fake project made the distinction
harder to dismiss. Its local environment changed too. The command had no way
to express "configure my account, leave this checkout alone."

An optional directory argument looked like a small fix. It was tempting to
preserve the old behavior whenever a template flag appeared, or infer project
mode from an existing `.co/` folder. Either choice would leave the destination
implicit. We instead made the argument itself choose the scope:

```bash
co init                          # global credentials
co init ./                       # this project's configuration
co init ./ --template co-ai       # configuration and template code
```

That costs existing scaffolding scripts one extra argument. Project-only
options without a path now fail before writing files, with an example showing
what to change. `co create` still creates a new project directory.

There was a second trap inside the smaller global path. The old initializer
looked for provider keys in the process environment. Package startup may have
put them there by loading the current project's `.env`. Reusing that detection
for global setup would silently turn a project credential into a machine-wide
default. The new path saves a provider key only when explicitly supplied with
`--key`; managed authentication uses its existing global destination.

One last offline test removed `keys.env` but kept the signing key. Init
reported a global configuration path, yet the file remained missing: the shared
setup helper returned early because the identity already existed. Recreating
the environment file from that same identity fixed the case without rotating
the keypair or pretending authentication had succeeded.

The original 14 contract tests went from 11 failures to all passing; the
missing-file case became a fifteenth. The installed-wheel checks then ran the
actual executable outside the repository. Plain init left the scratch working
directory empty. Explicit project init still filled its documentation folder.

The boundary is now visible in the command. A working directory tells the
process where it is; it does not, by itself, ask setup to make a project there.

The first release attempt stopped before publication while this distinction
was being clarified. Keeping that tag immutable meant cutting a new candidate,
1.7.3, rather than quietly replacing the code behind 1.7.2. The fixes have also
reached the public 1.8.0b1 preview, so trying the newer line does not restore
the old setup behavior. The [release record](../releases/v1.7.3.md) keeps the
command migration and captured filesystem results beside the version.
