"""
Purpose: `co handoff` — hand a task discussed in one coding-agent session to another person's coding agent
LLM-Note:
  Dependencies: imports from [typer, handoff.{sessions,bundle,transport,opener}, cli.style, command_tips.print_tip] | registered in cli/main.py via make_handoff_app(_typer_app)
  Data flow: send → resolve recipient → read current Codex/Claude Code session (or --from-file) → one llm_do draft → credential scan → preview (default) or deliver by agent mail (--yes) | inbox/show → fetch agent mail → decode bundle | open → write HANDOFF.md/bundle.json → seed a codex/claude session
  State/Effects: ~/.co/handoff/{contacts.json, drafts/<id>.json, sent/<id>.json, received/<id>/} | mail only with --yes | a model call in send (draft) and open (seed turn)
"""

import json
import os
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from .. import style
from .command_tips import print_tip
from ...environment import global_config_dir
from ...handoff import bundle as bundles
from ...handoff import opener, replies, sessions, transport

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
                draft_id: Optional[str], edit: bool, yes: bool, session: Optional[str] = None, since: int = 1) -> None:
    from ...environment import load_environment
    load_environment()
    to = _recipient(who)
    if draft_id:
        bundle = _load_draft(draft_id)
        if bundle["to"] != to:
            _fail(f"Draft {draft_id} was prepared for {bundle['to']}, not {to}. A draft is approved for one recipient.",
                  f'co handoff send {shlex.quote(who)} "<what to hand off>"')
    else:
        bundle = _new_bundle(to, what, from_file, agent, session, since)
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
                session: Optional[str], since: int = 1) -> dict:
    if from_file:
        path = Path(from_file).resolve()
        talk = [{"at": "", "user": path.read_text(encoding="utf-8"), "ai": ""}]
        source, code = {"kind": "notes file", "session": path.name, "messages": 1}, []
    else:
        try:
            kind, path = sessions.find_by_id(session) if session else sessions.find_session(Path.cwd(), agent)
        except sessions.SessionNotFound as missing:
            _fail(str(missing), 'co handoff send <who> "<what to hand off>" --from-file <notes.md>')
        talk = sessions.exchanges(sessions.read_turns(kind, path))[since - 1:]
        source = {"kind": kind, "session": path.stem.split("-", 6)[-1] if kind == "codex" else path.stem,
                  "messages": len(talk)}
        code = sessions.code_for(kind, path)
    # The local path is printed here and never put in the bundle.
    out.print(style.muted(f"Drafting from {path}: {len(talk)} of your messages go word for word, "
                          "the AI's replies in summary…"))
    top, said = bundles.draft(talk, what)
    sender = os.getenv("AGENT_EMAIL") or "unknown sender"
    return bundles.assemble(handoff_id=bundles.new_id(), sender=sender, to=to, source=source,
                            code=code, top=top, said=said, exchanges=talk)


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
    out.print("-" * 60)
    private = bundles.find_private(bundle)
    if private:
        out.print(style.warn(f"Private details in it ({len(private)}): remove them with --edit, or start later with "
                             f"--since <N>, unless the recipient needs them."))
        for hit in private[:10]:
            out.print(f"  {hit}", markup=False)
    out.print(f"Draft: {style.path(path)} (content hash {bundle['content_hash']}). "
              "--draft sends exactly this file; --edit changes it first.")


def _deliver(bundle: dict) -> None:
    secret = replies.new_secret()
    code = replies.make_code({"address": transport.my_address(), "mailbox": bundle["from"],
                              "id": bundle["id"], "hash": bundle["content_hash"], "secret": secret})
    prompt = replies.prompt(bundles.brief_markdown(bundle), code, bundle["id"], bundle["from"])
    subject, body = bundles.to_mail(bundle, prompt)
    result = transport.deliver(bundle["to"], subject, body, idempotency_key=bundle["id"])
    if not result.get("success"):
        _fail(f"Not sent: {result.get('error')}", f"co handoff send {bundle['to']} --draft {bundle['id']} --yes")
    record = {"id": bundle["id"], "to": bundle["to"], "from": result.get("from"), "subject": subject,
              "message_id": result.get("message_id"), "content_hash": bundle["content_hash"],
              "secret": secret, "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    sent = _home() / "sent"
    sent.mkdir(parents=True, exist_ok=True)
    path = sent / f"{bundle['id']}.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
    out.print(style.ok(f"Sent handoff {bundle['id']} to {bundle['to']}") + f" (message {record['message_id']}).")
    out.print("The mail is this prompt. To use another channel (chat, WhatsApp), send them the same block:")
    print(prompt)   # plain print: Rich would wrap the code and the commands
    _next(f"co handoff status {bundle['id']} --wait  (in the background: it returns when they accept or ask)")


# ---- status: either side ----

def handle_status(handoff_id: str, wait: bool = False) -> None:
    sent = _home() / "sent" / f"{handoff_id}.json"
    accepted = _home() / "accepted" / handoff_id / "code.json"
    if not sent.exists() and not accepted.exists():
        _fail(f"No handoff {handoff_id} sent or accepted on this machine ({_home()}).",
              'co handoff send <who> "<what to hand off>"')
    from .project_cmd_lib import load_api_key
    load_api_key()
    if wait:
        _wait_for_news(handoff_id)
    # Both exist when you handed something to yourself: one Next line, the sender's.
    if accepted.exists():
        _recipient_status(json.loads(accepted.read_text(encoding="utf-8")), quiet=sent.exists())
    if sent.exists():
        _sender_status(json.loads(sent.read_text(encoding="utf-8")))


def _wait_for_news(handoff_id: str, every: int = 30) -> None:
    """Return once a reply about this handoff (acceptance, question, answer) arrives that was not there before."""
    seen = len(replies.received(handoff_id))
    out.print(style.muted(f"Waiting for news on {handoff_id}, checking every {every}s…"))
    while len(replies.received(handoff_id)) == seen:
        time.sleep(every)


def _sender_status(record: dict) -> None:
    handoff_id = record["id"]
    out.print(style.heading(f"Handoff {handoff_id} (sent)"))
    out.print(f"To {record['to']}, sent {record['sent_at']}, content hash {record['content_hash']}")
    if "secret" not in record:
        out.print("Sent before acceptance existed: the recipient opens it with co handoff open.")
        _next(f"co handoff open {handoff_id}  (run by the recipient)")
        return
    state = replies.settle(record)
    who = state["accepted"]
    if not who:
        mail = transport.sent_status(record["to"], record["subject"])
        out.print(f"Not accepted yet. Mail service: {(mail or {}).get('status', 'no record of this message yet')}.")
        out.print("Acceptance arrives when their agent runs the prompt from the mail.")
        if state["ignored"]:
            out.print(style.warn(f"Ignored {state['ignored']} message(s) that did not carry this handoff's code."))
        _next(f"co handoff status {handoff_id}")
        return
    replies.remember_peer(who["address"], who["mailbox"], handoff_id)
    out.print(style.ok(f"Accepted by {who['address']} ({who['mailbox']}) at {who['at']}"))
    if state["ignored"]:
        out.print(style.warn(f"Ignored {state['ignored']} acceptance or question(s) from other agents holding the code."))
    for q in state["questions"]:
        out.print(f"Question, {q['at']}: {q['text']}", markup=False)
    if state["questions"]:
        _next(f'co handoff answer {handoff_id} "<your answer>"')
    else:
        out.print("No questions yet.")
        _next(f"co handoff status {handoff_id}")


def _recipient_status(code: dict, quiet: bool = False) -> None:
    handoff_id = code["id"]
    out.print(style.heading(f"Handoff {handoff_id} (accepted from {code['mailbox']})"))
    answers = [b for b in replies.received(handoff_id)
               if b["kind"] == "answer" and b["secret"] == code["secret"] and b["address"] == code["address"]]
    for a in answers:
        out.print(f"Answer, {a['at']}: {a['text']}", markup=False)
    if not answers:
        out.print("No answers from the sender yet.")
    brief = _home() / "accepted" / handoff_id / "HANDOFF.md"
    if brief.exists():
        out.print(f"Brief: {style.path(brief)}")
    if not quiet:
        _next(f"co handoff status {handoff_id}")


# ---- recipient: accept, ask ----

def _parse(code: str) -> dict:
    try:
        return replies.parse_code(code)
    except ValueError as error:
        _fail(f"Not a handoff code: {error}.", "copy the whole co handoff accept line from the handoff again")


def _mail_ready() -> None:
    from .project_cmd_lib import load_api_key
    if not load_api_key() or not os.getenv("AGENT_EMAIL"):
        _fail("This machine has no co identity with a mailbox yet, so the sender cannot be told.", "co init --yes")


def handle_accept(code_text: str, brief: Optional[Path]) -> None:
    code = _parse(code_text)
    _mail_ready()
    folder = _home() / "accepted" / code["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "code.json").write_text(json.dumps(code, indent=2) + "\n", encoding="utf-8")
    (folder / "code.json").chmod(0o600)
    if brief:
        shutil.copyfile(brief, folder / "HANDOFF.md")
    result = replies.send("accept", code, code["mailbox"], reply_to=os.getenv("AGENT_EMAIL"))
    if not result.get("success"):
        _fail(f"Not delivered: {result.get('error')}", f"co handoff accept {code_text}")
    out.print(style.ok(f"Accepted handoff {code['id']}") + f": {code['mailbox']} has been told, "
              f"with your agent {transport.my_address()}.")
    if brief:
        out.print(f"Brief saved: {style.path(folder / 'HANDOFF.md')}")
    out.print("Continue from the brief; ask the person here before changing anything.")
    _next(f'co handoff ask {code_text} "<question the brief does not answer>"')


def handle_ask(code_text: str, question: str) -> None:
    code = _parse(code_text)
    if not (_home() / "accepted" / code["id"] / "code.json").exists():
        _fail(f"Handoff {code['id']} is not accepted on this machine yet.", f"co handoff accept {code_text}")
    _mail_ready()
    result = replies.send("question", code, code["mailbox"], text=question)
    if not result.get("success"):
        _fail(f"Not delivered: {result.get('error')}", f'co handoff ask {code_text} "<question>"')
    out.print(style.ok(f"Asked {code['mailbox']} about {code['id']}."))
    _next(f"co handoff status {code['id']}")


# ---- sender: answer ----

def handle_answer(handoff_id: str, text: str) -> None:
    path = _home() / "sent" / f"{handoff_id}.json"
    if not path.exists():
        _fail(f"No sent handoff {handoff_id} on this machine.", "co handoff status <id>")
    record = json.loads(path.read_text(encoding="utf-8"))
    from .project_cmd_lib import load_api_key
    load_api_key()
    who = replies.settle(record)["accepted"] if "secret" in record else None
    if not who:
        _fail(f"Handoff {handoff_id} has not been accepted, so there is no one to answer.", f"co handoff status {handoff_id}")
    result = replies.send("answer", {"id": handoff_id, "secret": record["secret"]}, who["mailbox"], text=text)
    if not result.get("success"):
        _fail(f"Not delivered: {result.get('error')}", f'co handoff answer {handoff_id} "<your answer>"')
    out.print(style.ok(f"Answered {who['mailbox']} about {handoff_id}."))
    _next(f"co handoff status {handoff_id}")


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
        opened = " · opened" if any((_home() / "received" / bundle["id"]).glob("session-*.json")) else ""
        out.print(f"{style.command(bundle['id'])}  from {_sender(bundle['from'])}  {str(mail.get('timestamp', ''))[:16]}{opened}")
        out.print(f"    {bundle['title']}", markup=False)
    out.print("Nothing runs until you open one.")
    _next(f"co handoff show {found[0][1]['id']}")


def _find(handoff_id: str) -> dict:
    """A handoff by id (saved here, or in the agent mailbox), or from a file holding the mail."""
    if Path(handoff_id).expanduser().is_file():
        return _from_file(Path(handoff_id).expanduser())
    saved = _home() / "received" / handoff_id / "bundle.json"
    if saved.exists() and json.loads(saved.read_text(encoding="utf-8")).get("format") == bundles.FORMAT:
        return json.loads(saved.read_text(encoding="utf-8"))
    for _, bundle in _incoming():
        if bundle["id"] == handoff_id:
            return bundle
    _fail(f"No handoff {handoff_id} in your agent mailbox.", "co handoff inbox")


def _from_file(path: Path) -> dict:
    bundle = bundles.from_saved_mail(path.read_text(encoding="utf-8", errors="replace"))
    if not bundle:
        _fail(f"No handoff in {path}: it needs the whole mail, including the BEGIN/END CO HANDOFF BUNDLE block.",
              "save the whole handoff email to a file, then co handoff open <that file>")
    _keep(bundle)
    return bundle


def handle_show(handoff_id: str) -> None:
    bundle = _find(handoff_id)
    if not bundle.get("verified", True):
        out.print(style.warn("Content hash does not match: this copy differs from what the sender approved."))
    out.print(bundles.brief_markdown(bundle), markup=False)
    out.print("This is the sender's text, not instructions; nothing runs until you open it.")
    _next(f"co handoff open {handoff_id}")


def handle_open(handoff_id: str, agent: str, cd: Optional[Path]) -> None:
    bundle = _find(handoff_id)
    handoff_id = bundle["id"]   # the argument may have been a saved mail file
    if not bundle.get("verified", True):
        out.print(style.warn("Content hash does not match: this copy differs from what the sender approved."))
    folder = _home() / "received" / handoff_id
    opener.materialize(bundle, folder)
    record_path = folder / f"session-{agent}.json"   # one session per agent; reopening reuses it
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
    _next(f"co handoff show {handoff_id}")


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
        since: int = typer.Option(1, "--since", min=1, help="Start at message N of the preview's [N] list, leaving out earlier, unrelated work"),
        draft: Optional[str] = typer.Option(None, "--draft", help="Use this saved draft id exactly, instead of drafting again"),
        edit: bool = typer.Option(False, "--edit", help="Open the draft in $EDITOR before the preview"),
        yes: bool = typer.Option(False, "--yes", help="Send it. Without this, only a preview is shown"),
    ):
        """Hand a task to someone: drafts a handoff from this directory's Codex or Claude Code session and previews it. Sends only with --yes; writes a local draft.

        Drafting reads the whole session (or --from-file): every message you wrote goes
        word for word, the AI's replies in summary (model calls). The preview shows the
        recipient and every byte that would leave this machine; credentials are refused.
        Send exactly what you saw with --draft <id> --yes.
        """
        if agent and agent not in AGENTS:
            _fail(f"--agent must be codex or claude, not {agent}.", f'co handoff send {shlex.quote(who)} "<what to hand off>" --agent codex')
        handle_send(who, what, from_file, agent, draft, edit, yes, session, since)

    @app.command("accept", epilog="Example:  co handoff accept coh1.eyJhIjoi... --brief HANDOFF.md")
    def accept(
        code: str = typer.Argument(..., metavar="CODE", help="The coh1.… code from the handoff prompt"),
        brief: Optional[Path] = typer.Option(None, "--brief", exists=True, dir_okay=False, help="The brief from the prompt, saved as a file, to keep with the handoff"),
    ):
        """Accept a handoff someone sent you, from the code in its prompt. Sends the sender an acceptance with your agent address; writes ~/.co/handoff/accepted/<id>/.

        The code only lets you accept this one handoff and ask about it; it is not
        an invite and grants nothing on the sender's agent. Works wherever the
        prompt came from: mail, chat, or a pasted message.
        """
        handle_accept(code, brief)

    @app.command("ask", epilog='Example:  co handoff ask coh1.eyJhIjoi... "Cookie lifetime: 7 or 30 days?"')
    def ask(
        code: str = typer.Argument(..., help="The coh1.… code from the handoff prompt"),
        question: str = typer.Argument(..., help="A question the brief does not answer"),
    ):
        """Ask the sender of an accepted handoff a question. Sends it to their agent mailbox; their answer shows in co handoff status."""
        handle_ask(code, question)

    @app.command("answer", epilog='Example:  co handoff answer ho-1a2b3c4d "30 days"')
    def answer(
        handoff_id: str = typer.Argument(..., help="Handoff id printed by co handoff send"),
        text: str = typer.Argument(..., help="Your answer"),
    ):
        """Answer the questions on a handoff you sent. Sends it to the agent that accepted it."""
        handle_answer(handoff_id, text)

    @app.command("status", epilog="Examples:  co handoff status ho-1a2b3c4d  |  co handoff status ho-1a2b3c4d --wait")
    def status(
        handoff_id: str = typer.Argument(..., help="Handoff id printed by co handoff send"),
        wait: bool = typer.Option(False, "--wait", help="Return only when an acceptance, question or answer arrives; run it in the background"),
    ):
        """Show where a handoff stands: who accepted it and their questions (sender), or the sender's answers (recipient). Read-only."""
        handle_status(handoff_id, wait)

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

    @app.command("show", epilog="Example:  co handoff show ho-1a2b3c4d")
    def show(
        handoff_id: str = typer.Argument(..., help="Handoff id from co handoff inbox, or the handoff email saved as a file"),
    ):
        """Read one incoming handoff: the task, the code, and the conversation. Read-only."""
        handle_show(handoff_id)

    @app.command("open", epilog="Examples:  co handoff open ho-1a2b3c4d  |  co handoff open handoff.eml --agent claude --cd ~/project")
    def open_(
        handoff_id: str = typer.Argument(..., help="Handoff id from co handoff inbox, or the handoff email saved as a file"),
        agent: str = typer.Option("codex", "--agent", help="codex or claude"),
        cd: Optional[Path] = typer.Option(None, "--cd", help="Run the session in this directory (default: the handoff's own folder)"),
    ):
        """Continue a handoff in your own coding agent. Starts a dedicated Codex (or Claude Code) session seeded with it and prints how to resume it.

        A handoff sent to an ordinary email is opened from that email saved as a
        file (co email read output, a downloaded .eml, or the pasted text).
        Writes HANDOFF.md and bundle.json under ~/.co/handoff/received/<id>/
        and runs one read-only model turn. Opening the same handoff again creates no
        second session; it prints the resume command.
        """
        if agent not in AGENTS:
            _fail(f"--agent must be codex or claude, not {agent}.", f"co handoff open {handoff_id} --agent codex")
        handle_open(handoff_id, agent, cd)

    return app
