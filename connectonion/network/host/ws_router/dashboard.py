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


# A flat list stays readable to about a dozen rows in a 440px pane. Past that it is
# a wall, and the honest structure to impose is the one already in the names: skills
# ship in families (lark-base, lark-doc, lark-sheets; vercel:deploy, vercel:env), and
# an author who names three things alike has told you they belong together.
FLAT_MAX = 12
FAMILY_MIN = 3


def group_skills(skills):
    """Split skills into ``(families, loose)`` by the prefix in their names.

    A family is a prefix with at least ``FAMILY_MIN`` members, so two lark-* skills
    stay in the open rather than hiding behind a group of two. Both halves come back
    sorted: a Home page that reorders itself between runs is one you have to re-read
    every time.
    """
    families = {}
    for s in skills:
        families.setdefault(re.split(r"[-:]", s["name"], 1)[0], []).append(s)

    grouped = sorted(
        (prefix, sorted(members, key=lambda s: s["name"]))
        for prefix, members in families.items()
        if len(members) >= FAMILY_MIN
    )
    loose = sorted(
        (s for members in families.values() if len(members) < FAMILY_MIN for s in members),
        key=lambda s: s["name"],
    )
    return grouped, loose


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


def _skill_row(skill):
    """One skill as a button: its real name, and what it does underneath.

    The name is shown verbatim — it is what you type (``/lark-base``), and
    title-casing it turns ``nano-banana-us`` into "Nano Banana Us", which names
    nothing. The description is what makes a list of 115 names usable at all.
    """
    _, fragments = _starter_templates()
    return fragments["skill"].substitute(
        name=escape(str(skill.get("name", "")), quote=True),
        description=escape(str(skill.get("description") or "").strip()),
    ).strip()


def _skill_sections(skills):
    """The body of the starter dashboard: every published skill, reachable.

    Three shapes, because "a few skills" and "a hundred skills" are different pages:
    nothing at all gets a note saying so; a short list is shown flat, because
    collapsing six items hides them behind a click for no reason; a long one is
    grouped, with the first family open so the page opens on something to click
    rather than a row of shut drawers.
    """
    _, fragments = _starter_templates()
    if not skills:
        return "  " + fragments["empty"].template.strip()

    def rows(members, indent):
        return "\n".join(indent + _skill_row(s) for s in members)

    if len(skills) <= FLAT_MAX:
        listing = fragments["list"].substitute(
            rows=rows(sorted(skills, key=lambda s: s["name"]), "      ")
        )
        return "  " + listing.strip()

    families, loose = group_skills(skills)
    if loose:
        families.append(("other", loose))

    group = fragments["group"]
    return "\n".join(
        "  " + group.substitute(
            open="open" if i == 0 else "",
            prefix=escape(prefix),
            count=len(members),
            rows=rows(members, "        "),
        ).strip()
        for i, (prefix, members) in enumerate(families)
    )


def _subtitle(agent_metadata, skill_count):
    """Model, skills, tools — the three facts that say what this agent can do.

    Each part is dropped when it is unknown rather than printed as "0 tools", which
    reads as a broken agent instead of an unreported number.
    """
    parts = []
    if agent_metadata.get("model"):
        parts.append(escape(str(agent_metadata["model"])))
    if skill_count:
        parts.append(f"{skill_count} skill{'s' if skill_count != 1 else ''}")
    tools = agent_metadata.get("tools") or []
    if tools:
        parts.append(f"{len(tools)} tool{'s' if len(tools) != 1 else ''}")
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
    return page.safe_substitute(
        name=escape(str(agent_metadata.get("name") or "Agent")),
        subtitle=_subtitle(agent_metadata, len(skills)),
        address=_address_line(agent_metadata),
        body=_skill_sections(skills),
    )
