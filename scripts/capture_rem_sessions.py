"""Render fictional coding sessions and capture desktop/phone evidence offline.

Run with Playwright installed: python scripts/capture_rem_sessions.py OUT_DIR
Nothing is read from the owner's coding-session archive.
"""

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectonion.rem.config import prepare  # noqa: E402
from connectonion.rem.reader import render  # noqa: E402


def example(agent: str, session_id: str, day: str, status: str = "") -> str:
    kind = "codex" if agent == "Codex" else "claude-code"
    return f"""# Give every conversation a place to return to

## Summary
A quieter reading room for coding sessions: familiar turns, a clear record of what was kept, and a way back into the work.

## Facts
- Date: {day}
- Agent: {agent}
- Project: [Lantern](../projects/lantern.md)
- Folder: /work/lantern
- Session: {session_id}
- Turns: 3
- Ended: {day} 10:24
- Status: {status}
- Outcome: done
- Tags: design, reader

## Artifacts
- Commands: 2 run; notable: `co rem status`; `git diff --stat`

## What you typed
### 09:12
> Let’s make the session reader feel like a place you can return to.
> Keep the conversation familiar, with a little room to breathe.

### 09:38
> Tool calls should stay out of the way until I need them.
> And make it just as comfortable on my phone.

### 10:02
> Keep the timestamps. When something wasn’t saved, say so.

## Final reply
> The conversation now lives inside its own window, with a phone frame on small screens.
>
> Your turns and the final reply are preserved. Archived commands open on demand, and missing activity is clearly labelled.
>
> Both colour themes have been checked at desktop and phone sizes. You can pick up the work using the resume command below.

## Sources
- {kind}:{session_id}:10
- {kind}:{session_id}:20
- {kind}:{session_id}:30
"""


def build(root: Path) -> None:
    prepare(root)
    (root / 'projects' / 'lantern.md').write_text('# Lantern\n\n## What it is\nA fictional reading room for useful work.\n')
    (root / 'sessions').mkdir(exist_ok=True)
    day = datetime.now(timezone.utc).date().isoformat()
    for name, agent, stamp, status in [('codex', 'Codex', day, ''), ('claude', 'Claude Code', day, ''),
                                        ('running', 'Codex', '2026-11-05', 'running')]:
        text = example(agent, f'fictional-{name}-session', stamp, status)
        if status:
            text = text.replace('- Outcome: done', '- Outcome: partial')
            text = text.partition('## Final reply')[0] + '## Sources\n- codex:fictional-running-session:10\n'
        (root / 'sessions' / f'{name}.md').write_text(text)


def capture(out: Path) -> None:
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / 'notebook'
        build(root)
        page_file = out / 'reader.html'
        page_file.write_text(render(root, local=True))
    with sync_playwright() as api:
        browser = api.chromium.launch(channel='chrome', headless=True)
        for size, width, height in [('desktop', 1440, 1100), ('phone', 390, 844)]:
            for theme in ['light', 'dark']:
                page = browser.new_page(viewport={'width': width, 'height': height}, color_scheme=theme)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('http*://**/*', lambda route: route.abort())
                for name, fragment in [('timeline', '#c=sessions'), ('codex', '#r=sessions%2Fcodex.md'),
                                        ('claude', '#r=sessions%2Fclaude.md')]:
                    page.goto(page_file.resolve().as_uri() + fragment)
                    page.locator('.session-row' if name == 'timeline' else '.session-device').first.wait_for()
                    assert not errors, errors
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (size, theme, name)
                    page.screenshot(path=str(out / f'{name}-{theme}-{size}.png'), full_page=True)
                    if name != 'timeline':
                        page.locator('.session-tool-call summary').first.click()
                        assert page.locator('.session-tool-call[open]').count() == 1
                        page.locator('.session-composer textarea').fill('Continue with keyboard navigation.')
                        assert page.locator('.session-composer').evaluate('(form) => form.sessionContinuation().message') == 'Continue with keyboard navigation.'
                        page.locator('.session-find input').fill('timestamps')
                        assert page.locator('.session-transcript mark').count() >= 1
                        page.goto(page_file.resolve().as_uri() + fragment + '&h=session-message-2')
                        assert page.locator('#session-message-2.session-cited').count() == 1
                page.close()
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    capture(parser.parse_args().out)
