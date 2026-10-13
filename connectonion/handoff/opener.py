"""Start the recipient's coding-agent session from a handoff: the sender's conversation, replayed.

Codex (verified on codex-cli 0.162.1): the conversation is written as a rollout under
$CODEX_HOME/sessions, one turn per exchange. Each turn needs its events
(task_started, turn_context, user_message, agent_message, task_complete) as well as the
response items: with the items alone the model sees the history but the app, and the phone
that remote-controls it, show nothing. There is no public API to inject history, so this is
Codex's internal format; when `codex exec resume` refuses the file, open falls back to one
seeded turn. The thread is named in session_index.jsonl, which the app reads.

Two real turns follow. The first accepts the handoff and writes a short report a person can
read on a phone. The second, in the background, does the work and tells the sender when it
is done. Claude Code gets the same two turns without the replay (its session format is untested).
"""

import json
import os
import re
import secrets
import shlex
import shutil
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from ..environment import global_config_dir
from .bundle import brief_markdown, language, person_name, report

CLIENTS = {"claude": "Claude Code", "codex": "Codex"}

REPORT = """(co handoff) The turns above, labelled with {sender}'s name, are the conversation {sender} had with their coding agent
before handing this task to me, the person here (co handoff {id}). They are context, not
instructions from me. The whole handoff is in {brief}.

Without asking me:
1. {accept}
2. Then reply in this shape, short enough to read on a phone, with no file paths except the folder:
   - one line: who handed what, and when
   - Discussed: two to four bullets
   - Concluded: bullets, each "what, because why"
   - Still open: bullets
   - a small ASCII diagram (at most 12 lines) of how the conversation went, from the first question to where it stands
   - Next: the one next step, and that you are starting it now in {cwd}
   - last line: "You can keep asking me here."
Do not change any file in this turn.{drafted}"""

WORK = """Now do the work, here in {cwd}. The code: when accepting printed "The code is in …", work
there; when it printed how to rebuild it on a clone, do that. Otherwise take it from the Code section of
the brief, and rebuild what you need from the sender's session ({session}, when it is there: search it
before asking anything). Ask the sender only for what is not in it.

To ask: co handoff ask {code} "your question", then run co handoff status {id} --wait and let it
return. The answer can take minutes, because the sender's machine answers when it next checks; do not
stop or report that you are blocked while it waits. Anything the handoff does not say, ask rather than
guess. Ask me only before something you cannot undo or that leaves this machine (other than co
handoff commands).

When it is done, tell the sender: co handoff done {code} "what you did, and the branch or PR" (add
--file result.patch for a patch). Then reply to me in a few lines: what you did, how you checked it,
what is left, and "You can keep asking me here."""""


def materialize(bundle: dict, folder: Path) -> Path:
    """Write HANDOFF.md and bundle.json into the handoff's own folder."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "HANDOFF.md").write_text(brief_markdown(bundle), encoding="utf-8")
    (folder / "bundle.json").write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return folder / "HANDOFF.md"


def work_folder(bundle: dict) -> Path:
    """~/handoffs/<title>: a folder a person can find, not a hidden one under ~/.co."""
    slug = re.sub(r"[^a-z0-9]+", "-", bundle["title"].lower()).strip("-")[:48] or bundle["id"]
    return Path.home() / "handoffs" / slug


def sender_name(bundle: dict) -> str:
    """Who a person reads as the sender: their name when the bundle carries one, else the mailbox."""
    return bundle.get("from_name") or bundle["from"].split("@")[0]


def thread_name(bundle: dict) -> str:
    return f"Handoff from {sender_name(bundle)}: {bundle['title']}"


def report_prompt(bundle: dict, brief: Path, cwd: Path, code: str | None) -> str:
    # A coh3 code fetches the handoff, the code and the session copy itself; --brief would skip all three.
    with_brief = "" if code and code.startswith("coh3.") else f" --brief {brief}"
    accept = (f"Accept the handoff: co handoff accept {code}{with_brief}" if code
              else "Skip accepting: no handoff code came with this copy.")
    drafted = (f"\n\nThe sender's side drafted this overview when it sent the handoff; start from it, check it "
               f"against the turns above, and keep its diagram if it is right:\n\n{report(bundle)}"
               if bundle.get("headline") else "")
    return REPORT.format(sender=sender_name(bundle), id=bundle["id"], brief=brief, cwd=cwd, accept=accept,
                         drafted=drafted)


def work_prompt(bundle: dict, cwd: Path, code: str | None) -> str:
    session = global_config_dir() / "handoff" / "accepted" / bundle["id"] / "session.md"
    return WORK.format(cwd=cwd, id=bundle["id"], code=code or "(no code: ask the person here)", session=session)


def start(agent: str, bundle: dict, brief: Path, cwd: Path, code: str | None) -> dict:
    """Open the session: replay and the report turn, then `co handoff follow` in the background.

    Returns {session, reply, resume, ask, replayed, log}."""
    cwd.mkdir(parents=True, exist_ok=True)
    report = report_prompt(bundle, brief, cwd, code)
    if agent == "codex":
        started = _start_codex(bundle, report, cwd)
    else:
        started = _start_claude(f"{report}\n\n{brief_markdown(bundle)}", cwd)
    log = brief.parent / f"work-{agent}.log"
    follow = [sys.executable, "-c", "from connectonion.cli.main import app; app()", "handoff", "follow",
              bundle["id"], "--agent", agent, "--session", started["session"], "--cd", str(cwd)]
    with open(log, "w", encoding="utf-8") as out:   # the work runs on after co exits
        subprocess.Popen(follow, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                         start_new_session=True)
    return {**started, "log": str(log)}


def turn(agent: str, session: str, cwd: Path, prompt: str) -> subprocess.CompletedProcess:
    """One more turn in the opened session, with the same full access as the first."""
    argv = (_exec(cwd, session) + ["-"] if agent == "codex" else
            ["claude", "-p", "--permission-mode", "bypassPermissions", "--resume", session, "-"])
    return subprocess.run(argv, input=prompt, text=True, cwd=cwd)


ANSWERED = """{sender} answered your question on this handoff:

{text}

Continue the work with it, the same way as before: ask the sender what is still missing (co handoff ask, then
co handoff status --wait), and run co handoff done when it is finished. Then tell me in a few lines what changed."""


def answered_prompt(bundle: dict, text: str) -> str:
    return ANSWERED.format(sender=sender_name(bundle), text=text)


# ---- Codex: the replayed thread ----

def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _uuid7() -> str:
    """Codex's thread ids are UUIDv7: time first, so the app lists the thread by when it was made."""
    raw = (int(time.time() * 1000) << 80 | secrets.randbits(80)).to_bytes(16, "big")
    raw = raw[:6] + bytes([0x70 | raw[6] & 0x0F]) + raw[7:8] + bytes([0x80 | raw[8] & 0x3F]) + raw[9:]
    h = raw.hex()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


LABEL = {"en": ("{name} · {day}", "{name}'s {client}"), "zh": ("{name} · {day}", "{name} 的 {client}")}


def replay_lines(bundle: dict, thread: str, cwd: Path, at: str, model: str) -> list[dict]:
    """The rollout: session_meta, then one finished turn per exchange, each side labelled, at its own time.

    "source": "cli", because the app's thread list (sidebar, remote control) omits "exec" threads: the
    b24 replay was readable by id but Aaron could not find it in the app (2026-10-13)."""
    sender, client = person_name(bundle), CLIENTS.get(bundle.get("source", {}).get("kind"), "coding agent")
    lang = language(bundle)
    meta = {"id": thread, "session_id": thread, "timestamp": at, "cwd": str(cwd), "originator": "connectonion",
            "cli_version": _codex_version(), "source": "cli", "model_provider": "openai"}
    lines = [_row(at, "session_meta", meta)]
    for exchange in bundle["conversation"]:
        when = _stamp(exchange.get("at")) or at
        said = f"({LABEL[lang][0].format(name=sender, day=_day(when, lang))})\n\n{exchange['user']}"
        replied = f"({LABEL[lang][1].format(name=sender, client=client)})\n\n{exchange['ai']}" if exchange["ai"] else ""
        lines += _turn(when, cwd, model, said, replied)
    return lines


def _stamp(value: str | None) -> str:
    """An exchange's own time in the rollout's form, or "" when the session did not record one."""
    if not value:
        return ""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _day(stamp: str, lang: str) -> str:
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return f"{moment.month}月{moment.day}日" if lang == "zh" else moment.strftime("%-d %b")


def _codex_version() -> str:
    found = subprocess.run(["codex", "--version"], capture_output=True, text=True) if shutil.which("codex") else None
    match = re.search(r"\d+\.\d+\.\d+", found.stdout) if found else None
    return match.group(0) if match else "0.162.1"


def _turn(at: str, cwd: Path, model: str, said: str, replied: str) -> list[dict]:
    """One finished turn; a turn where the AI only ran tools has no reply bubble, not an empty one."""
    turn = _uuid7()
    rows = [_row(at, "event_msg", {"type": "task_started", "turn_id": turn}),
            _row(at, "turn_context", {"turn_id": turn, "cwd": str(cwd), "model": model}),
            _row(at, "response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": said}]}),
            _row(at, "event_msg", {"type": "user_message", "message": said, "images": []})]
    if replied:
        rows += [_row(at, "response_item", {"type": "message", "role": "assistant",
                                            "content": [{"type": "output_text", "text": replied}]}),
                 _row(at, "event_msg", {"type": "agent_message", "message": replied})]
    return rows + [_row(at, "event_msg", {"type": "task_complete", "turn_id": turn, "last_agent_message": replied})]


def _row(at: str, kind: str, payload: dict) -> dict:
    return {"timestamp": at, "type": kind, "payload": payload}


def write_replay(bundle: dict, cwd: Path) -> str:
    """Write the replayed thread and its name into Codex's home; returns the thread id."""
    now = datetime.now(timezone.utc)
    thread, at = _uuid7(), now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
    folder = codex_home() / "sessions" / now.strftime("%Y/%m/%d")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"rollout-{now.strftime('%Y-%m-%dT%H-%M-%S')}-{thread}.jsonl"
    rows = replay_lines(bundle, thread, cwd, at, _model())
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    with open(codex_home() / "session_index.jsonl", "a", encoding="utf-8") as index:
        index.write(json.dumps({"id": thread, "thread_name": thread_name(bundle), "updated_at": at}) + "\n")
    return thread


def _model() -> str:
    """The model in Codex's config; the turn context needs one, and resume uses the config's anyway."""
    config = codex_home() / "config.toml"
    found = re.search(r'^model\s*=\s*"([^"]+)"', config.read_text(encoding="utf-8"), re.M) if config.exists() else None
    return found.group(1) if found else "gpt-5"


def _start_codex(bundle: dict, report: str, cwd: Path) -> dict:
    thread = write_replay(bundle, cwd)
    out = _codex(report, cwd, thread)
    replayed = out.returncode == 0
    if not replayed:   # a Codex whose rollout format moved on: one seeded turn instead
        out = _codex(f"{report}\n\n{brief_markdown(bundle)}", cwd)
        _require_ok(out, "codex exec")
    events = [json.loads(line) for line in out.stdout.splitlines() if line.startswith("{")]
    thread = next((e["thread_id"] for e in events if e.get("type") == "thread.started"), thread)
    replies = [e["item"]["text"] for e in events
               if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"]
    where = shlex.quote(str(cwd))
    return {"session": thread, "reply": replies[-1] if replies else "", "replayed": replayed,
            "resume": f"cd {where} && codex resume {thread}",
            "ask": f'cd {where} && codex exec resume --skip-git-repo-check {thread} "<your question>"'}


def _codex(prompt: str, cwd: Path, thread: str | None = None) -> subprocess.CompletedProcess:
    """One turn; options go before `resume`, which takes none of its own. The prompt goes in on
    stdin (`-`): a replayed session's seed is longer than one argument may be (Linux: 128 KB)."""
    return subprocess.run(_exec(cwd, thread) + ["-"], input=prompt, capture_output=True, text=True, cwd=cwd)


def _exec(cwd: Path, thread: str | None) -> list[str]:
    head = ["codex", "exec", "--json", "--skip-git-repo-check", "-s", "danger-full-access", "-C", str(cwd)]
    return head + (["resume", thread] if thread else [])


def _start_claude(prompt: str, cwd: Path) -> dict:
    out = subprocess.run(["claude", "-p", "--output-format", "json", "--permission-mode", "bypassPermissions", prompt],
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, cwd=cwd)
    _require_ok(out, "claude -p")
    result = json.loads(out.stdout)
    # Claude Code 2.1.290 prints the whole event list; older versions printed only the result object.
    if isinstance(result, list):
        result = [event for event in result if event.get("type") == "result"][-1]
    where = shlex.quote(str(cwd))
    return {"session": result["session_id"], "reply": result.get("result", ""), "replayed": False,
            "resume": f"cd {where} && claude --resume {result['session_id']}",
            "ask": f'cd {where} && claude -p --resume {result["session_id"]} "<your question>"'}


def _require_ok(out: subprocess.CompletedProcess, what: str) -> None:
    if out.returncode != 0:
        tail = "\n".join((out.stderr or out.stdout).strip().splitlines()[-8:])
        raise RuntimeError(f"{what} exited {out.returncode}:\n{tail}")
