"""Dashboard delivery — push the agent's ``dashboard.html`` to the browser.

The browser can't read a file inside the agent's container, so the Host reads
``dashboard.html`` from the agent's project directory and sends it over the
already-authenticated WebSocket: once on connect, and again after each run. Kept
deliberately dead simple — no filesystem watcher, no hashing, no plugin.

The file is read off the event loop and capped at ``MAX_DASHBOARD_BYTES``: it is
agent-authored, so load failures render an explanatory Home without stalling
the host or exceeding the relay envelope. The post-run push is skipped when the file hasn't
changed since this connection last saw it.
"""

import asyncio
import json
import re
from functools import lru_cache
from html import escape
from pathlib import Path
from string import Template

from ....console import Console
from ....project import project_root

DASHBOARD_FILE = "dashboard.html"
CO_DIR = ".co"
# An operator's own starting point for every agent they host. Optional; the bundled
# template is used when it isn't there.
STARTER_OVERRIDE = Path.home() / CO_DIR / "starter.html"

# File and transport are separate budgets. A normal UTF-8 dashboard can use
# 128 MiB; the 256 MiB wire envelope also accommodates sealed/base64 delivery.
MAX_DASHBOARD_BYTES = 128 * 1024 * 1024
from ...transport_limits import MAX_WEBSOCKET_MESSAGE_BYTES


def dashboard_error(message, session_id=None):
    """Keep Home visible when loading fails, without exposing file contents."""
    Console().print(f"[yellow]Control Center: {message}[/yellow]")
    frame = {"type": "DASHBOARD_SNAPSHOT", "html":
             "<!doctype html><meta charset='utf-8'><h1>Control Center could not load</h1><p>"
             + escape(message) + "</p><p>Correct the dashboard and reconnect to retry.</p>"}
    if session_id:
        frame["session_id"] = session_id
    return frame


# The project directory, resolved once at host startup. Resolving it per read would
# follow any later os.chdir (a tool, a plugin) and start serving whatever file
# happened to be in the new directory.
_project_dir = None

# What to render when the agent has not written a Home page of its own. Set once
# at host startup, for the same reason as _project_dir.
_agent_metadata = None


# Who a rendered Home is for. The starter's activity sections are read from
# .co/session_results.jsonl, which holds every caller's turns, prompt text
# verbatim. Rendered once for everyone, a stranger on `trust: open` -- or any
# contact on `careful` -- connected and read the owner's recent prompts in the
# "Recent" list, which is exactly what #696 promised a second identity could no
# longer see. So a snapshot sent over a socket is rendered *for* that socket's
# verified address: its own turns only, and the schedule (operator config, whose
# rows can be a prompt and a failure reason) only for an admin.
#
# Admins see their own turns too, not everyone's: the page is a Home, not an
# audit view, and "an identity sees only its own sessions" is a rule with no
# exception to reason about. The operator's full history is in the log.
#
# EVERYONE is for rendering in-process -- tests, tooling on the operator's own
# machine. Nothing that answers a socket may use it: read_dashboard_snapshot
# requires a viewer and has no default.
EVERYONE = object()


def viewer_for(address, is_admin=False):
    """The viewer a socket's snapshot is rendered for. No address, no activity."""
    return {"address": address, "is_admin": bool(is_admin)}


def dashboard_path():
    """Where this agent's Home page lives.

    ``.co/dashboard.html``, beside ``.co/skills/`` — both are what the agent *is*,
    as opposed to the logs and evals it accumulates.

    A ``dashboard.html`` in the project root is the older location. One that is
    already there is still served, and never moved or overwritten: an agent whose
    Home silently disappeared on upgrade would be a worse bug than an inconsistent
    path. New ones are written to ``.co/``.
    """
    root = _project_dir or project_root()
    preferred = root / CO_DIR / DASHBOARD_FILE
    if preferred.exists():
        return preferred
    legacy = root / DASHBOARD_FILE
    return legacy if legacy.exists() else preferred


def read_dashboard_snapshot(session_id=None, *, viewer):
    """Build a ``DASHBOARD_SNAPSHOT`` frame for the current ``dashboard.html``.

    Returns an explanatory Home page for unreadable or oversized files.
    ``session_id`` is stamped so the relay routes it to the right client, matching
    every other server→client frame. ``viewer`` is who the page is rendered for
    (see ``EVERYONE``); it is keyword-only with no default so no socket path can
    forget it and fall back to showing everyone's turns.
    """
    path = dashboard_path()
    if not path.exists():
        if _agent_metadata is None:
            # ensure_dashboard has not run, so there is nothing to render *about*.
            # An embedder that never starts a host gets no Home, as before.
            return None
        # No file means "not customised", not "no Home": render the starter.
        html = render_starter(_agent_metadata, viewer=viewer)
        frame = {"type": "DASHBOARD_SNAPSHOT", "html": html}
        if session_id:
            frame["session_id"] = session_id
        return frame
    try:
        size = path.stat().st_size
    except OSError as e:
        return dashboard_error(f"Could not inspect dashboard.html: {e}", session_id)
    if size > MAX_DASHBOARD_BYTES:
        return dashboard_error(
            f"dashboard.html is {size:,} bytes; the limit is {MAX_DASHBOARD_BYTES:,} bytes (128 MiB).",
            session_id)
    try:
        html = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # The file is agent-authored: it can be a directory, a broken symlink, or
        # binary. Any of those means "no Home", and the operator should hear why.
        return dashboard_error(f"Could not read dashboard.html: {e}", session_id)
    frame = {"type": "DASHBOARD_SNAPSHOT", "html": html}
    if session_id:
        frame["session_id"] = session_id
    # JSON escaping and sealed-frame base64 can exceed the HTML byte count.
    # Reserve a small envelope for session/counter fields and encryption tags.
    wire_bytes = len(json.dumps(frame, ensure_ascii=False).encode('utf-8'))
    if ((wire_bytes + 16 + 2) // 3) * 4 + 65536 > MAX_WEBSOCKET_MESSAGE_BYTES:
        return dashboard_error("Dashboard exceeds the 256 MiB transport envelope after encoding.", session_id)
    return frame


async def send_dashboard(send_msg, session_id, conn, force=False):
    """Push a ``DASHBOARD_SNAPSHOT`` unless this connection already has the current file.

    ``conn`` is the per-socket state dict, so a freshly connected client always gets
    its snapshot (nothing recorded yet) while a run that didn't touch the dashboard
    doesn't re-ship the whole page. ``force=True`` always sends.

    ``conn`` is also who the page is for: its verified ``agent_address`` and
    ``is_admin`` decide which activity the starter shows (see ``EVERYONE``).

    The read runs in a worker thread — it's file I/O on the event loop otherwise.
    """
    try:
        stat = dashboard_path().stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        # No file: the starter is rendered from metadata fixed at startup, so it
        # cannot change within a run. One stamp for the whole run means each
        # client is sent it once, like any other unchanged page.
        stamp = ("starter", None)
    if not force and conn.get("dashboard_stamp") == stamp:
        return

    viewer = viewer_for(conn.get("agent_address"), conn.get("is_admin"))
    frame = await asyncio.to_thread(read_dashboard_snapshot, session_id, viewer=viewer)
    if not frame:
        return
    await send_msg(frame)
    conn["dashboard_stamp"] = stamp


def ensure_dashboard(agent_metadata, project_dir=None):
    """Anchor the project directory, and remember what to render a Home from.

    Called once at host startup. **No file is written.** An agent that has not
    written its own Home gets the bundled starter, rendered fresh on every read.

    This used to write ``dashboard.html`` on first boot and then never touch it
    again, which sounds harmless and is not: the file froze whatever the starter
    looked like the first time that agent ever started, and no later improvement
    to the starter could reach it. Every agent's Home was a fossil of the version
    that happened to be installed on its first day, and the only way to see a
    change was to delete the file and remember why.

    An agent that wants its own Home still writes ``.co/dashboard.html``; from
    that moment the file wins and nothing here overwrites it. The difference is
    that not having one is now a state rather than a one-time event.
    """
    global _project_dir, _agent_metadata
    _project_dir = Path(project_dir) if project_dir else project_root()
    _agent_metadata = agent_metadata or {}


def published_skills(skills):
    """The skills the starter dashboard may offer as one-click actions.

    Only published (project-tree) skills qualify. A client validates every button
    against the agent's published profile, which carries exactly these — so a button
    for a user or builtin skill would render and then silently refuse to run.
    """
    from ....useful_plugins.skills import PUBLISHED_SKILL_LOCATIONS
    return [s for s in skills if s.get("location") in PUBLISHED_SKILL_LOCATIONS]


# A flat list stays readable to about a dozen rows in a 440px pane. Past that,
# show the first PREVIEW_ROWS and fold the rest behind one control.
FLAT_MAX = 12

# Eight, because the fold decides it rather than the content. A row is 56px plus
# a 2px gap; the header block is ~135px and the disclosure ~44px, so 135 + 8x58 +
# 44 lands the "more" control itself above the fold of a 440x800 pane. At nine
# rows the escape hatch sits below the fold — something you must scroll to
# discover, which is the problem it exists to solve.
#
# The gap to FLAT_MAX is deliberate: a fold can never hold fewer than four items,
# so the page never offers "1 more skill" behind a click.
PREVIEW_ROWS = 8


def _parse_starter(path):
    """``(page, fragments)`` from a starter file.

    The file is a complete page, then a ``<!--FRAGMENTS`` marker, then the repeated
    pieces as ``<template id="...">`` tags. Splitting on the marker rather than on
    the tags means the authoring notes below it never reach an agent's
    dashboard.html — and that anything written there is free to mention ``$`` or a
    template tag without being substituted or half-stripped into the output.

    ``string.Template`` rather than ``str.format``: the page is mostly CSS, and every
    rule in it is a pair of braces that ``format`` would read as a field.
    """
    raw = path.read_text(encoding="utf-8")
    page, _, scaffolding = raw.partition("<!--FRAGMENTS")
    found = re.findall(r'<template id="([^"]+)">(.*?)</template>', scaffolding, re.DOTALL)
    return Template(page.rstrip() + "\n"), {name: Template(body) for name, body in found}


# maxsize=1 caches the parse for the process; tests that swap the override call
# _starter_templates.cache_clear().
@lru_cache(maxsize=1)
def _starter_templates():
    """The starter to render from — the bundled one, or the operator's.

    ``~/.co/starter.html`` replaces it when present, so "all my agents start from my
    styling" needs no per-project copy. It replaces the *template*, not the page:
    every agent still renders its own name and its own skills, which a shared
    finished page could not do — the client validates each button against that
    agent's published skills, so someone else's Home renders as dead buttons.

    An override only has to carry the parts it wants to change. Its fragments are
    layered over the bundled ones, so restyling the page shell — the common case —
    does not mean copying the skill row and the group markup along with it, or
    silently losing them.
    """
    page, fragments = _parse_starter(Path(__file__).parent / "starter.html")
    if STARTER_OVERRIDE.is_file():
        override_page, override_fragments = _parse_starter(STARTER_OVERRIDE)
        page, fragments = override_page, {**fragments, **override_fragments}
    return page, fragments


# What an author writes when they have nothing to say. Rendered literally it is
# a line of body text whose content is an apology. An empty description already
# collapses; these should too.
_NON_DESCRIPTIONS = {"no description", "none", "n/a", "-", "todo"}


def first_sentence(text, limit=None):
    """The human-facing part of a description.

    Skill descriptions are written for a model: a sentence of purpose followed by
    paragraphs of instruction. Only the first sentence belongs on a Home page.
    Clamping by pixels instead gave every row a different height and every
    description a mid-word ellipsis — "Use only for…", "verify exact…" — which is
    noise exactly where the page most needs to be read.
    """
    text = " ".join(str(text or "").split())
    if text.lower() in _NON_DESCRIPTIONS:
        return ""
    head = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    if limit is None or len(head) <= limit:
        return head
    return head[:limit].rsplit(" ", 1)[0] + "…"


def _skill_row(skill):
    """One skill as a button: its real name, and what it does underneath.

    The name is shown verbatim — it is what you type (``/lark-base``), and
    title-casing it turns ``nano-banana-us`` into "Nano Banana Us", which names
    nothing. The description is what makes a list of 115 names usable at all.
    """
    _, fragments = _starter_templates()
    return fragments["skill"].substitute(
        name=escape(str(skill.get("name", "")), quote=True),
        description=escape(first_sentence(skill.get("description"))),
    ).strip()


def _skill_sections(skills):
    """The body of the starter dashboard: every published skill, reachable.

    One alphabetical list. Past ``FLAT_MAX`` the first ``PREVIEW_ROWS`` are shown
    and the rest sit behind a single disclosure.

    This used to group by the prefix in the names — lark-*, stripe-* — an
    inferred taxonomy built on a naming coincidence, and it was paid for at full
    structural price: fifteen skills rendered as four group headers, three
    visible rows, and a bucket called "other" holding the skills that belonged to
    no family, sorted last. The page showed a fifth of its content and spent four
    rows describing drawers.

    Sorting alphabetically clusters those families anyway — ``lark-base`` and
    ``lark-doc`` land next to each other with no header, no bucket and nothing
    hidden. The taxonomy bought a label nobody needed and cost twelve skills of
    visibility.
    """
    _, fragments = _starter_templates()
    if not skills:
        return "  " + fragments["empty"].template.strip()

    ordered = sorted(skills, key=lambda s: s["name"])

    def rows(members, indent):
        return "\n".join(indent + _skill_row(s) for s in members)

    if len(ordered) <= FLAT_MAX:
        return "  " + fragments["list"].substitute(rows=rows(ordered, "    ")).strip()

    head, tail = ordered[:PREVIEW_ROWS], ordered[PREVIEW_ROWS:]
    return ("  " + fragments["list"].substitute(rows=rows(head, "    ")).strip()
            + "\n  " + fragments["more"].substitute(
                count=len(tail),
                plural="s" if len(tail) != 1 else "",
                rows=rows(tail, "      "),
            ).strip())


def _quick_actions(skills):
    """Up to three real skills, prominent without inventing unsupported actions."""
    if not skills:
        return ""
    _, fragments = _starter_templates()
    rows = "\n".join("      " + _skill_row(skill) for skill in sorted(
        skills, key=lambda item: item["name"]
    )[:3])
    return "    " + fragments["quick"].safe_substitute(rows=rows).strip()


def _diagnostics(agent_metadata, skill_count):
    """Operator facts kept behind one disclosure, escaped and copyable."""
    _, fragments = _starter_templates()
    facts = []
    for label, value, class_name in (
        ("Model", agent_metadata.get("model"), ""),
        ("Trust", agent_metadata.get("trust"), ""),
        ("Tools", len(agent_metadata.get("tools") or []), ""),
        ("Skills", skill_count, ""),
        ("Address", agent_metadata.get("address"), "addr"),
    ):
        if value in (None, "", 0):
            continue
        facts.append(fragments["diag"].safe_substitute(
            label=escape(str(label)), value=escape(str(value)), **{"class": class_name}
        ).strip())
    if not facts:
        return ""
    rows = "\n".join("      " + item for item in facts)
    return "    " + fragments["diagnostics"].safe_substitute(rows=rows).strip()


def _subtitle(agent_metadata, skill_count):
    """Model, skills, tools — the three facts that say what this agent can do.

    Each part is dropped when it is unknown rather than printed as "0 tools", which
    reads as a broken agent instead of an unreported number.
    """
    parts = []
    if skill_count:
        parts.append(f"{skill_count} skill{'s' if skill_count != 1 else ''}")
    tools = agent_metadata.get("tools") or []
    if tools:
        parts.append(f"{len(tools)} tool{'s' if len(tools) != 1 else ''}")
    # Last, and only after what the agent can do: which model runs it is the least
    # interesting true thing on the page, and it used to lead.
    if agent_metadata.get("model"):
        parts.append(escape(str(agent_metadata["model"])))
    if agent_metadata.get("trust"):
        # Who this agent will talk to. The operator set it in code and cannot
        # otherwise see what the running agent actually resolved it to.
        parts.append(f"trust: {escape(str(agent_metadata['trust']))}")
    return " · ".join(parts)


def _address_line(agent_metadata):
    """The agent's address, in full, or nothing.

    In full because a truncated address is decoration: a deployed agent's address
    cannot be known before its first boot (#396), so learning it today means
    opening an ssh session and reading the logs. Half of it does not save that
    trip. It wraps rather than shrinks, so it stays selectable in a 440px pane.
    """
    address = agent_metadata.get("address")
    if not address:
        return ""
    return '<p class="addr">' + escape(str(address)) + '</p>'


def render_starter(agent_metadata, viewer=EVERYONE):
    """Build the day-zero dashboard HTML: who this agent is, and every skill it
    publishes as a one-click action.

    Written once, then owned by the agent — so it has to be worth keeping, and it
    has to hold up at both ends of the range. The pane it renders into is ~440px
    wide (oo-chat's Home column), full-width on mobile, and occasionally a whole
    browser window, which is why the layout is a single centred column with a
    max-width rather than anything that stretches.

    The markup and CSS live in ``starter/*.html`` — this function only decides what
    goes in them. Design notes are in those files, next to the rules they explain.
    """
    skills = published_skills(agent_metadata.get("skills") or [])
    page, _ = _starter_templates()
    name = str(agent_metadata.get("name") or "Agent")
    return page.safe_substitute(
        name=escape(name),
        initial=escape(name.strip()[:1] or "A"),
        tagline=_tagline(agent_metadata),
        subtitle=_subtitle(agent_metadata, len(skills)),
        # Compatibility for operator starter overrides written before Control
        # Center. The bundled template uses diagnostics; old templates may
        # still contain $address.
        address=_address_line(agent_metadata),
        activity=_activity_sections(viewer),
        quick_actions=_quick_actions(skills),
        capability_count=(f"{len(skills)} skill{'s' if len(skills) != 1 else ''}"
                          if skills else "None published"),
        diagnostics=_diagnostics(agent_metadata, len(skills)),
        body=_skill_sections(skills),
    )


def _tagline(agent_metadata):
    """One sentence saying what this agent is for, or nothing.

    Only an operator-written summary. The host also derives one from the first
    1000 characters of the system prompt, and that is prompt text rather than a
    description: rendering it put "# Agent You are an autonomous agent working on
    someone's behalf." at the top of the page, in the second person, addressed to
    the agent instead of to the person reading it. Better to say nothing.
    """
    return escape(first_sentence(agent_metadata.get("tagline"), limit=140))


# ---------------------------------------------------------------- activity

MAX_ACTIVITY_ROWS = 5


def _co():
    """The .co directory this agent renders from."""
    from pathlib import Path as _P
    root = _project_dir or project_root()
    return _P(root) / ".co"


def _ago(seconds):
    """Coarse on purpose. "3h ago" is what the question deserves; a timestamp
    makes the reader do subtraction to answer "is this thing still alive"."""
    if seconds < 60:
        return "just now"
    for size, unit in ((3600, "m"), (86400, "h"), (float("inf"), "d")):
        if seconds < size:
            n = int(seconds // (60 if unit == "m" else 3600 if unit == "h" else 86400))
            return f"{n}{unit} ago"
    return "a while ago"


def _tail_lines(path, wanted, chunk=65536):
    """The last lines of an append-only file, newest first, read from the end.

    Bounded by the answer rather than by the history. A record here carries the
    turn's whole message list — 23 KB on a real agent, 85 KB at the top end — and
    nothing trims the file, so reading it whole to show five rows is a cost that
    grows forever and is paid on every turn (#526).

    The chunk size is a starting point, not a window: one record can be larger
    than it, so the walk continues until enough lines are found or the file is
    exhausted.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if not size:
        return []

    lines, buf, pos = [], b"", size
    with open(path, "rb") as f:
        while pos > 0 and len(lines) < wanted:
            step = min(chunk, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + buf
            parts = buf.split(b"\n")
            # The first part may be half a record; leave it for the next chunk,
            # unless we have reached the start of the file and it is whole.
            buf = parts[0] if pos > 0 else b""
            complete = parts[1:] if pos > 0 else parts
            lines = [c for c in complete if c.strip()] + lines
    return list(reversed(lines[-wanted:] if wanted else lines))


def _run_owner(rec):
    """The verified address that started this run -- session_owner, on a raw line."""
    session = rec.get("session")
    requester = session.get("requester") if isinstance(session, dict) else None
    return requester.get("address") if isinstance(requester, dict) else None


def recent_runs(limit=MAX_ACTIVITY_ROWS, owner=EVERYONE):
    """The last few turns, newest first, one entry per session.

    The log is append-only and a session appears twice — once as ``running``,
    again as ``done``. The later line wins, or the page would report every
    finished run as still in flight. Reading from the end means the later line
    is also the one seen first.

    ``owner`` keeps only the runs that address started. A run nobody owns
    (a schedule firing, a pre-#696 record) belongs to no visitor. The scan is
    still bounded by lines, so on a busy shared host a visitor may see fewer
    than ``limit`` of their own rows -- fewer rows, never someone else's.
    """
    import json as _json
    path = _co() / "session_results.jsonl"
    if not path.is_file():
        return []

    latest = {}
    # More lines than sessions wanted: each session writes at least twice, and a
    # torn line costs nothing but itself.
    for raw in _tail_lines(path, wanted=limit * 4):
        try:
            rec = _json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue          # a torn write must not cost the whole page
        if isinstance(rec, dict) and rec.get("session_id"):
            latest.setdefault(rec["session_id"], rec)   # newest first: first wins
        if len(latest) >= limit and owner is EVERYONE:
            break

    # Filtered after the newest-line-wins pick, so a session is judged by its
    # latest record, as session_owner does.
    runs = [r for r in latest.values()
            if owner is EVERYONE or (owner and _run_owner(r) == owner)]
    runs = sorted(runs, key=lambda r: r.get("created") or 0, reverse=True)
    return runs[:limit]


def scheduled_entries():
    """What this agent runs on its own, and how each last went.

    Reads the schedule module rather than reparsing the file, so the page and
    the scheduler cannot disagree about what an entry means.
    """
    try:
        from ..schedule import last_run, load_entries, load_state, running_entries

        _running = running_entries()
    except Exception:
        return [], []
    try:
        entries, problems = load_entries(_co(), report=True)
        state = load_state(_co())
    except Exception:
        return [], []
    out = []
    for e in entries:
        st = state.get(e.name) or {}
        when = last_run(state, e.name)
        out.append({
            "name": e.name,
            # An exec entry has no prompt, and a blank here is a scheduled
            # task that looks like it does nothing (#709).
            "run": e.run or e.exec,
            "cadence": f"every {_cadence(e)}" if e.interval else str(e.at or ""),
            "status": st.get("status"),
            "last_run": when,
            "running": e.name in _running,
            "reason": st.get("reason"),
        })
    return out, problems


def _why(reason, limit=60):
    """The first line of a failure that carries information, short enough to
    sit in a row.

    Not literally the first line. Providers format refusals as banners, and the
    real one this was built for opens with a row of equals signs:

        ======================================================================
        ❌ Insufficient ConnectOnion Credits
        ======================================================================

    The sentence a reader needs is the third line. Rendering line one turned
    the row into punctuation.

    Naming the failure is the job; the traceback belongs to the log, and the
    row already tells the reader which log to open and roughly when.
    """
    for line in str(reason).splitlines():
        line = line.strip()
        # A line with no letters or digits is decoration, not a message.
        if line and any(ch.isalnum() for ch in line):
            return line if len(line) <= limit else line[:limit - 1] + "…"
    return ""


def _cadence(entry):
    total = int(entry.interval.total_seconds())
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if total % size == 0 and total >= size:
            return f"{total // size}{unit}"
    return f"{total}s"



def _took(ms):
    """How long a turn took, in the unit a reader can hold.

    Seconds stop being readable at about a minute, and the runs this section
    exists for are the long ones — a full extraction pass is four minutes, and
    "243.0s" makes you do the division to find that out.
    """
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {rest}s" if rest else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def _collapse(runs, scheduled):
    """Label scheduled runs by their entry, and fold consecutive repeats.

    A schedule entry's prompt is one fixed sentence sent verbatim every firing,
    so an agent that checks something every fifteen minutes fills this section
    with the same row — and the rows that differ, the typed ones, are the first
    pushed out. What varies between firings is what each found, which is in the
    result, not the prompt (#528).

    Only *consecutive* repeats fold. A typed turn between two firings separates
    them, because it did.
    """
    by_run = {s["run"]: s["name"] for s in scheduled}
    folded = []
    for r in runs:
        label = by_run.get(r.get("prompt"))
        key = label or None
        if key and folded and folded[-1]["key"] == key:
            folded[-1]["count"] += 1
            continue
        # The fallback is a whole paragraph when the run came from a schedule
        # entry whose text has since been edited — it no longer matches any
        # entry, and a scheduled prompt is instructions, by design. Pasted in
        # with its newlines it renders as three lines inside a one-line row,
        # truncated mid-token (#546). Same rule as _why: the first line that
        # carries information. The whole prompt is still in the session record.
        folded.append({"key": key,
                       "label": label or _why(r.get("prompt") or "", limit=80),
                       "count": 1,
                       "run": r})
    return folded

def _activity_sections(viewer=EVERYONE):
    """Both sections, or nothing at all.

    A fresh agent has neither a schedule nor a history, and a box that is empty
    on every new agent is worse than no box — it is prime space on the first
    page anyone sees, spent saying nothing.
    """
    from datetime import datetime, timezone

    _, fragments = _starter_templates()
    section, row = fragments["activity"], fragments["act"]
    now = datetime.now(timezone.utc)
    out = []

    everyone = viewer is EVERYONE
    # The schedule is the operator's configuration; an entry's row can be its
    # prompt and its last failure reason. Only an admin is shown it.
    scheduled, problems = (scheduled_entries() if everyone or viewer["is_admin"]
                           else ([], []))
    if scheduled:
        rows = []
        for s in scheduled:
            if s.get("running"):
                # While a run is in flight record_run has not landed, so
                # last_run is the *previous* completion. Showing that for an
                # entry configured every 15m whose run takes longer reads as
                # eight minutes late when it is in fact working (#539).
                meta, tone = "running", "live"
            elif s["last_run"] is None:
                meta, tone = "not yet run", ""
            else:
                ago = _ago((now - s["last_run"]).total_seconds())
                # "done" is not said here. It means the turn returned, which is
                # all the scheduler can know — an agent that answered "I could
                # not reach the drive" returned just as successfully as one that
                # did the work. Rendering that as `done` made three consecutive
                # failures read as a healthy job (#535). "ran 2m ago" claims
                # only what happened.
                #
                # `failed` is different: the turn raised, and the scheduler
                # genuinely knows that.
                if s["status"] == "failed":
                    # The reason, when the scheduler caught one. A deployed
                    # agent's console is on a machine nobody is watching, so
                    # `failed` alone costs an ssh session to turn into
                    # "the account is out of credits" (#541).
                    meta = f"failed · {ago}"
                    if s.get("reason"):
                        meta += f" · {_why(s['reason'])}"
                    tone = "bad"
                else:
                    meta, tone = f"ran · {ago}", ""
            rows.append(row.safe_substitute(
                # The entry's name, not its run text: an entry can be called
                # "check for new contracts" while its instruction stays a
                # paragraph. Entry.name falls back to run when none is given.
                what=escape(f"{s['name']}  ({s['cadence']})"),
                meta=escape(meta), tone=tone).strip())
        out.append(section.safe_substitute(
            title="Scheduled", rows="\n".join("      " + r for r in rows)).strip())

    if problems:
        # A dropped entry renders as nothing, and so does a schedule that is
        # merely not due yet. Saying which line was thrown away is the whole
        # difference between the two.
        rows = [row.safe_substitute(what=escape(p), meta="ignored", tone="bad").strip()
                for p in problems]
        out.append(section.safe_substitute(
            title="Schedule problems",
            rows="\n".join("      " + r for r in rows)).strip())

    runs = recent_runs(owner=EVERYONE if everyone else viewer["address"])
    if runs:
        rows = []
        for item in _collapse(runs, scheduled):
            r = item["run"]          # the newest of a folded group
            status = r.get("status")
            if status == "running":
                meta, tone = "running", "live"
            elif status == "waiting_approval":
                # It stopped and asked. Saying "done" here invites nobody to answer.
                meta, tone = "waiting on you", "live"
            elif status == "interrupted":
                # Killed with its process — usually by a deploy. It may have
                # finished its work first; nothing recorded how far it got, and
                # "done" would claim it did. This is the same lie #536 took out
                # of the Scheduled row, arriving through the other door.
                meta, tone = "interrupted", "bad"
            else:
                ms = r.get("duration_ms")
                meta = _took(ms) if isinstance(ms, (int, float)) else "done"
                tone = ""
            created = r.get("created")
            if created:
                meta += " · " + _ago(now.timestamp() - float(created))
            what = item["label"][:80]
            if item["count"] > 1:
                what += f"  ×{item['count']}"
            rows.append(row.safe_substitute(
                what=escape(what), meta=escape(meta), tone=tone).strip())
        out.append(section.safe_substitute(
            title="Recent", rows="\n".join("      " + r for r in rows)).strip())

    return "\n".join(out)
