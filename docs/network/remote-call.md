# Direct Tool Execution — `remote.call`

> Run one of a remote agent's tools directly, bypassing the LLM. Input in, raw
> output out — like a remote command line. Gated by the `.co/host.yaml`
> permission whitelist.

---

## Why

`connect().input(prompt)` sends a task to the agent's **LLM**: it reasons, picks
tools, and comes back when the whole task is done. That's what you want for
"check my notifications and reply to anything urgent."

Sometimes you don't want the agent to *think* — you already know the exact tool
and arguments, and you just want the result:

- Take a screenshot of the remote browser *right now*
- Run `co status` on the box and read the output
- Click a selector, then grab the page

`remote.call(tool, **args)` is that fast path. No reasoning, no session, no
conversation history — the named tool runs and its raw result comes straight
back. The result can be text **or** a base64 image (a screenshot), so it behaves
like a terminal that can also draw.

| | `remote.input(prompt)` | `remote.call(tool, **args)` |
|---|---|---|
| Who decides what runs | the LLM | you |
| Latency | a full reasoning loop | one tool call |
| Keeps history | yes (session) | no (stateless) |
| Good for | open-ended tasks | known, scripted steps |

---

## Quick start

```python
from connectonion import connect

remote = connect("0x3d4017c3...")           # add keys=... for strict-trust agents

# Text out
print(remote.call("bash", command="co status").text)

# Image out — a screenshot tool returns base64; .images extracts it
shot = remote.call("take_screenshot")
if shot.images:
    import base64
    png = base64.b64decode(shot.images[0].split(",", 1)[1])
    open("page.png", "wb").write(png)

# Drive a browser step by step
remote.call("go_to", url="https://example.com")
remote.call("click", selector="text=Sign in")
```

`remote.call` runs over the **same authenticated WebSocket** as `input()`, so
relay discovery, Ed25519 auth, and trust all still apply. It's a fast path, not
a back door.

---

## The result: `ExecResult`

```python
result = remote.call("bash", command="uptime")

result.text          # str  — raw tool output (may contain base64 image data)
result.status        # "success" | "error"
result.ok            # bool — True when status == "success"
result.error         # str | None — message when status == "error"
result.duration_ms   # int  — how long the tool ran on the server
result.images        # list[str] — base64 data URLs pulled out of .text
```

`ExecResult` never raises for a *tool* failure — a crash inside the tool comes
back as `status="error"` with the message in `.error`, exactly like the LLM loop
reports tool errors for retry. (Transport problems like a timeout also return an
error result rather than raising.)

```python
r = remote.call("bash", command="cat missing.txt")
if not r.ok:
    print("failed:", r.error)
```

---

## The whitelist gates every call

What may run via `remote.call` is **the same permission whitelist the LLM
approval flow uses** — the `permissions:` block in `.co/host.yaml`. There is one
list to maintain, and "safe to run without a human in the loop" means the same
thing whether the LLM or a remote client initiates the tool.

Before running, the server checks the request against the whitelist. Not on the
list → refused:

```python
remote.call("bash", command="rm -rf /")
# ExecResult(status="error", error="blocked: command not in the permission whitelist. ...")
```

Nothing to "enable" — it's on by default and bounded entirely by the whitelist.
An empty whitelist means nothing runs directly.

### How patterns match

Entries are keyed either by **tool name** or by a **`Bash(...)` command pattern**:

```yaml
permissions:
  # Simple tool name — matches any call to that tool
  "take_screenshot":
    allowed: true
    source: safe
    reason: read-only page capture

  # Exact command
  "Bash(git status)":
    allowed: true
    source: config
    reason: safe git read

  # Wildcard — trailing " *" means "this command with any args"
  "Bash(ls *)":
    allowed: true
    source: config
    reason: list directory contents
```

- `"Bash(ls *)"` matches `ls`, `ls -la`, `ls /tmp` — but not `lsof`.
- `"Bash(git status)"` matches only the exact command.
- Command **chains are checked per-subcommand**: `git status && ls -la` runs only
  if *both* `git status` and `ls -la` are whitelisted. Sneaking a command in via
  `&&`, `|`, or `;` doesn't work — `cat foo && rm bar` is rejected because `rm`
  isn't allowed.

> **Wildcards run the program, not a subcommand.** `"Bash(python *)"` would allow
> `python evil.py` — running arbitrary code. That's why version checks are pinned
> exact (`"Bash(python --version)"`), never `python *`. Keep wildcards to tools
> that are safe with *any* arguments (`ls`, `cat`, `git log`).

---

## Allowed by default

A fresh `host()` ships a whitelist of safe, read-only commands and the browser
navigation/observation tools. Highlights:

| Group | Entries |
|---|---|
| Read-only agent tools | `read`, `read_file`, `glob`, `grep`, `search`, `list_files`, `ask_user` |
| Browser (navigation/observe) | `go_to`, `take_screenshot`, `click`, `scroll`, `type_text_by_selector`, `extract_items_by_selector`, `wait_for_element` |
| ConnectOnion CLI | `Bash(co *)` |
| File viewing | `cat *`, `head *`, `tail *`, `nl *`, `wc *`, `file *`, `stat *`, `diff *`, `tree *`, `du *` |
| Path helpers | `basename *`, `dirname *`, `realpath *`, `readlink *` |
| Text (read-only) | `echo *`, `sort *`, `uniq *`, `cut *`, `tr *`, `column *`, `jq *` |
| Checksums | `md5sum *`, `sha256sum *`, `shasum *`, `cksum *` |
| System info | `pwd`, `ls *`, `uname *`, `df *`, `free *`, `ps *`, `top *`, `uptime *`, `whoami`, `date *`, `which *`, `env *` |
| Identity | `id`, `groups *`, `printenv *`, `locale`, `arch`, `nproc *`, `lsb_release *` |
| Tool versions (exact) | `python --version`, `python3 --version`, `pip --version`, `node -v`, `npm --version`, `git --version`, `go version` |
| Package inspection | `pip list *`, `pip freeze`, `pip show *`, `npm list *`, `npm ls *` |
| Git (read-only) | `git status`, `git diff *`, `git log *`, `git branch *`, `git show *`, `git remote *`, `git blame *`, `git ls-files *`, `git config --get *` |
| Testing | `pytest *`, `npm test` |

Deliberately **not** included: anything with side effects (`sed -i`,
`find -exec`/`-delete`, `tee`, `xargs`, `curl … | sh`) or interpreter execution
(bare `python`, `node`). Add those yourself only if you trust the caller.

---

## Adding your own commands

Edit `.co/host.yaml` — no code change, no restart of anything but the host:

```yaml
permissions:
  "Bash(kubectl get *)":
    allowed: true
    source: config
    reason: read k8s resources

  "Bash(docker ps *)":
    allowed: true
    source: config
    reason: list containers

  # A whole tool, any args
  "extract_data":
    allowed: true
    source: config
    reason: safe read-only extraction
```

The project `.co/host.yaml` merges on top of the shipped defaults, so you only
list what you add. Project entries override defaults, but never a permission a
user granted interactively.

---

## Async

Inside an event loop, use the async form:

```python
result = await remote.call_async("take_screenshot", timeout=30)
```

`remote.call(...)` is the sync wrapper; calling it from within a running event
loop raises — use `call_async` there.

---

## Onboarding

If the agent's trust level requires onboarding (invite code or payment), a raw
`call()` can't complete the interactive handshake. Run `input()` once to onboard,
then `call()` works on the same identity:

```python
remote.call("take_screenshot")
# ExecResult(status="error", error="agent requires onboarding — run input() once to onboard, then call() works")
```

---

## On the wire

Direct execution adds two WebSocket frames (after the usual `CONNECT` →
`CONNECTED` auth handshake):

**Client → agent**

```json
{ "type": "EXEC", "exec_id": "uuid", "tool": "bash", "args": { "command": "co status" } }
```

**Agent → client**

```json
{
  "type": "EXEC_RESULT",
  "exec_id": "uuid",
  "tool": "bash",
  "status": "success",
  "result": "…raw output…",
  "duration_ms": 42
}
```

Each `EXEC` runs as its own server-side task, so a slow tool (a long shell
command) never blocks the connection's read loop or other in-flight `EXEC`s.
`exec_id` correlates the reply, so you can pipeline several calls on one socket.

---

## Related

- [connect.md](connect.md) — `connect()` and `input()` for LLM-driven tasks
- [host.md](host.md) — hosting an agent with `host()`
- [host-config.md](host-config.md) — the full `.co/host.yaml` reference
- [websocket-protocol.md](websocket-protocol.md) — CONNECT/INPUT/OUTPUT frames
