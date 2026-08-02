"""Dashboard delivery — push the agent's ``dashboard.html`` to the browser.

The browser can't read a file inside the agent's container, so the Host reads
``dashboard.html`` from the agent's project directory and sends it over the
already-authenticated WebSocket: once on connect, and again after each run. Kept
deliberately dead simple — no filesystem watcher, no hashing, no plugin.

The file is read off the event loop and capped at ``MAX_DASHBOARD_BYTES``: it is
agent-authored, so an oversized one must degrade to "no Home", never stall the
host or blow up a relay frame. The post-run push is skipped when the file hasn't
changed since this connection last saw it.
"""

import asyncio
import re
from html import escape
from pathlib import Path
from functools import lru_cache
from string import Template

from ....console import Console

DASHBOARD_FILE = "dashboard.html"
CO_DIR = ".co"
# An operator's own starting point for every agent they host. Optional; the bundled
# template is used when it isn't there.
STARTER_OVERRIDE = Path.home() / CO_DIR / "starter.html"

# Generous on purpose: the client's CSP allows images only as `data:` URIs, so the one
# way to put a chart or logo on a dashboard is to inline it, and base64 adds ~33%. A
# single 400KB screenshot lands near 530KB before any markup — a tighter cap would
# reject pages the format actively pushes authors toward.
#
# The ceiling this has to stay under is the relay's: uvicorn accepts WebSocket messages
# up to 16MB by default, and the snapshot crosses it as one frame (plus JSON escaping,
# which adds a few percent). 2MB keeps ~8x headroom while still catching a runaway file
# — a log accidentally named dashboard.html, or an agent dumping a dataset into it.
MAX_DASHBOARD_BYTES = 2 * 1024 * 1024

# The project directory, resolved once at host startup. Resolving it per read would
# follow any later os.chdir (a tool, a plugin) and start serving whatever file
# happened to be in the new directory.
_project_dir = None

# What to render when the agent has not written a Home page of its own. Set once
# at host startup, for the same reason as _project_dir.
_agent_metadata = None


def project_root(start=None):
    """The directory that owns ``.co/`` — the project, not wherever you ran from.

    Walks up from ``start``. Everything else the agent is made of is found this way
    (``.co/skills``, ``.co/host.yaml``), and the Home page had no such notion: it
    resolved against the bare cwd, so running the agent from a subdirectory created
    a second dashboard.html there and served that one instead.

    Falls back to ``start`` when there is no ``.co/`` above it — an agent hosted
    outside a project still gets a Home, it just lives where it was started.
    """
    start = Path(start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        if (directory / CO_DIR).is_dir():
            return directory
    return start


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


def read_dashboard_snapshot(session_id=None):
    """Build a ``DASHBOARD_SNAPSHOT`` frame for the current ``dashboard.html``.

    Returns ``None`` when the file is missing, unreadable, or larger than
    ``MAX_DASHBOARD_BYTES`` — agents without a usable dashboard are unaffected.
    ``session_id`` is stamped so the relay routes it to the right client, matching
    every other server→client frame.
    """
    path = dashboard_path()
    if not path.exists():
        if _agent_metadata is None:
            # ensure_dashboard has not run, so there is nothing to render *about*.
            # An embedder that never starts a host gets no Home, as before.
            return None
        # No file means "not customised", not "no Home": render the starter.
        html = render_starter(_agent_metadata)
        frame = {"type": "DASHBOARD_SNAPSHOT", "html": html}
        if session_id:
            frame["session_id"] = session_id
        return frame
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_DASHBOARD_BYTES:
        Console().print(
            f"[yellow]{DASHBOARD_FILE} is {size / 1_048_576:.1f}MB (limit "
            f"{MAX_DASHBOARD_BYTES // 1_048_576}MB) — not sending it to clients. "
            f"Inline images are the usual cause; compress them before embedding.[/yellow]"
        )
        return None
    try:
        html = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # The file is agent-authored: it can be a directory, a broken symlink, or
        # binary. Any of those means "no Home", and the operator should hear why.
        Console().print(f"[yellow]Could not read {path}: {e}[/yellow]")
        return None
    frame = {"type": "DASHBOARD_SNAPSHOT", "html": html}
    if session_id:
        frame["session_id"] = session_id
    return frame


async def send_dashboard(send_msg, session_id, conn=None):
    """Push a ``DASHBOARD_SNAPSHOT`` unless this connection already has the current file.

    ``conn`` is the per-socket state dict, so a freshly connected client always gets
    its snapshot (nothing recorded yet) while a run that didn't touch the dashboard
    doesn't re-ship the whole page. Pass ``conn=None`` to always send.

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
    if conn is not None and conn.get("dashboard_stamp") == stamp:
        return

    frame = await asyncio.to_thread(read_dashboard_snapshot, session_id)
    if not frame:
        return
    if conn is not None:
        conn["dashboard_stamp"] = stamp
    await send_msg(frame)


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


def render_starter(agent_metadata):
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
        address=_address_line(agent_metadata),
        activity=_activity_sections(),
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


def recent_runs(limit=MAX_ACTIVITY_ROWS):
    """The last few turns, newest first, one entry per session.

    The log is append-only and a session appears twice — once as ``running``,
    again as ``done``. The later line wins, or the page would report every
    finished run as still in flight. Reading from the end means the later line
    is also the one seen first.
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
        if len(latest) >= limit:
            break

    runs = sorted(latest.values(), key=lambda r: r.get("created") or 0, reverse=True)
    return runs[:limit]


def scheduled_entries():
    """What this agent runs on its own, and how each last went.

    Reads the schedule module rather than reparsing the file, so the page and
    the scheduler cannot disagree about what an entry means.
    """
    try:
        from ..schedule import load_entries, load_state, last_run
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
            "run": e.run,
            "cadence": f"every {_cadence(e)}" if e.interval else str(e.at or ""),
            "status": st.get("status"),
            "last_run": when,
        })
    return out, problems


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
        folded.append({"key": key,
                       "label": label or str(r.get("prompt") or ""),
                       "count": 1,
                       "run": r})
    return folded

def _activity_sections():
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

    scheduled, problems = scheduled_entries()
    if scheduled:
        rows = []
        for s in scheduled:
            if s["last_run"] is None:
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
                    meta, tone = f"failed · {ago}", "bad"
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

    runs = recent_runs()
    if runs:
        rows = []
        for item in _collapse(runs, scheduled):
            r = item["run"]          # the newest of a folded group
            if r.get("status") == "running":
                meta, tone = "running", "live"
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
