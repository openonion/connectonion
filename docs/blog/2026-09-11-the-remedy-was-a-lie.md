# The remedy was a lie

A refused tool call used to come back as one sentence:

```
command is outside the focused verification and read-only allowlists;
no approval channel is available
```

That names a policy. An agent reading it has exactly one move available —
try again — and trying again cannot work, because the decision is a lookup
against a static list and will come out the same way every time. So the loop
runs until the iteration budget is gone. That is how a scheduled job ended at
28 of 300 iterations with nothing done: not one refusal, but one refusal and
272 retries of it.

The owner's ask was three lines: say why it was refused, say how to get it
approved next time, and tell the agent to think rather than repeat. So a
refusal now carries all three, and the middle one prints the exact permission
line to add and the two places it can go.

Which is where this stops being a formatting change.

## Printing a line means promising it works

The first version suggested, for `cat /etc/shadow`:

```yaml
"Bash(cat *)":
  allowed: true
```

Paste that into `host.yaml` and the command is still refused. A wildcard grant
is honoured only for the effect class its own text classifies to, and `cat`
on its own is an ordinary workspace read, while `cat /etc/shadow` is a read
outside the workspace. Different class, no grant. The suggestion was confident,
specific, well-formatted, and wrong.

The second one was worse, because nothing could have fixed it. For
`echo x > ../outside.txt` it suggested `Bash(echo x > ../outside.txt)` — and
there is no pattern at all that allows that call, because the parser strips
redirects out of the text patterns are matched against. I was inventing syntax
for a capability the permission language does not have.

Think about what a wrong remedy actually does. The operator pastes it. It does
not work. They widen it: `Bash(cat *)` becomes `Bash(*)`. That one works. Now
the agent can run anything, and the audit trail says the operator chose that
deliberately. A refusal that says nothing leaves the policy intact; a refusal
that suggests the wrong fix walks the operator toward disabling it.

## So the remedy checks itself

Before printing the HOW section, the code now runs its own suggestion through
the real grant path — the control-file gate first, then the grant check, in the
order the live call asks them. If the suggestion would not lift the refusal,
the section is replaced with:

```
THERE IS NO GRANT FOR THIS
No permission pattern expresses it, so only a person changing the call or the
file by hand can allow it. Do not go looking for a pattern that works; there
is not one.
```

That last sentence is there because an agent told "no" without being told
"and there is no version of this that works" will spend the rest of the run
looking.

The check found a third case I had not thought about: `write` with a path of
`.co/host.yaml`. The grant path said a `write` grant would allow it, and it
would have — except the control-file gate runs *before* the policy verdict is
read, so the real answer is no. My probe had asked only the half of the
pipeline that grants operate on. Asking in the wrong order is the same bug as
not asking.

## The test that found all of it

```python
@pytest.mark.parametrize(("command", "expected_effect"), REFUSED_CALLS)
def test_the_grant_the_refusal_suggests_actually_allows_the_call(...):
    # 1. the call is refused
    # 2. the refusal names a pattern
    # 3. with exactly that pattern in place, the identical call runs
```

Sixteen refused calls, each one asserting that the advice the product gives is
true. Neither lie survived it, and neither would have been caught by testing
the message — the message was well-formed in both cases. The only thing that
distinguishes good advice from bad advice is following it and seeing what
happens.

That is the same shape as everything else in this line of work. The policy had
sixty green tests while production was failing, because the tests asked whether
the code matched the specification and nobody asked whether the specification
matched the job. Here the code produced a syntactically perfect grant line and
nobody asked whether the line worked. Both times the fix was to run the thing
and look.

## What it did on a real run

Asked to read a file outside the workspace, unattended:

```
$ co ai "Read /etc/hosts and tell me the first line."
… <system-reminder> … Do not retry this call …
I cannot read `/etc/hosts`: access to files outside the project workspace is
blocked by the environment's security policy.
```

One attempt. No retry. A sentence the operator can act on.

The per-class advice is the half I expect to earn its keep: a credential
refusal now says *you almost never need a secret's contents — say what you were
going to use it for*, and a `sed`/`awk` refusal says *`head`, `cut` and
`read_file(limit=, offset=)` do the reading job without a grant*. A refusal
that names an alternative is a refusal the agent can route around correctly,
which is the difference between a policy that shapes behaviour and one that
just stops it.
