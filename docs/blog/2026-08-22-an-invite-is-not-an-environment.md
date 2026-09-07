# An Invite Is Not an Environment

The 1.7 beta Host was running. The browser was open. The release test still
could not begin.

`co ai` already knew how to create a private owner invite and keep it in
`~/.co/keys.env`. That was useful for a person returning to the same machine:
the code survived a restart, and clients that had already received it were not
locked out. It was the wrong lifetime for a clean release run.

An E2E runner wanted a new credential for one Host process. Its choices were to
edit a persistent file, export the credential into an environment inherited by
the coding agent and its tools, or stop and call the missing value an external
authorization blocker. We took the third path during beta acceptance. The
blocked test was telling us something real, but not what we first wrote down.

The fix gives `co ai` two explicit inputs. A person can pass `--invite-code` for
a local run. Automation can use `--invite-code-file`, keeping the value out of
shell history and the process argument list. Both become an in-memory override
on the Host's `TrustAgent`. They do not update `.env`, mutate `os.environ`, or
enter the model and tool subprocess environment.

This work also found an older leak at the boundary. WebSocket onboarding logs
printed both accepted and rejected invite values. A secret that was absent from
the policy file could still end up in CI output. The logs now record the signed
client, outcome, and resulting trust level—the facts an operator needs—without
recording the credential used to prove them.

The installed-wheel smoke checked the whole non-network chain: CLI file input,
runtime trust configuration, OIP discovery, WebSocket onboarding, unchanged
process environment, unchanged `keys.env`, and sanitized output. The focused
regression set passed 154 tests. The managed test sandbox forbade binding a
localhost port, so the final browser leg remains an explicit CI acceptance
step, not an inferred success.

The lesson is about lifetime. An invite can establish a durable relationship
without becoming durable configuration itself. Authentication works better
when the credential lives exactly as long as the workflow that needs it—and no
longer.
