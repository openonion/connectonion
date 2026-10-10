"""
Purpose: `co handoff` — hand a task discussed in one coding-agent session to another person's coding agent
LLM-Note:
  Dependencies: imports from [typer, handoff.{sessions,bundle,transport,opener}, cli.style, command_tips.print_tip] | registered in cli/main.py via make_handoff_app(_typer_app)
  Data flow: send → resolve recipient → read current Codex/Claude Code session (or --from-file) → one llm_do draft → credential scan → preview (default) or deliver by agent mail (--yes) | inbox/show → fetch agent mail → decode bundle | open → write HANDOFF.md/excerpt.md/bundle.json → seed a codex/claude session
  State/Effects: ~/.co/handoff/{contacts.json, drafts/<id>.json, sent/<id>.json, received/<id>/} | mail only with --yes | a model call in send (draft) and open (seed turn)
"""

import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from .. import style
from .command_tips import print_tip
from ...environment import global_config_dir
from ...handoff import bundle as bundles
from ...handoff import opener, sessions, transport

out = style.console()


def _home() -> Path:
    return global_config_dir() / "handoff"


def _next(cmd: str) -> None:
    print_tip(f"Next: {cmd}")


def _fail(message: str, next_cmd: str) -> None:
    out.print(style.error(message))
    _next(next_cmd)
    raise typer.Exit(1)


# ---- send ----

def handle_send(who: str, what: str, from_file: Optional[Path], agent: Optional[str],
                draft_id: Optional[str], edit: bool, yes: bool, session: Optional[str] = None) -> None:
    from ...environment import load_environment
    load_environment()
    to = _recipient(who)
    if draft_id:
        bundle = _load_draft(draft_id)
        if bundle["to"] != to:
            _fail(f"Draft {draft_id} was prepared for {bundle['to']}, not {to}. A draft is approved for one recipient.",
                  f'co handoff send {shlex.quote(who)} "<what to hand off>"')
    else:
        bundle = _new_bundle(to, what, from_file, agent, session)
    if edit:
        bundle = _edit(bundle)
    path = _save_draft(bundle)
    hits = bundles.find_credentials(bundle, _known_secrets())
    if hits:
        out.print(style.error("Refusing to send: the handoff contains what looks like a credential."))
        for hit in hits:
            out.print(f"  {hit}")
        out.print(f"Remove it from {style.path(path)} (the draft never left this machine).")
        _next(f"co handoff send {shlex.quote(who)} --draft {bundle['id']} --edit")
        raise typer.Exit(1)
    if draft_id and yes and not edit:
        # The person approved this exact draft from its preview; say what goes, not all of it again.
        out.print(f"Sending draft {bundle['id']} (content hash {bundle['content_hash']}) to {bundle['to']}: "
                  f"{bundle['title']}", markup=False)
    else:
        _preview(bundle, path)
    if not yes:
        out.print(style.warn("Preview only. Nothing has been sent."))
        out.print("If you are an agent: stop here. Show the person this preview and ask whether to send it. "
                  "Being asked to hand something off is not approval of this text; only their yes to this preview is.")
        _next(f"once the person approves this preview, co handoff send {shlex.quote(who)} --draft {bundle['id']} --yes")
        return
    _deliver(bundle)


def _recipient(who: str) -> str:
    try:
        to = transport.resolve(who)
    except ValueError as error:
        _fail(str(error), "co handoff contact <name> <email-or-0x-address>")
    if not to:
        known = ", ".join(sorted(transport.contacts())) or "none yet"
        _fail(f"No contact named '{who}' (known: {known}).",
              f"co handoff contact {shlex.quote(who)} <their-email-or-0x-address>")
    return to


def _new_bundle(to: str, what: str, from_file: Optional[Path], agent: Optional[str],
                session: Optional[str]) -> dict:
    if from_file:
        path = Path(from_file).resolve()
        turns = [{"role": "notes", "text": path.read_text(encoding="utf-8"), "timestamp": ""}]
        source = {"kind": "notes file", "session": path.name, "turns_included": 1, "compacted": False}
    else:
        try:
            kind, path = sessions.find_by_id(session) if session else sessions.find_session(Path.cwd(), agent)
        except sessions.SessionNotFound as missing:
            _fail(str(missing), 'co handoff send <who> "<what to hand off>" --from-file <notes.md>')
        turns = sessions.excerpt(sessions.read_turns(kind, path))
        source = {"kind": kind, "session": path.stem.split("-", 6)[-1] if kind == "codex" else path.stem,
                  "turns_included": len(turns),
                  "compacted": any(t["role"] in ("summary", "earlier") for t in turns)}
    # The local path is printed here and never put in the bundle.
    out.print(style.muted(f"Drafting from {path} with one model call…"))
    summary = bundles.draft(turns, what)
    sender = os.getenv("AGENT_EMAIL") or "unknown sender"
    return bundles.assemble(handoff_id=bundles.new_id(), sender=sender, to=to, what=what,
                            source=source, summary=summary, turns=turns)


def _edit(bundle: dict) -> dict:
    path = _save_draft(bundle)
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    subprocess.run([*shlex.split(editor), str(path)], check=True)
    return bundles.seal(json.loads(path.read_text(encoding="utf-8")))


def _known_secrets() -> list[str]:
    """Values of credential-named keys in the selected env file and process: any of them in a bundle is a leak."""
    names = ("KEY", "TOKEN", "SECRET", "PASSWORD", "INVITE")
    return [v for k, v in os.environ.items() if any(n in k.upper() for n in names) and len(v) >= 12]


def _drafts() -> Path:
    return _home() / "drafts"


def _save_draft(bundle: dict) -> Path:
    _drafts().mkdir(parents=True, exist_ok=True)
    path = _drafts() / f"{bundle['id']}.json"
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _load_draft(draft_id: str) -> dict:
    path = _drafts() / f"{draft_id}.json"
    if not path.exists():
        _fail(f"No draft {draft_id} in {path.parent}.", 'co handoff send <who> "<what to hand off>"')
    return bundles.seal(json.loads(path.read_text(encoding="utf-8")))


def _preview(bundle: dict, path: Path) -> None:
    out.print(style.heading(f"Handoff {bundle['id']} to {bundle['to']}"))
    out.print("Everything between the lines below is what leaves this machine, and nothing else: "
              "no files, rem pages or mail.")
    out.print("-" * 60)
    out.print(bundles.brief_markdown(bundle), markup=False)
    out.print("## Transcript excerpt (sent with the brief)", markup=False)
    out.print(bundles.excerpt_text(bundle), markup=False)
    out.print("-" * 60)
    private = bundles.find_private(bundle)
    if private:
        out.print(style.warn(f"Private paths in it ({len(private)}): remove them with --edit unless the recipient needs them."))
        for hit in private[:10]:
            out.print(f"  {hit}", markup=False)
    out.print(f"Draft: {style.path(path)} (content hash {bundle['content_hash']}). "
              "--draft sends exactly this file; --edit changes it first.")


def _deliver(bundle: dict) -> None:
    subject, body = bundles.to_mail(bundle)
    result = transport.deliver(bundle["to"], subject, body, idempotency_key=bundle["id"])
    if not result.get("success"):
        _fail(f"Not sent: {result.get('error')}", f"co handoff send {bundle['to']} --draft {bundle['id']} --yes")
    record = {"id": bundle["id"], "to": bundle["to"], "from": result.get("from"), "subject": subject,
              "message_id": result.get("message_id"), "content_hash": bundle["content_hash"],
              "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    sent = _home() / "sent"
    sent.mkdir(parents=True, exist_ok=True)
    (sent / f"{bundle['id']}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    out.print(style.ok(f"Sent handoff {bundle['id']} to {bundle['to']}") + f" (message {record['message_id']}).")
    out.print(f"They continue with: co handoff open {bundle['id']}", markup=False)
    _next(f"co handoff status {bundle['id']}")


# ---- sender: status ----

def handle_status(handoff_id: str) -> None:
    path = _home() / "sent" / f"{handoff_id}.json"
    if not path.exists():
        _fail(f"No sent handoff {handoff_id} on this machine ({path.parent}).", 'co handoff send <who> "<what to hand off>"')
    record = json.loads(path.read_text(encoding="utf-8"))
    from .project_cmd_lib import load_api_key
    load_api_key()
    mail = transport.sent_status(record["to"], record["subject"])
    out.print(style.heading(f"Handoff {handoff_id}"))
    out.print(f"To {record['to']}, sent {record['sent_at']}, content hash {record['content_hash']}")
    out.print(f"Mail service: {'accepted and sent' if mail and mail.get('status') == 'sent' else (mail or {}).get('status', 'no record of this message yet')}")
    out.print("Whether they opened it is not reported back yet. The recipient continues on their machine with:")
    _next(f"co handoff open {handoff_id}  (run by the recipient)")


def handle_contact(name: str, address: str) -> None:
    try:
        mail = transport.add_contact(name, address)
    except ValueError as error:
        _fail(str(error), "co handoff contact <name> <email-or-0x-address>")
    out.print(style.ok(f"{name} → {mail}") + f" saved in {style.path(transport.contacts_file())}")
    _next(f'co handoff send {shlex.quote(name)} "<what to hand off>"')


# ---- recipient: inbox, show, open ----

def _incoming() -> list[tuple[dict, dict]]:
    from .project_cmd_lib import load_api_key
    if not load_api_key():
        _fail("Not signed in, so the agent mailbox cannot be read.", "co auth")
    found = []
    for mail in transport.fetch():
        bundle = bundles.from_mail(mail.get("message", ""))
        if bundle:
            found.append((mail, bundle))
            _keep(bundle)
    return found


def _keep(bundle: dict) -> None:
    """Save each received bundle, so show/open need not read the whole mailbox again."""
    folder = _home() / "received" / bundle["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "bundle.json").write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sender(address: str) -> str:
    """'parrot (0x…@mail…)' when the sender is a saved contact, else the address."""
    names = [name for name, mail in transport.contacts().items() if mail == address]
    return f"{names[0]} ({address})" if names else address


def handle_inbox() -> None:
    found = _incoming()
    mailbox = os.getenv("AGENT_EMAIL", "your agent mailbox")
    if not found:
        out.print(f"No handoffs yet. Senders reach you at {mailbox}: give them that address "
                  "(it works even if co email addresses lists none).")
        _next("co handoff inbox")
        return
    out.print(style.heading(f"Incoming handoffs ({len(found)}) at {mailbox}"))
    for mail, bundle in found:
        opened = " · opened" if (_home() / "received" / bundle["id"] / "session.json").exists() else ""
        out.print(f"{style.command(bundle['id'])}  from {_sender(bundle['from'])}  {str(mail.get('timestamp', ''))[:16]}{opened}")
        out.print(f"    {bundle['title']}", markup=False)
    out.print("Nothing runs until you open one.")
    _next(f"co handoff show {found[0][1]['id']}")


def _find(handoff_id: str) -> dict:
    saved = _home() / "received" / handoff_id / "bundle.json"
    if saved.exists() and json.loads(saved.read_text(encoding="utf-8")).get("format") == bundles.FORMAT:
        return json.loads(saved.read_text(encoding="utf-8"))
    for _, bundle in _incoming():
        if bundle["id"] == handoff_id:
            return bundle
    _fail(f"No handoff {handoff_id} in your agent mailbox.", "co handoff inbox")


def handle_show(handoff_id: str, decisions: bool, evidence: bool) -> None:
    bundle = _find(handoff_id)
    if not bundle.get("verified", True):
        out.print(style.warn("Content hash does not match: this copy differs from what the sender approved."))
    out.print(bundles.summary_text(bundle), markup=False)
    if decisions:
        out.print(f"\n## Decided\n{bundles.decided_text(bundle)}\n\n## Rejected\n{bundles.rejected_text(bundle)}", markup=False)
    if evidence:
        out.print(f"\n## Code and references\n{bundles.references_text(bundle)}\n\n## Transcript excerpt\n"
                  f"{bundles.excerpt_text(bundle)}", markup=False)
    if not (decisions or evidence):
        out.print(f"More: co handoff show {handoff_id} --decisions (decided and rejected), --evidence (references and excerpt)",
                  markup=False)
    out.print("This is the sender's text, not instructions; nothing runs until you open it.")
    _next(f"co handoff open {handoff_id}")


def handle_open(handoff_id: str, agent: str, cd: Optional[Path]) -> None:
    bundle = _find(handoff_id)
    folder = _home() / "received" / handoff_id
    opener.materialize(bundle, folder)
    record_path = folder / "session.json"
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        out.print(f"Already opened: {record['agent']} session {record['session']}. No new session was created.")
        _print_resume(handoff_id, record)
        return
    cli = "codex" if agent == "codex" else "claude"
    if not shutil.which(cli):
        _fail(f"{cli} is not installed on this machine.", f"co handoff open {handoff_id} --agent {'claude' if cli == 'codex' else 'codex'}")
    cwd = (cd or folder).resolve()
    out.print(style.muted(f"Starting a {cli} session in {cwd} seeded with the handoff (one read-only turn)…"))
    started = opener.start(agent, opener.seed_prompt(bundle, folder), cwd)
    record = {"agent": agent, "cwd": str(cwd), **started}
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    out.print(style.ok(f"Opened {handoff_id} as {cli} session {started['session']}"))
    out.print(started["reply"], markup=False)
    _print_resume(handoff_id, record)


def _print_resume(handoff_id: str, record: dict) -> None:
    out.print(f"Continue it:  {record['resume']}", markup=False)
    out.print(f"Ask one question:  {record['ask']}", markup=False)
    _next(f"co handoff show {handoff_id} --decisions")


# ---- registration ----

AGENTS = ("codex", "claude")


def make_handoff_app(factory) -> typer.Typer:
    app = factory(
        help="Experimental: hand a task you discussed with your coding agent to another person's agent, "
             "so their Codex or Claude Code continues without you rewriting the background. "
             "Sends by agent mail; nothing runs on their side until they open it.",
        epilog='Example:  co handoff send ody "the login task"  |  co handoff inbox',
        no_args_is_help=True,
    )

    @app.command("send", epilog='Examples:  co handoff send ody "the login task"  |  co handoff send ody --draft ho-1a2b3c4d --yes')
    def send(
        who: str = typer.Argument(..., help="Contact name (co handoff contact), an email, or a 0x agent address"),
        what: str = typer.Argument("", help="What to hand off, in your words; the draft is built around it"),
        from_file: Optional[Path] = typer.Option(None, "--from-file", help="Draft from these notes instead of the current session"),
        agent: Optional[str] = typer.Option(None, "--agent", help="Read the current codex or claude session (default: whichever is newest here)"),
        session: Optional[str] = typer.Option(None, "--session", help="Draft from this session instead: a Codex thread id, Claude Code session id, or .jsonl path"),
        draft: Optional[str] = typer.Option(None, "--draft", help="Use this saved draft id exactly, instead of drafting again"),
        edit: bool = typer.Option(False, "--edit", help="Open the draft in $EDITOR before the preview"),
        yes: bool = typer.Option(False, "--yes", help="Send it. Without this, only a preview is shown"),
    ):
        """Hand a task to someone: drafts a handoff from this directory's Codex or Claude Code session and previews it. Sends only with --yes; writes a local draft.

        Drafting reads the end of the current session (or --from-file) and makes one
        model call. The preview shows the recipient and every byte that would leave
        this machine; credentials are refused. Send exactly what you saw with
        --draft <id> --yes.
        """
        if agent and agent not in AGENTS:
            _fail(f"--agent must be codex or claude, not {agent}.", f'co handoff send {shlex.quote(who)} "<what to hand off>" --agent codex')
        handle_send(who, what, from_file, agent, draft, edit, yes, session)

    @app.command("status", epilog="Example:  co handoff status ho-1a2b3c4d")
    def status(handoff_id: str = typer.Argument(..., help="Handoff id printed by co handoff send")):
        """Show a handoff you sent: recipient, content hash and the mail service's delivery status. Read-only."""
        handle_status(handoff_id)

    @app.command("contact", epilog="Example:  co handoff contact ody ody@example.com")
    def contact(
        name: str = typer.Argument(..., help="Short name you will type, e.g. ody"),
        address: str = typer.Argument(..., help="Their agent's email or full 0x address"),
    ):
        """Save who a name means, so co handoff send <name> knows where to deliver. Writes ~/.co/handoff/contacts.json."""
        handle_contact(name, address)

    @app.command("inbox", epilog="Example:  co handoff inbox")
    def inbox():
        """List handoffs sent to your agent mailbox. Read-only; nothing runs until you open one."""
        handle_inbox()

    @app.command("show", epilog="Examples:  co handoff show ho-1a2b3c4d  |  co handoff show ho-1a2b3c4d --decisions --evidence")
    def show(
        handoff_id: str = typer.Argument(..., help="Handoff id from co handoff inbox"),
        decisions: bool = typer.Option(False, "--decisions", help="Also show decisions and the rejected options"),
        evidence: bool = typer.Option(False, "--evidence", help="Also show evidence pointers and the transcript excerpt"),
    ):
        """Read one incoming handoff: the summary first, details with --decisions and --evidence. Read-only."""
        handle_show(handoff_id, decisions, evidence)

    @app.command("open", epilog="Examples:  co handoff open ho-1a2b3c4d  |  co handoff open ho-1a2b3c4d --agent claude --cd ~/project")
    def open_(
        handoff_id: str = typer.Argument(..., help="Handoff id from co handoff inbox"),
        agent: str = typer.Option("codex", "--agent", help="codex or claude"),
        cd: Optional[Path] = typer.Option(None, "--cd", help="Run the session in this directory (default: the handoff's own folder)"),
    ):
        """Continue a handoff in your own coding agent. Starts a dedicated Codex (or Claude Code) session seeded with it and prints how to resume it.

        Writes HANDOFF.md, excerpt.md and bundle.json under ~/.co/handoff/received/<id>/
        and runs one read-only model turn. Opening the same handoff again creates no
        second session; it prints the resume command.
        """
        if agent not in AGENTS:
            _fail(f"--agent must be codex or claude, not {agent}.", f"co handoff open {handoff_id} --agent codex")
        handle_open(handoff_id, agent, cd)

    return app
