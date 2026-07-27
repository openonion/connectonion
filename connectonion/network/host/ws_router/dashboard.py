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
from html import escape
from pathlib import Path

from ....console import Console

DASHBOARD_FILE = "dashboard.html"

# A dashboard is a glanceable Home, not a data dump. Well past any hand-written or
# agent-written page, small enough that reading and framing it is never a problem.
MAX_DASHBOARD_BYTES = 512 * 1024

# Where dashboard.html lives, captured at host startup. Resolving cwd per read
# would follow any later os.chdir (a tool, a plugin) and start serving whatever
# file happened to be in the new directory.
_project_dir = None


def dashboard_path():
    """Path to ``dashboard.html`` in the agent's project directory."""
    return (_project_dir or Path.cwd()) / DASHBOARD_FILE


def read_dashboard_snapshot(session_id=None):
    """Build a ``DASHBOARD_SNAPSHOT`` frame for the current ``dashboard.html``.

    Returns ``None`` when the file is missing, unreadable, or larger than
    ``MAX_DASHBOARD_BYTES`` — agents without a usable dashboard are unaffected.
    ``session_id`` is stamped so the relay routes it to the right client, matching
    every other server→client frame.
    """
    path = dashboard_path()
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_DASHBOARD_BYTES:
        Console().print(
            f"[yellow]{DASHBOARD_FILE} is {size // 1024}KB (limit "
            f"{MAX_DASHBOARD_BYTES // 1024}KB) — not sending it to clients.[/yellow]"
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
    except OSError:
        return
    stamp = (stat.st_mtime_ns, stat.st_size)
    if conn is not None and conn.get("dashboard_stamp") == stamp:
        return

    frame = await asyncio.to_thread(read_dashboard_snapshot, session_id)
    if not frame:
        return
    if conn is not None:
        conn["dashboard_stamp"] = stamp
    await send_msg(frame)


def ensure_dashboard(agent_metadata, project_dir=None):
    """Write a starter ``dashboard.html`` if the agent has none, and anchor the
    directory every later read resolves against.

    Called once at host startup; a no-op when the file already exists (the agent
    owns it after that). Gives every agent a polished Home on day zero.
    """
    global _project_dir
    _project_dir = Path(project_dir) if project_dir else Path.cwd()

    path = dashboard_path()
    if path.exists():
        return
    try:
        path.write_text(render_starter(agent_metadata), encoding="utf-8")
    except OSError as e:
        # A read-only or missing project dir is a fine reason to have no dashboard;
        # it is not a reason to refuse to start the host. Say so and move on.
        Console().print(f"[yellow]Could not write {path}: {e}[/yellow]")
        return
    Console().print(f"[dim]Created {DASHBOARD_FILE} — your agent's Home page.[/dim]")


def featured_skills(skills, limit=4):
    """Pick the skills the starter dashboard offers as one-click actions.

    Only published (project-tree) skills qualify. A client validates every button
    against the agent's published profile, which carries exactly these — so a button
    for a user or builtin skill would render and then silently refuse to run.
    """
    from ....useful_plugins.skills import PUBLISHED_SKILL_LOCATIONS
    return [s for s in skills if s.get("location") in PUBLISHED_SKILL_LOCATIONS][:limit]


def render_starter(agent_metadata):
    """Build the day-zero dashboard HTML: an empty-first, visual-over-textual Home
    with the agent name and up to four of its skills as one-click actions."""
    name = escape(str(agent_metadata.get("name") or "Agent"))
    featured = featured_skills(agent_metadata.get("skills") or [])

    if featured:
        buttons = "\n".join(
            f'      <button class="action" data-ochat-skill="{escape(s["name"], quote=True)}">'
            f'{escape(s["name"].replace("-", " ").replace("_", " ").title())}</button>'
            for s in featured
        )
        actions = f'    <section class="card">\n      <h2>Quick actions</h2>\n{buttons}\n    </section>'
    else:
        actions = (
            '    <section class="card empty">\n'
            '      <h2>Quick actions</h2>\n'
            '      <p>Add skills to your agent and they show up here as one-click actions.</p>\n'
            '    </section>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    background: #fafafa; color: #171717; padding: 40px 28px; line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}
  header {{ margin-bottom: 28px; }}
  h1 {{ font-size: 28px; font-weight: 650; letter-spacing: -0.02em; }}
  .sub {{ color: #737373; font-size: 14px; margin-top: 4px; }}
  .card {{
    background: #fff; border: 1px solid #e5e5e5; border-radius: 12px;
    padding: 22px 24px; margin-bottom: 16px;
  }}
  .card h2 {{
    font-size: 12px; font-weight: 650; letter-spacing: 0.08em; text-transform: uppercase;
    color: #a3a3a3; margin-bottom: 14px;
  }}
  .action {{
    display: block; width: 100%; text-align: left; font: inherit; font-size: 15px; font-weight: 550;
    padding: 14px 16px; margin-bottom: 8px; cursor: pointer;
    background: #fff; color: #171717; border: 1px solid #d4d4d4; border-radius: 8px;
    transition: border-color .15s, transform .15s;
  }}
  .action:last-child {{ margin-bottom: 0; }}
  .action:hover {{ border-color: #16a34a; transform: translateY(-1px); }}
  .empty p {{ color: #a3a3a3; font-size: 14px; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #121212; color: #ededed; }}
    .sub {{ color: #a3a3a3; }}
    .card {{ background: #1b1b1b; border-color: #2e2e2e; }}
    .action {{ background: #1b1b1b; color: #ededed; border-color: #3f3f3f; }}
    .action:hover {{ border-color: #1eae54; }}
  }}
</style>
</head>
<body>
  <header>
    <h1>{name}</h1>
    <p class="sub">Home</p>
  </header>
{actions}
</body>
</html>
"""
