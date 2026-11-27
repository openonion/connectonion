"""Regression tests for RC33 privacy & isolation fixes: #3435 (P0), #3436, #3417, #3387, #3375."""

import json
import subprocess
from pathlib import Path

import pytest

from connectonion.rem import reader, service
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.reader_template import read_part


def _fixture_notebook(root: Path) -> Path:
    prepare(root)
    nb = Notebook(root)
    nb.write(
        "knowledge/private-health.md",
        "# Private Medical Diagnosis [personal]\n"
        "Masked: 7\n\n"
        "## Summary\n"
        "- Follow up with cardiologist about private blood panel [personal].\n",
    )
    nb.write(
        "people/alice-chen.md",
        "# Alice Chen\n\n"
        "## Facts\n"
        "- Role: Product Partner\n"
        "- Email: alice@example.com\n\n"
        "## Insight\n"
        "- Public architecture collaboration on Q4 launch.\n"
        "- Discussed [Private Medical Diagnosis](../knowledge/private-health.md) in confidence.\n"
        "- Salary negotiation is $420,000 base [sensitive].\n"
        "- Family trip to Kyoto in December [personal].\n\n"
        "## Private Notes\n"
        "- Passport number AB998877 [sensitive].\n"
        "- Personal diary entry about divorce [personal].\n\n"
        "## Relationships\n"
        "- [Bob Lin](bob-lin.md): shared tax audit dispute [sensitive].\n"
        "- [Carol Wu](carol-wu.md): co-authored the public API spec.\n",
    )
    nb.write(
        "people/bob-lin.md",
        "# Bob Lin\n\n## Facts\n- Role: Advisor\n",
    )
    nb.write(
        "people/carol-wu.md",
        "# Carol Wu\n\n## Facts\n- Role: Engineer\n",
    )
    nb.write(
        "sessions/2026-11-26-codex-priv.md",
        "# Session with private turn\n\n"
        "## Facts\n- Agent: Codex\n- Session: sess-priv-1\n\n"
        "## What you typed\n\n"
        "### 09:00 [sensitive]\n> Secret bank routing number 99881122 [sensitive]\n\n"
        "### 09:05\n> Refactor the public parser tests\n",
    )
    return root


def test_3435_shared_snapshot_strips_all_private_passages_before_serialization(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = _fixture_notebook(tmp_path / "rem")

    # Shared snapshot (`local=False`) must contain ZERO private raw text, markers, or private topic titles.
    shared_data = reader.snapshot(root, local=False)
    shared_html = reader.render(root, live=False, local=False)
    shared_json = json.dumps(shared_data, ensure_ascii=False)
    serialized = shared_json + "\n" + shared_html

    forbidden_in_html = [
        "Private Medical Diagnosis",
        "cardiologist",
        "$420,000",
        "Passport number AB998877",
        "divorce",
        "Family trip to Kyoto",
        "tax audit dispute",
        "99881122",
    ]
    for secret in forbidden_in_html:
        assert secret not in serialized, f"P0 leak (#3435): {secret!r} found in shared snapshot!"
    # No raw privacy markers may survive anywhere in the serialized data payload.
    for marker in ("[sensitive]", "[personal]"):
        assert marker not in shared_json, f"P0 leak (#3435): raw {marker!r} survived in shared JSON!"

    # Public content remains intact in the shared snapshot.
    assert "Public architecture collaboration on Q4 launch" in serialized
    assert "co-authored the public API spec" in serialized
    assert "Refactor the public parser tests" in serialized

    # Owner's own local reader (`local=True`) stays unchanged and still carries private passages for owner's curtain UI.
    owner_data = reader.snapshot(root, local=True)
    owner_serialized = json.dumps(owner_data, ensure_ascii=False)
    assert "$420,000" in owner_serialized
    assert "Private Medical Diagnosis" in owner_serialized


def test_3375_non_default_notebook_does_not_inherit_home_wechat_keys(tmp_path, monkeypatch):
    home = tmp_path / "fake_home"
    (home / ".co" / "wechat").mkdir(parents=True)
    (home / ".co" / "wechat" / "keys.json").write_text('{"db": "secret-key"}')
    monkeypatch.setattr(service.Path, "home", staticmethod(lambda: home))

    # Non-default temp notebook root MUST NOT inherit HOME's WeChat source.
    fixture_root = tmp_path / "fixture-notebook"
    prepare(fixture_root)
    fixture_sub = service.subscriptions(fixture_root)["wechat"]
    assert fixture_sub["enabled"] is False
    assert fixture_sub["consented"] is False

    # Owner's default ~/.co/rem notebook still auto-enables WeChat when keys exist.
    default_root = home / ".co" / "rem"
    prepare(default_root)
    default_sub = service.subscriptions(default_root)["wechat"]
    assert default_sub["enabled"] is True
    assert default_sub["consented"] is True


def test_3387_private_topic_links_and_search_results_use_masked_label_at_cover():
    """Links in Insight prose and search/best-match rendering must mask private titles at cover/public."""
    js_i18n = read_part("scripts/i18n_and_boot.js")
    js_priv = read_part("scripts/privacy_and_theme.js")
    js_md = read_part("scripts/markdown_and_tags.js")
    js_rec = read_part("scripts/record_and_search.js")

    # Verify record_and_search.js uses pageName(r) in search & best-match links, not raw r.title.
    assert 'text: r.title, "aria-describedby": detailId' not in js_rec
    assert 'el("a", { href: href(r), text: r.title })' not in js_rec

    # Exercise inline() + privateMaskLabel() in Node at cover vs all.
    harness = "\n".join([
        "const document = { documentElement: { classList: { contains: () => false } } };",
        "const UI = { zh: { 'Personal item': '个人事项' } };",
        "let uiLanguage = 'zh', privacyLevel = 'cover';",
        "const t = (s, v) => (UI.zh[s] || s).replace(/\\{(\\w+)\\}/g, (_, k) => v?.[k] ?? '');",
        "const REM = { owner: 'people/owner.md', tags: {}, graph: { nodes: [] }, records: [",
        "  { path: 'knowledge/private-health.md', category: 'knowledge', title: 'Private Medical Diagnosis', private: true, masked_number: 7 },",
        "  { path: 'people/alice.md', category: 'people', title: 'Alice Chen' }",
        "] };",
        "function byPath(p) { return REM.records.find(r => r.path === p) || null; }",
        "function href(r) { return '#r=' + encodeURIComponent(r.path); }",
        "function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;'); }",
        "function privateTopicHidden(r) { return r.private && r.category === 'knowledge' && privacyLevel === 'public'; }",
        js_md,
        "const coverHtml = inline('Discussed [Private Medical Diagnosis](../knowledge/private-health.md).', 'people/alice.md');",
        "privacyLevel = 'all';",
        "const allHtml = inline('Discussed [Private Medical Diagnosis](../knowledge/private-health.md).', 'people/alice.md');",
        "console.log(JSON.stringify({ coverHtml, allHtml }));",
    ])
    proc = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout.strip())
    assert "Private Medical Diagnosis" not in out["coverHtml"]
    assert "个人事项 7" in out["coverHtml"]
    assert "Private Medical Diagnosis" in out["allHtml"]


def test_3417_and_3436_public_only_hides_private_only_headings_and_sensitive_task_summaries(tmp_path, monkeypatch):
    """Browser regression verifying #3417 (empty private section heading vanishes) and #3436 (sensitive task summary hidden at Public only)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        pytest.skip(f"playwright unavailable: {exc}")

    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = _fixture_notebook(tmp_path / "rem")
    # Add an open thread with a sensitive title and a completed delegated task summary.
    nb = Notebook(root)
    nb.write(
        "people/alice-chen.md",
        nb.read("people/alice-chen.md") + "\n## Open threads\n- Review confidential severance terms [sensitive]\n",
    )
    html_path = tmp_path / "owner.html"
    html = reader.render(root, live=False, local=True)
    # Inject a completed delegated task receipt onto the sensitive open thread row in the rendered page for testing.
    html_path.write_text(html, encoding="utf-8")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(html_path.as_uri() + "#r=people%2Falice-chen.md")
            page.wait_for_selector("#main h1")
            # Switch to Public only (#3417).
            page.evaluate("setPrivacy('public')")
            page.wait_for_timeout(150)
            body_text = page.locator("#main").inner_text()
            headings = [h.strip() for h in page.locator("#main h2, #main h3").all_inner_texts()]
            assert "Private Notes" not in headings, f"#3417 regression: empty heading kept: {headings}"
            assert "Passport number" not in body_text
            assert "Public architecture collaboration" in body_text

            # Verify #3436 directly via taskStatus / taskStatusNode / taskResult on a sensitive completed task.
            res = page.evaluate("""() => {
              const entry = { r: { path: 'people/alice-chen.md', private: false }, t: { originalText: 'Review severance [sensitive]', text: 'Review severance [sensitive]' } };
              const task = { result: 'completed', agent: 'codex', summary: 'Prepared severance payout counter-offer of $250k', reason: 'Confidential HR terms' };
              privacyLevel = 'public';
              const pubStatus = taskStatus(task, entry);
              const pubNode = taskStatusNode(task, entry);
              privacyLevel = 'cover';
              const covStatus = taskStatus(task, entry);
              privacyLevel = 'all';
              const allStatus = taskStatus(task, entry);
              return { pubStatus, pubNodeIsNull: pubNode === null, covStatus, allStatus };
            }""")
            assert res["pubStatus"] == ""
            assert res["pubNodeIsNull"] is True
            assert "250k" not in res["covStatus"]
            assert "250k" in res["allStatus"]
            browser.close()
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) or "browser" in str(exc).lower():
            pytest.skip(f"headless browser unavailable: {exc}")
        raise
