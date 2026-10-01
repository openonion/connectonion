"""The reader's design contract that holds without a browser.

Both themes must define every colour token: a token missing from dark falls
back to the light value and paints a light patch on a dark page. The page is
opened from file:// with a person's private notes in it, so it never names a
remote host. The People table's mail columns come from one adapter (#2064).
"""

import json
import re
from datetime import datetime, timezone

from connectonion.rem.reader import TEMPLATE, mail_facts, snapshot


def _blocks(css: str) -> dict:
    light = re.search(r":root \{(.*?)\n  \}", css, re.S).group(1)
    media = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\}', css, re.S).group(1)
    forced = re.search(r':root\[data-theme="dark"\] \{(.*?)\}', css, re.S).group(1)
    tokens = lambda block: set(re.findall(r"(--[\w-]+):", block))  # noqa: E731
    return {"light": tokens(light), "dark-auto": tokens(media), "dark-forced": tokens(forced)}


def test_both_themes_define_every_colour_token():
    blocks = _blocks(TEMPLATE.read_text(encoding="utf-8"))
    faces = {"--display", "--text", "--ui", "--mono"}
    colours = blocks["light"] - faces
    assert len(colours) >= 20
    assert blocks["dark-auto"] == colours
    assert blocks["dark-forced"] == colours


def test_the_template_names_no_remote_host_and_loads_no_font():
    page = TEMPLATE.read_text(encoding="utf-8")
    assert not re.search(r"https?://(?!www\.)[a-z0-9.-]+\.[a-z]{2,}", page)
    assert "@font-face" not in page and "@import" not in page and "<link" not in page


def test_mail_facts_sum_a_person_seen_under_two_addresses(tmp_path):
    state = tmp_path / ".state"
    state.mkdir()
    (state / "map.json").write_text(json.dumps({"people": [
        {"address": "a@x.example", "record": "people/a.md", "mails": 5, "sent": 2, "received": 3, "first": "2026-08-02", "last": "2026-09-01"},
        {"address": "a@y.example", "record": "people/a.md", "mails": 4, "sent": 1, "received": 3, "first": "2026-07-09", "last": "2026-09-20"},
        {"record": "people/owner.md"}]}))
    assert mail_facts(tmp_path) == {"people/a.md": {"mails": 9, "sent": 3, "received": 6, "first": "2026-07-09", "last": "2026-09-20"}}


def test_the_fixture_notebook_snapshot_carries_what_the_views_draw(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
    from rem_reader_notebook import build
    data = snapshot(build(tmp_path / "rem", datetime.now(timezone.utc)))
    mara = next(r for r in data["records"] if r["path"] == "people/mara-ostrowski.md")
    assert mara["mail"]["mails"] == 59 and mara["written"]
    assert any("people/mara-ostrowski.md" in run.get("changed", []) for run in data["logs"])
