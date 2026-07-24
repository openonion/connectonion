"""Dashboard delivery — push the agent's ``dashboard.html`` to the browser.

The browser can't read a file inside the agent's container, so the Host reads
``dashboard.html`` from the agent's working directory (cwd) and sends it over the
already-authenticated WebSocket: once on connect, and again after each run. Kept
deliberately dead simple — no filesystem watcher, no hashing, no plugin.
"""

from html import escape
from pathlib import Path

DASHBOARD_FILE = "dashboard.html"


def read_dashboard_snapshot(session_id=None):
    """Build a ``DASHBOARD_SNAPSHOT`` frame for the current ``dashboard.html``.

    Returns ``None`` when the file doesn't exist (agents without a dashboard are
    unaffected). ``session_id`` is stamped so the relay routes it to the right
    client, matching every other server→client frame.
    """
    path = Path(DASHBOARD_FILE)
    if not path.exists():
        return None
    frame = {"type": "DASHBOARD_SNAPSHOT", "html": path.read_text(encoding="utf-8")}
    if session_id:
        frame["session_id"] = session_id
    return frame


def ensure_dashboard(agent_metadata):
    """Write a starter ``dashboard.html`` into the cwd if the agent has none.

    Called once at host startup; a no-op when the file already exists (the agent
    owns it after that). Gives every agent a polished Home on day zero.
    """
    path = Path(DASHBOARD_FILE)
    if path.exists():
        return
    path.write_text(render_starter(agent_metadata), encoding="utf-8")


def render_starter(agent_metadata):
    """Build the day-zero dashboard HTML: an empty-first, visual-over-textual Home
    with the agent name and up to four of its skills as one-click actions."""
    name = escape(str(agent_metadata.get("name") or "Agent"))
    skills = agent_metadata.get("skills") or []
    featured = skills[:4]

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
