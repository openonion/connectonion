"""Read the coding-agent conversation a handoff is drafted from.

Two on-disk formats, both checked on a real Mac (codex-cli 0.162.1, Claude Code 2.1):

- Codex: ``$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<time>-<thread id>.jsonl``.
  Row 1 is ``session_meta`` with ``payload.cwd``; a turn is a ``response_item``
  whose payload is ``{"type": "message", "role": "user"|"assistant", "content": [...]}``.
  Inside Codex the shell has ``CODEX_THREAD_ID``.
- Claude Code: ``~/.claude/projects/<cwd with every non-alphanumeric as ->/<session>.jsonl``.
  A turn is a row with ``type`` user/assistant and a ``message``; ``isMeta`` and
  ``isSidechain`` rows are the client talking to itself. Inside Claude Code the
  shell has ``CLAUDE_CODE_SESSION_ID``.

Both clients write far more into the user slot than anyone typed (AGENTS.md,
environment context, skill bodies); `INJECTED_BLOCK` from co rem's importer is the
measured filter for that, reused rather than re-learned.

What a handoff keeps, the way a compaction does: every message the person typed,
word for word, and what the AI said, to be summarised. Tool calls, tool output
and reasoning are never read.

Compaction. Both clients keep the full history on disk and only add a marker when
the model's context was compacted, so the whole conversation is read from the
start and the markers are skipped:

- Claude Code writes a ``user`` row with ``isCompactSummary: true`` (the client's
  summary, not the person's words).
- Codex writes a ``compacted`` row whose ``replacement_history`` repeats user
  messages already earlier in the rollout; its summary is encrypted anyway.

A message the person typed while Claude Code was mid-turn is not a ``user`` row: it
is an ``attachment`` row of type ``queued_command`` with ``origin.kind: human``.
"""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from ..rem.source import INJECTED_BLOCK

# Written by the client into the user slot, not typed by the person.
CLIENT_NOTICE = re.compile(r"^\[Request interrupted by user")
# Codex /goal wraps the person's objective in an injected-looking block and repeats it every turn.
# A Codex command's working directory, in a function call's JSON arguments or a custom tool's JS input.
WORKDIR = re.compile(r'\\?"workdir\\?"\s*:\s*\\?"([^"\\]+)')
GOAL = re.compile(r'^\s*<codex_internal_context source="goal">.*?<objective>\s*(.*?)\s*</objective>', re.S)


class SessionNotFound(Exception):
    """No session for this directory; the message says what was looked for."""


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def claude_slug(cwd: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def find_session(cwd: Path, agent: str = None) -> tuple[str, Path]:
    """The current session for `cwd`: (agent, path). `agent` is one of AGENTS, or None for any."""
    from . import other_agents
    cwd = Path(cwd).resolve()
    found = []
    if agent in (None, "codex"):
        found += [("codex", p) for p in _codex_candidates(cwd)]
    if agent in (None, "claude"):
        found += [("claude", p) for p in _claude_candidates(cwd)]
    for other in other_agents.AGENTS:
        if agent in (None, other):
            found += [(other, p) for p in other_agents.candidates(other, cwd)[:1]]
    if not found:
        where = {"codex": f"{codex_home() / 'sessions'} (cwd {cwd})",
                 "claude": str(Path.home() / ".claude" / "projects" / claude_slug(cwd)),
                 **{a: other_agents.NAMES[a] for a in other_agents.AGENTS}}
        looked = "; ".join(where[a] for a in (list(where) if agent is None else [agent]))
        raise SessionNotFound(f"No coding-agent session found for {cwd}. Looked in: {looked}")
    # The live session is the one being written to right now.
    return max(found, key=lambda item: item[1].stat().st_mtime)


def _codex_candidates(cwd: Path) -> list[Path]:
    root = codex_home() / "sessions"
    thread = os.environ.get("CODEX_THREAD_ID")
    if thread:
        named = sorted(root.glob(f"*/*/*/rollout-*-{thread}.jsonl"))
        if named:
            return named[-1:]
    rollouts = sorted(root.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [p for p in rollouts[:200] if _codex_cwd(p) == cwd][:1]


def _codex_cwd(path: Path) -> Path | None:
    with path.open(encoding="utf-8") as f:
        first = json.loads(f.readline() or "{}")
    payload = first.get("payload") or {}
    # co's own Codex runs (co rem, opened handoffs) are not a person's discussion.
    if first.get("type") != "session_meta" or payload.get("originator") in ("connectonion", "co_rem"):
        return None
    return Path(payload.get("cwd", "")).resolve() if payload.get("cwd") else None


def _claude_candidates(cwd: Path) -> list[Path]:
    folder = Path.home() / ".claude" / "projects" / claude_slug(cwd)
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session and (folder / f"{session}.jsonl").exists():
        return [folder / f"{session}.jsonl"]
    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:1]


def read_turns(agent: str, path: Path) -> list[dict]:
    """The whole conversation, oldest first: {role: user|assistant, text, timestamp}."""
    from . import other_agents
    if agent in other_agents.AGENTS:
        return other_agents.turns(agent, path)
    parse = _codex_turn if agent == "codex" else _claude_turn
    turns, goals = [], set()
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                turn = parse(json.loads(line))
                goal = turn.pop("goal", None) if turn else None
                if turn and goal not in goals:
                    turns.append(turn)
                if goal:
                    goals.add(goal)
    return turns


# Claude Code records a message typed while it is busy twice: queued, then delivered.
REPEAT_WITHIN = 600   # seconds


def exchanges(turns: list[dict]) -> list[dict]:
    """Each user message with the AI text that followed it: {at, user, ai, final, steps}. ``ai`` is all of
    it; ``final`` is the reply the person read at the end, after ``steps`` running remarks between tools.
    A turn the person cut short by typing ends on a remark like "Tests first:"; the last one that is not
    a lead-in stands for it then."""
    found = []
    for turn in turns:
        if turn["role"] == "user" and not _repeat(found, turn):
            found.append({"at": turn["timestamp"], "user": turn["text"], "ai": "", "final": "", "steps": 0})
        elif turn["role"] == "assistant" and found:
            last = found[-1]
            last["steps"] += bool(last["ai"])
            last["ai"] = (last["ai"] + "\n\n" + turn["text"]).strip()
            if not last["final"] or not turn["text"].endswith((":", "：")):
                last["final"] = turn["text"]
    return found


def _repeat(found: list[dict], turn: dict) -> bool:
    if not found or found[-1]["user"] != turn["text"] or not (found[-1]["at"] and turn["timestamp"]):
        return False
    return abs((_moment(turn["timestamp"]) - _moment(found[-1]["at"])).total_seconds()) < REPEAT_WITHIN


def find_by_id(ref: str) -> tuple[str, Path]:
    """A session named by path, Codex thread id or Claude Code session id."""
    from . import other_agents
    path = Path(ref).expanduser()
    if path.is_file() and other_agents.kind_of(path):
        return other_agents.kind_of(path), path.resolve()
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            first = json.loads(f.readline() or "{}")
        return ("codex" if first.get("type") == "session_meta" else "claude"), path.resolve()
    named = sorted((codex_home() / "sessions").glob(f"*/*/*/rollout-*-{ref}.jsonl"))
    if named:
        return "codex", named[-1]
    named = sorted((Path.home() / ".claude" / "projects").glob(f"*/{ref}.jsonl"))
    if named:
        return "claude", named[-1]
    raise SessionNotFound(f"No session file or id '{ref}' under {codex_home() / 'sessions'} "
                          f"or {Path.home() / '.claude' / 'projects'}")


def _codex_turn(row: dict) -> dict | None:
    payload = row.get("payload") or {}
    if row.get("type") != "response_item" or payload.get("type") != "message":
        return None
    if payload.get("role") not in ("user", "assistant"):
        return None
    text = "\n".join(part.get("text", "") for part in payload.get("content") or []
                     if isinstance(part, dict) and part.get("type") in ("input_text", "output_text"))
    goal = GOAL.match(text) if payload["role"] == "user" else None
    if goal:
        return {"role": "user", "text": f"Goal: {goal.group(1)}", "timestamp": row.get("timestamp", ""),
                "goal": goal.group(1)}
    return _spoken(payload["role"], text, row.get("timestamp", ""))


def _claude_turn(row: dict) -> dict | None:
    attachment = row.get("attachment") or {}
    if attachment.get("type") == "queued_command" and (attachment.get("origin") or {}).get("kind") == "human":
        return _spoken("user", _text(attachment.get("prompt")), row.get("timestamp", ""))
    if row.get("type") not in ("user", "assistant") or row.get("isMeta") or row.get("isSidechain") \
            or row.get("isCompactSummary"):
        return None
    return _spoken(row["type"], _text((row.get("message") or {}).get("content")), row.get("timestamp", ""))


def _text(content) -> str:
    """A Claude Code message body: a string, or a list whose text parts are what was said."""
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content
                         if isinstance(part, dict) and part.get("type") == "text")
    return content if isinstance(content, str) else ""


def _spoken(role: str, text: str, when: str) -> dict | None:
    if not text.strip():
        return None
    if role == "user" and (INJECTED_BLOCK.match(text) or CLIENT_NOTICE.match(text)):
        return None
    return {"role": role, "text": text.strip(), "timestamp": when}


def places(agent: str, path: Path) -> list[tuple[Path, str, str]]:
    """The directories the session worked in, most recent first: (folder, branch it recorded, last time there).

    Claude Code puts `cwd` and `gitBranch` on every row, and the cwd follows the session
    into worktrees. Codex records `session_meta.cwd` (with `git.branch`) and a `cwd` in
    every `turn_context`, but a session started above the repositories works in them
    through each command's `workdir`.
    """
    from . import other_agents
    if agent in other_agents.AGENTS:
        where = other_agents.folder(agent, path)
        return [(where, "", "")] if where else []
    last = {}
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            payload = row.get("payload") or {}
            if agent == "claude" and row.get("cwd"):
                cwd, branch = row["cwd"], row.get("gitBranch")
            elif row.get("type") in ("session_meta", "turn_context") and payload.get("cwd"):
                cwd, branch = payload["cwd"], (payload.get("git") or {}).get("branch")
            elif WORKDIR.search(str(payload.get("input") or payload.get("arguments") or "")):
                cwd, branch = WORKDIR.search(str(payload.get("input") or payload.get("arguments"))).group(1), ""
            else:
                continue
            branch = branch or last.pop(cwd, ("", ""))[0]
            last.pop(cwd, None)
            last[cwd] = (branch or "", row.get("timestamp", ""))   # re-inserted, so the dict ends with the latest
    return [(Path(cwd), branch, when) for cwd, (branch, when) in reversed(last.items())]


def code_at(folder: Path, branch: str = "", before: str = "") -> dict | None:
    """Where the code is, so the recipient's agent can check out the same thing; None outside a repository.

    `branch` and `before` are what the session recorded: the last commit on that branch by the
    time the session last worked there, not whatever the folder has checked out today."""
    if not shutil.which("git") or not Path(folder).is_dir():
        return None
    git = lambda *args: subprocess.run(["git", "-C", str(folder), *args], capture_output=True, text=True)
    at = lambda ref: git("rev-list", "-1", *([f"--before={before}"] if before else []), ref)
    if branch and branch != "HEAD":
        head = at(branch)
    else:   # detached: where HEAD actually was then, from the reflog; today's HEAD may have moved back
        head = git("rev-parse", "--verify", "-q", f"HEAD@{{{before}}}") if before else at("HEAD")
        head = head if head.returncode == 0 and head.stdout.strip() else at("HEAD")
    if head.returncode or not head.stdout.strip():   # the recorded branch is gone: what is checked out
        head, branch = at("HEAD"), ""
    if head.returncode or not head.stdout.strip():   # not a repository, or no commit by then
        return None
    commit = head.stdout.strip()
    remote = git("remote", "get-url", "origin").stdout.strip()
    return {"repository": re.sub(r"//[^/@]+@", "//", remote) or None,   # never a user:token@ in a URL
            "branch": branch if branch and branch != "HEAD" else _branch_of(git, commit),
            "commit": commit,
            "pushed": bool(git("branch", "-r", "--contains", commit).stdout.strip()),
            # Changes in the folder today belong to that commit only if it is still what is checked out.
            "uncommitted": len(git("status", "--porcelain").stdout.splitlines())
            if commit == git("rev-parse", "HEAD").stdout.strip() else 0}


def _branch_of(git, commit: str) -> str:
    """A branch at `commit`, local first: Claude Code records "HEAD" once a session cd's into a repository
    (#2416). "HEAD" when no branch points there, which is what detached means."""
    for args in (("branch", "--points-at", commit), ("branch", "-r", "--points-at", commit)):
        names = [n.strip() for n in git(*args, "--format=%(refname:short)").stdout.splitlines()]
        names = [n.removeprefix("origin/") for n in names if n and "HEAD" not in n]
        if names:
            return names[0]
    return "HEAD"


def code_for(agent: str, path: Path, limit: int = 3, since: str = "") -> list[dict]:
    """The repositories the session worked in, most recent first, one entry per repository and commit."""
    return [code for code, _ in code_with_folders(agent, path, limit, since)]


def code_with_folders(agent: str, path: Path, limit: int = 3, since: str = "") -> list[tuple[dict, Path]]:
    """code_for, with the local folder of each, which never leaves this machine.

    `since` (the first handed-off message's time) leaves out folders the session only worked in
    before it: with --since, the other work earlier in the session is not the recipient's."""
    found = []
    for folder, branch, when in places(agent, path):
        if since and _moment(when) < _moment(since):
            continue
        code = code_at(folder, branch, when)
        if code and all((c["repository"], c["commit"]) != (code["repository"], code["commit"]) for c, _ in found):
            found.append((code, Path(folder)))
    return found[:limit]


def code_patch(folder: Path, code: dict) -> dict | None:
    """What the recipient cannot fetch (#2469): commits on no remote, as `git format-patch` text, and
    changes not committed, as a diff (new files included). None when everything is pushed."""
    if code["pushed"] and not code["uncommitted"]:
        return None
    git = lambda *args, ok=(0,): _git_out(folder, args, ok)
    base = ""
    if not code["pushed"] and code["repository"]:
        oldest = git("rev-list", "--reverse", code["commit"], "--not", "--remotes").split()[:1]
        # Nothing on the remote yet: the oldest unpushed commit is the root, which has no parent.
        base = git("rev-parse", "--verify", "-q", f"{oldest[0]}^", ok=(0, 1)).strip() if oldest else code["commit"]
    commits = "" if code["pushed"] else git("format-patch", "--stdout", "--binary",
                                             *([f"{base}..{code['commit']}"] if base else ["--root", code["commit"]]))
    changes = git("diff", "--binary", code["commit"]) if code["uncommitted"] else ""
    untracked = git("ls-files", "--others", "--exclude-standard").splitlines() if code["uncommitted"] else []
    for new in [f for f in untracked if not BYTECODE.search(f)]:   # a repo with no .gitignore keeps its .pyc
        changes += git("diff", "--binary", "--no-index", "/dev/null", new, ok=(0, 1))
    return {"name": Path(folder).name, "base": base or (code["commit"] if code["pushed"] else ""),
            "commits": commits, "changes": changes}


BYTECODE = re.compile(r"(^|/)__pycache__/|\.py[co]$")


def _git_out(folder: Path, args: tuple, ok: tuple) -> str:
    # diffs can contain bytes that are not UTF-8 (#2570); never let decode kill the send
    done = subprocess.run(
        ["git", "-C", str(folder), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if done.returncode not in ok:
        raise RuntimeError(f"git {' '.join(args)} failed in {folder}: {done.stderr.strip()}")
    return done.stdout


def patch_digest(patch: dict) -> dict:
    """What the sealed bundle records about a patch that travels beside it, so accept can check it."""
    import hashlib
    body = json.dumps(patch, sort_keys=True).encode()
    return {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def _moment(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def titles(agent: str, path: Path) -> dict[str, str]:
    """Issue and PR titles the session already read (gh output in its tool results): {"1043": "title"}.

    So a handoff can say what #1043 is without fetching anything, even for a private repository."""
    found = {}
    if agent not in ("codex", "claude", "droid"):   # the others keep tool output elsewhere, or not at all
        return found
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if '"title' in line or "title:" in line or "\\t" in line:
                for output in _tool_outputs(json.loads(line)):
                    found.update(_titles_in(_unescaped(output)))
    return found


# What a session read that is the sender's own and not the work: every leak on 2026-10-14 came from
# an AI reply quoting one of them.
READS = {"mail": re.compile(r"\bco (?:gmail|outlook|email|inbox)\b|Gmail__|search_threads|get_thread|\bgws gmail\b"),
         "co rem pages": re.compile(r"\bco rem\b|\.co/rem\b")}


def reads_private(agent: str, path: Path) -> list[str]:
    """Which of READS the session's tool calls touched, from the calls themselves, not what anyone said."""
    found = set()
    if agent not in ("codex", "claude", "droid"):
        return []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if "tool_use" in line or "function_call" in line or "custom_tool_call" in line:
                calls = re.sub(r'\\?"\s*,\s*\\?"', " ", " ".join(_tool_calls(json.loads(line))))   # ["co", "rem"]
                found |= {what for what, pattern in READS.items() if pattern.search(calls)}
    return sorted(found, key=list(READS).index)


def _tool_calls(row: dict) -> list[str]:
    payload = row.get("payload") or {}
    if payload.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
        return [json.dumps(payload.get("arguments") or payload.get("input") or payload.get("action") or "")
                + " " + str(payload.get("name", ""))]
    content = (row.get("message") or {}).get("content")
    return [part.get("name", "") + " " + json.dumps(part.get("input")) for part in content
            if isinstance(part, dict) and part.get("type") == "tool_use"] if isinstance(content, list) else []


def _tool_outputs(row: dict) -> list[str]:
    payload = row.get("payload") or {}
    if payload.get("type") in ("function_call_output", "custom_tool_call_output"):
        output = payload.get("output")
        return [output if isinstance(output, str) else json.dumps(output)]
    content = (row.get("message") or {}).get("content")
    results = [part.get("content") for part in content if isinstance(part, dict) and part.get("type") == "tool_result"] \
        if isinstance(content, list) else []
    return [r if isinstance(r, str) else _text(r) for r in results]


def _unescaped(text: str) -> str:
    """gh JSON inside a tool's JSON output arrives escaped two or three times over."""
    for _ in range(4):
        text = text.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\")
    return text


LIST_ROW = re.compile(r"^#?(\d{1,6})\t(.+)$", re.M)
STATES = {"OPEN", "CLOSED", "MERGED", "DRAFT"}


def _titles_in(text: str) -> dict[str, str]:
    """{number: title}, keeping only text shaped like a title: tables also have numbered rows of dates and addresses."""
    return {n: t for n, t in _candidates(text).items() if TITLE_SHAPE.match(t) and not re.match(r"0x[0-9a-f]{8}|\d{4}-\d\d", t)}


# Words and a space, not a date or an address.
TITLE_SHAPE = re.compile(r"^(?=.*[A-Za-z].*[A-Za-z])(?=.*\s).{8,}$")


def _candidates(text: str) -> dict[str, str]:
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    found = {}
    # gh --json: each issue's fields lie between its "number" and the next one's
    parts = re.split(r'"number"\s*:\s*', text)
    for before, part in zip(parts, parts[1:]):
        number = re.match(r"\d+", part)
        title = re.search(r'"title"\s*:\s*"([^"\n]{3,300})"', part) or re.search(r'"title"\s*:\s*"([^"\n]{3,300})"[^"]*$', before)
        if number and title:
            found[number.group(0)] = title.group(1)
    # gh issue/pr view: "title:\t…" and "number:\t…" lines
    view_title, view_number = re.search(r"^title:\t(.+)$", text, re.M), re.search(r"^number:\t(\d+)$", text, re.M)
    if view_title and view_number:
        found[view_number.group(1)] = view_title.group(1).strip()
    # gh issue list: number, state, title, …; gh pr list: number, title, branch, state, …
    # A numbered row without a state column is some other table (workflow runs, a co listing).
    for number, rest in LIST_ROW.findall(text):
        columns = rest.split("\t")
        if columns[0] in STATES and len(columns) > 1:
            found.setdefault(number, columns[1])
        elif STATES & set(columns[1:]):
            found.setdefault(number, columns[0])
    return found
