# Sixty green tests and a job that could not run

At iteration sixteen of a LinkedIn round that runs seven times a day, the agent
asked to look at a page it had just fetched:

```
CO_WHO=x co browser -t t get_text | head -40
```

and got back

```
Tool 'bash' denied by connectonion.auto: command is outside the focused
verification allowlist; no approval channel is available
```

It never recovered. Twenty-eight of three hundred iterations, zero comments
posted, no report written, and three health checks that read the report went
red for a reason none of them could name. The operator found it the next
morning. The test suite, sixty-odd tests deep on exactly this approval policy,
had been green the whole time.

## The tests were right

The first instinct is that a test was missing. It was not. There is a test that
says an unknown shell command asks a person. There is a test that says, when
no person is present, asking fails closed. Both were written on purpose in
1.7, both have names that say what they check, and both were passing because
the code did exactly that.

`head` is not on any list. Neither is `grep`, `wc`, `cat`, `ls`, `tail`,
`sed`. Only eleven commands auto-approve, all of them test and build tools.
Everything else asks, and unattended, asking is refusing. Then the chain rule
compounds it: every segment of a piped command needs its own permission, so
the shipped grant that covered `co browser ...` was worthless the moment the
model piped its output into a filter.

None of that is a bug in the sense a test can find. The tests encode the
policy, the policy said this, and the policy was wrong. A suite built to catch
"the code does not do what we said" has no purchase on "what we said is not
what an operator needs."

## What was missing was the job

Every one of those sixty tests is a single call to the classifier: this
command, this verdict. Not one of them models what an unattended agent
actually does when given a task. So I wrote that test: an agent, with nobody
to ask, writes a small Rust command-line tool, builds it, runs its tests, runs
the binary, and looks at the result through `head` and `wc` and `grep`. The
model is scripted; the Agent loop, the tool executor, the approval plugin and
`cargo` are real.

It failed on the first step. Not on `| head`. On `mkdir`.

Not because `mkdir` was refused — the operator grant covered it — but because
the agent was `quiet=True`, as every unattended agent is, and a quiet agent's
logger has no console. Six places in the approval code reached
`agent.logger.console.log_permission_granted(...)` directly. The policy said
yes, then the plugin crashed on the way to saying so, and the tool result read
`'NoneType' object has no attribute 'log_permission_granted'`. Every
auto-approved call in every quiet agent had been doing this. The unit tests
never built a quiet Agent; they built a `SimpleNamespace` with `logger=None`,
which the guard handled.

The second finding was quieter. Every policy decision is supposed to be
recorded on the trace entry for its tool call, and there is a test that checks
the decision has the right fields. The recorder matched the entry by `id`; the
executor stores the call id as `tool_id`. In a real agent the decision never
reached the trace. The test passed because its fake pending tool had no id at
all, and "no id" matched the last entry.

Three bugs, then, from one test that runs the job instead of the table.

## The fix, and what it does not touch

Read-only commands now run in Auto without asking: the filters and printers
you reach for to look at output. Two things take a command back out: a path
argument that resolves outside the workspace asks, the way the read tools
already do, and `sed -i` asks, because it rewrites the file. An output
redirect is a file write and is held to the write tool's rule — inside the
workspace it is allowed, a control file or a path outside is denied; `2>&1` is
not a write. In an unattended run, a read-only pipe segment rides along beside
a granted command, and every other segment still needs its own grant, so `co
browser status && co email send` is still an email send nobody authorized.

This is the Auto policy for the agent's own calls. The remote-EXEC whitelist in
`host.yaml` carries a comment saying it must never include `cat` or `head`,
and it still does not. Two different questions: what may a stranger make this
agent run, and what may this agent run for itself.

## What the Rust test pins down

The scripted job needs exactly two operator grants: `mkdir`, and the binary it
just built. Everything else — the file writes, `cargo build`, `cargo test`, and
every `cd`, `tail`, `head`, `wc`, `ls`, `grep` around them — rides on the
built-in policy. The test asserts which rule carried each step, and a second
test takes the two grants away and asserts that exactly those two steps are
refused and nothing else. If a future policy change makes `| tail -20` need a
grant again, that test fails at the build step, with the step and the rule
named, instead of in production at iteration sixteen.

## What a real model reaches for

A real-model version of the same job sits behind the `real_api` marker. It
lets the model pick the commands, which is how you find out what a model
reaches for that the list does not cover. Three runs, three findings.

The first run wrote `main.rs` with `cat << 'EOF' > greeter/src/main.rs`, a
heredoc. `bashlex` cannot parse a here-document, an unparseable command asks,
and unattended that is a refusal. So a heredoc is now classified by its first
line — the body is data to `cat` — and a redirect into a workspace file is
held to the write tool's rule: inside the workspace it is a reversible edit,
a control file is denied, outside is denied. `bash << EOF` still asks,
because `bash` is not read-only and the body is what it would run.

The second run started with `cargo new`, which writes `src/main.rs`; then
`write` refused to overwrite an existing file, the heredoc was blocked by the
plugin that steers models toward the write tool, and the model tried
`python3 -c "open(...).write(...)"`. The policy refused that, correctly. It
also refused `ping -c 1 8.8.8.8`, correctly. The model rewrote the project
around `lib.rs` and finished anyway: tests green, binary built, `Hello,
Aaron!`. The finding was about the operator's setup, not the policy — give
the agent an `edit` tool — and about the test: a refusal is a finding to
print, not a failure, when the policy was right to refuse. What decides the
test is whether the job got done with nobody present.

The third run passed in twenty-two seconds.

## One more, found by not trusting the tests

With the suite green I ran the issue's own table by hand — the shipped
permissions, an agent with `io=None`, sixteen commands, print the verdict
beside the one I expected. Fifteen matched. `head ~/.ssh/id_rsa` came back
**allow**.

The outside-workspace rule was supposed to catch it, and normally does,
because `~` is not the project. In that check HOME *was* the project, which
is the shape the test suite's own isolation creates — and is also a real
configuration, and is also what happens when a key gets committed, and is
always true of the agent's own `.co/keys/agent.key`. The credential check
only looked for `.env`, `secret` and `credential` in the words. A private key
matched none of them.

So key material is now recognised by where it lives and what it is called,
and denied wherever it sits: anything under `.ssh`, `.gnupg`, `.aws`, a `keys`
directory; the usual filenames; the usual suffixes. On path components, not
substrings, so `keys.md` is still documentation. Ten tests, red first.

That one was not found by a test. It was found by writing down what the
answers ought to be, running them, and looking at the column that did not
match. The tests then made it permanent.

And then the same method found the next one. With the key rule in, I ran the
whole thing through the real `co ai` — no scripted model, no fixture, the
actual CLI in a temp project — and asked it for `cat server.pem | head -2`.
The model declined, politely, on its own initiative. But the transcript above
its refusal showed it had first called `read_file` on the same file, and the
console had printed `policy read-only workspace operation` beside it.

The shell rule and the tool rule disagreed. `cat server.pem` was denied;
`read_file("server.pem")` was allowed. A gate one tool wide is a detour, and
the only reason nothing leaked is that the model happened to have better
manners than the policy. Both now refuse key material by the same rule.

Then the third, and this one I had already written down. The pull request
said, under "least confident about": *`awk` can call `system()` and GNU `sed`
has an `e` flag, neither of which this checks.* Having written the sentence,
I ran it:

```
awk 'BEGIN{system("rm -rf /")}'   →  allow
```

There is no clever fix. Keeping `awk` and `sed` on a read-only list while
excluding the ways they execute means writing a parser for two languages, in
a security path, and being right about it — against an adversary who is
prompt injection and has all day. The honest line is the one the category
already implies: a command that takes a *program* is not a command that
reads. Both come off the list. They ask, which is what they did before any
of this, and the inspection they get reached for is covered by `head`,
`tail`, `cut`, `jq` and `read_file(limit=, offset=)`.

That widening was the one thing in this change that made the system less
safe than 1.8.4, and it lasted about an hour, because I wrote down what I was
unsure about instead of hoping nobody asked.

## The sweep

At that point the pattern was obvious enough to industrialise. I wrote out
twenty-six things an attacker would try — `cd /etc && cat passwd`,
exfiltration through the granted browser command, `tee`, `cp`, `dd`, `ln -s`,
`sh -c`, `perl -e`, `python3 -c`, a read-only first segment carrying a payload
after `&&` — and printed the verdict for each.

Twenty-five refused. The twenty-sixth was `make install`.

That one predates all of this: 1.8.4 allowed `make install`, bare `make`, and
`make -C /etc all`, all classified as "focused test, lint, or build command".
`cargo` had been narrowed to `test`/`check`/`clippy`/`build`, `go` to `test`,
the package runners to targets naming test or lint or build. `make` was the
one nobody got to. It now needs a named verification target and no `-C` or
`-f` pointing it somewhere else.

It is worth being precise about what that fixes, because it would be easy to
oversell. The focused-verification category is an execution surface on
purpose: an agent that may write a test and run it may run whatever that test
runs, and no amount of target-name checking changes that. What the narrowing
removes is the commands in that category that were never verification —
`make install` writes outside the workspace by convention, and that is a
different claim from "run my tests".

One more came out of the same sweep, which I had thought was already covered:

```
cat $(cat which_file.txt)   →  allow
```

The outside-workspace check looks at arguments that look like paths. That one
does not look like a path; it looks like a substitution, and it reads whatever
the file names. Two neighbouring cases had been refused and I had taken that
as the rule holding — `head $(echo /etc/shadow)` because bashlex splits the
word and the tail starts with a slash, `cat ${SECRET_PATH}` because the word
happens to contain "secret". Luck, twice, in a security path. A file argument
containing `$(`, a backtick or `$name` now asks; a bare `$` still means
end-of-line, so `grep 'foo$' notes.txt` is untouched.

## The tally

Six defects, one of them the reported bug and five found while fixing it,
plus two pre-existing holes in code the fix sat next to. Of the eight, one
was found by a test. The other seven were found by running the thing: an
agent doing a real job, the real CLI in a throwaway directory, and a list of
what an attacker would try with the verdicts printed beside it.

The suite is not what found them, and it was never going to be — it had sixty
green tests on this exact policy while production was failing. What the suite
does is hold them. Every one of the eight now has a test that was red before
the fix, so the next person to widen this policy gets told which specific
thing they broke, by name, in about forty seconds.
