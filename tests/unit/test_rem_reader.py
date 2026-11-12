"""The HTML reader is disposable presentation over the notebook, never a second store."""

import json
import os
import re
import shutil
import subprocess

import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.reader import TEMPLATE, contact_candidates, open_reader, reader_path, render, write_reader

HOSTILE = "# Alice\n\nSaid: <script>alert(1)</script> and </script><img src=x onerror=alert(2)>\n"


def _run_reader_js(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed; it runs the reader's JavaScript")
    privacy = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0)
                        for name in ["privatePassages", "unlabelled", "hasPrivacy"])
    privacy += "\n" + re.search(r"function privateTopicHidden\(.*?\}", TEMPLATE.read_text(), re.S).group(0)
    script = privacy + "\n" + script
    # stdin, not -e: Linux caps one argument at 128 KB and the template is larger.
    script = "const UI = {en: {}}; let uiLanguage = 'en';\n" + re.search(r"function t\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + re.search(r"function uiLocale\(.*?\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + script
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_source_sender_preserves_archived_display_names_and_normalizes_addresses():
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
                          for name in ['mailbox', 'sourceSender', 'sourceIdentity'])
    result = _run_reader_js(functions + r'''
      const REM = {}, byPath = () => null, personByAddress = () => null;
      console.log(JSON.stringify({
        identity: sourceIdentity({sender: 'Mara'}),
        quoted: mailbox('"Mara Ostrowski" <MARA@EXAMPLE.TEST>'),
        bare: mailbox('MARA@EXAMPLE.TEST'),
        path: sourceIdentity({sender: '/private/people/mara.md'})
      }));
    ''')
    assert result == {'identity': 'Mara',
                      'quoted': {'name': 'Mara Ostrowski', 'address': 'mara@example.test'},
                      'bare': {'name': 'mara', 'address': 'mara@example.test'}, 'path': ''}


@pytest.mark.parametrize('record', ['projects/harbour.md', 'orgs/fernhill-labs.md', 'people/mara-ostrowski.md'])
@pytest.mark.parametrize('language', ['en', 'zh'])
def test_round_nine_browser_fixture_retains_all_four_context_disclosures(tmp_path, monkeypatch, record, language):
    """Run the browser's exact fixture edit against the real citation projection."""
    import ast
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    from connectonion.rem.reader import snapshot

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    data = snapshot(build(tmp_path / 'rem', datetime(2026, 10, 1, 12, tzinfo=timezone.utc), zh=True))
    browser = TEMPLATE.parents[2] / 'tests/e2e/cli/test_rem_reader_design_browser.py'
    test = next(node for node in ast.parse(browser.read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == 'test_round_nine_full_purpose_and_quiet_record_disclosures')
    injection = next(node.value for node in ast.walk(test) if isinstance(node, ast.Constant)
                     and isinstance(node.value, str) and 'const r = byPath(path), links = []' in node.value)
    names = ['recordContext', 'connectedContext', 'relationDisclosure', 'dedupeRelationSnippets',
             'conversationFor', 'sourceList', 'sourceId', 'rawSection', 'listItems']
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js(functions + '\nUI.zh = ' + ui + ';\nconst REM = ' + json.dumps(data) + ';\n' + r'''
      const COMMENT = /<!--[\s\S]*?-->/g, UNKNOWN_TEXT = /^Unknown$/;
      const byPath = path => REM.records.find(r => r.path === path);
      const KNOWN = new Map(), FACTS = new Map(), render = () => {};
      const projectSessions = () => null, fmtDate = value => value;
      const localizedRelation = link => link, relationCard = () => ({tag: 'card'});
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: children.filter(Boolean),
        appendChild(node) {this.children.push(node)}});
    ''' + 'uiLanguage = ' + json.dumps(language) + ';\n'
        + 'const record = ' + json.dumps(record) + ';\n' + r'''
      for (const r of REM.records) {
        r.original = r.text;
        if (r.translations?.[uiLanguage]) { r.shown = uiLanguage; r.text = r.translations[uiLanguage]; }
      }
    ''' + '(' + injection + ')(record);\n' + r'''
      const context = recordContext(byPath(record)), classes = [];
      function visit(node) {
        if (!node || typeof node !== 'object') return;
        if (node.tag === 'details') classes.push(node.class);
        (node.children || []).forEach(visit);
      }
      visit(context);
      console.log(JSON.stringify({classes, conversations: Array.from({length: 6}, (_, i) =>
        conversationFor(byPath(record), 'pilot-conversation-' + i)?.messages.length)}));
    ''')
    assert result['conversations'] == [1] * 6
    assert len(result['classes']) == 4
    assert all('more-relations' in value for value in result['classes'])
    assert any('notebook-links' in value for value in result['classes'])
    assert any('mention-hints' in value for value in result['classes'])


@pytest.mark.parametrize('card', [
    'Business card handed over at the Lantern meetup — photo on 2026-11-01 <card> https://example.com/card',
    'Photo: Business `card*copy` handed over at Lantern',
])
def test_numbered_card_source_keeps_its_label_and_popup_text(card):
    page = TEMPLATE.read_text()
    names = ['sourceList', 'sourceId', 'rawSection', 'listItems', 'openEvidence']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = _run_reader_js(functions + 'const card = ' + json.dumps(card) + ';' + r'''
      const COMMENT = /<!--[\s\S]*?-->/g, UNKNOWN_TEXT = /^Unknown$/;
      const r = {text: '# Elara Finch\n\n## Sources\n1. ' + card + '\n'
        + '- [3] gmail:followup — 2026-11-02\n\n## Notes\n9. Not a source\n'};
      const sources = sourceList(r), REM = {}, evidenceLayout = () => {}, scrollEvidenceSpan = () => {};
      const evidenceLine = () => ({numbers: [], text: 'elara@example.com [1]'});
      const supportingSpan = () => null, markedSpan = text => text, chipLabel = () => 'source 1';
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children, focus() {}});
      const panel = {children: [], parentElement: {}, replaceChildren(...nodes) {this.children = nodes;},
        appendChild(node) {this.children.push(node);}};
      const evidencePanel = () => panel, closeEvidence = () => {}, document = {body: {classList: {add() {}}}};
      let evidenceTrigger;
      openEvidence(r, '1', {});
      console.log(JSON.stringify({sources, panel}));
    ''')
    assert result['sources'][0]['n'] == '1' and result['sources'][0]['text'] == card
    assert result['sources'][1] == {'n': '3', 'text': 'gmail:followup — 2026-11-02'}
    assert any(node.get('text') == card for node in result['panel']['children'])
    assert "The original isn't in this snapshot." not in json.dumps(result['panel'])
    assert not any(node.get('class') == 'private-hidden-notice' for node in result['panel']['children'])


def test_numbered_card_source_hover_shows_escaped_text_and_keeps_typed_context():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['citeChip', 'citationId', 'sourceId', 'esc'])
    result = _run_reader_js(functions + r'''
      const REM = {source_context: {'gmail:followup': {subject: 'Card follow-up'}}};
      const byPath = () => ({}), citationDate = () => 'source 1', chipLabel = () => 'Gmail';
      const citationSource = (r, n) => ({1: 'Photo: Business card <photo> & notes', 3: 'gmail:followup — 2026-11-02'})[n] || '';
      const sourceList = () => [{n: '1', plain: true}, {n: '3'}];
      console.log(JSON.stringify([citeChip('1', 'people/elara-finch.md'),
        citeChip('3', 'people/elara-finch.md'), citeChip('9', 'people/elara-finch.md')]));
    ''')
    assert 'title="Source: Photo: Business card &lt;photo&gt; &amp; notes"' in result[0]
    assert ' missing' not in result[0]
    assert 'subject “Card follow-up”' in result[1] and ' missing' not in result[1]
    assert 'original not in this snapshot' in result[2] and ' missing' in result[2]


def test_this_week_project_rows_strip_the_now_label():
    page = TEMPLATE.read_text(encoding="utf-8")
    parsing = page[page.index("const UNKNOWN_LINE ="):page.index("function mappedContact(")]
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["splitTrailers", "plainLine", "displayLine", "summaryLine"])
    week = page[page.index("  const week = weekChanges();"):page.index("  const recent = listedRecords()")] + "  main.appendChild(weekPages);\n"
    script = "\n".join([
        parsing, functions,
        'const youify = text => text;',
        'const translationPending = () => false; const el = (tag, attrs, children = []) => ({tag, ...attrs, children});',
        'const shortDate = day => day, moon = () => null, href = r => r.path;',
        'const singular = () => "project", sectionHead = text => ({text});',
        'let r; const weekChanges = () => [{r, day: "2026-10-16"}];',
        'const rows = [], main = {appendChild: node => rows.push(node)};',
        'const updatedMarker = () => null, firstBuild = () => false, translationNotice = () => null;',
        'for (const [i, line] of ["Now: waiting on review", "**Now:** waiting on review"].entries()) {',
        'r = {path: `projects/pilot-${i}.md`, title: "Pilot", category: "projects",',
        'text: "# Pilot\\n\\n## Insight\\n- " + line};',
        week, '}', 'console.log(JSON.stringify(rows));',
    ])
    rows = _run_reader_js(script)
    for details in rows:
        week_list = details["children"][1]
        summary = next(child["text"] for child in week_list["children"][0]["children"][2]["children"]
                       if child and child.get("class") == "s")
        assert summary == "waiting on review"


def test_empty_highlight_terms_finish_and_keep_literal_text():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['esc', 'highlight', 'sessionHighlight'])
    # Bound execution inside Node as well: a zero-width match used to grow forever.
    script = functions + r'''
      console.log(JSON.stringify([
        highlight('<pilot>', ''), sessionHighlight('<pilot>', ['']),
        sessionHighlight('<pilot>', ['', 'pilot']), highlight('pilot pilot', 'pilot')
      ]));
    '''
    result = _run_reader_js("require('node:vm').runInNewContext(" + json.dumps(script) +
                            ", {console}, {timeout: 1000});")
    assert result == ['&lt;pilot&gt;', '&lt;pilot&gt;', '&lt;<mark>pilot</mark>&gt;',
                      '<mark>pilot</mark> <mark>pilot</mark>']


@pytest.mark.parametrize('written', [False, True])
def test_first_build_keeps_failures_and_written_pages_visible(written):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['morningBrief', 'failureSummary'])
    result = _run_reader_js(functions + 'const written = ' + json.dumps(written) + ';' + r'''
      const REM = {owner: 'people/avery-lin.md'};
      const pass = {claims: [], changed: written ? [{path: 'people/mara-ostrowski.md'}] : [],
        failed: [{error: 'Failed to authenticate: 403 private payload'}, {error: 'TimeoutError'}]};
      const lastPass = () => pass, firstBuild = () => true, nightlyUpdatesOff = () => true;
      const known = () => ({status: 'Investigated'}), sectionHead = text => ({text});
      const inline = text => text, remCommand = text => text, commandChip = command => ({command});
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        appendChild(node) { this.children.push(node); }, append(...nodes) { this.children.push(...nodes); }});
      console.log(JSON.stringify(morningBrief()));
    ''')
    assert result['aria-label'] == 'First build'
    paragraphs = [node.get('text', '') for node in result['children']]
    assert any('2 investigations failed' in text and 'Model access was refused' in text
               and 'A request timed out' in text for text in paragraphs)
    assert any('Your notebook was just built' in text for text in paragraphs) is written
    assert any('No memory pages were written' in text for text in paragraphs) is not written
    assert 'private payload' not in json.dumps(result)
    assert result['children'][-1]['href'] == '#view=activity'
    assert not any(node.get('class') == 'translation-note' for node in result['children'])


def test_fact_list_omits_placeholder_only_fields_and_keeps_mail():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['factList', 'knownValue', 'plainLine'])
    result = _run_reader_js(functions + r'''
      const FACT_LABELS = {people: ['Phone', 'Role', 'Location']}, COPYABLE = new Set();
      const UNFILLED_LINE = /^Unknown — not verified\.?$/i, youify = text => text;
      const parseFacts = () => new Map([['Phone', [{value: 'Unknown'}]], ['Role', [{value: '—'}]],
        ['Location', [{value: 'Unknown — not verified.'}]]]);
      const legacyFact = () => [], mappedContact = () => false, softBreaks = node => node;
      const changedValue = node => node, factValue = item => ({text: item.value});
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        append(...nodes) { this.children.push(...nodes); }});
      const panel = (title, children) => ({title, children});
      const r = {category: 'people'}, empty = factList(r);
      r.mail = {mails: 3, received: 2, sent: 1};
      console.log(JSON.stringify({empty, withMail: factList(r)}));
    ''')
    assert result['empty'] is None
    mail_rows = result['withMail']['children'][1]['children']
    assert mail_rows[-2]['text'] == 'Mail'
    assert mail_rows[-1]['children'][0]['text'] == '3 · 2 in, 1 out'


def test_statement_capitalisation_preserves_code_and_paths():
    page = TEMPLATE.read_text(encoding="utf-8")
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["capFirst", "memoryStatement", "newestStanding", "plainLine", "listItems"])
    cases = [
        ("origin/main is ahead", "origin/main is ahead"),
        ("`co rem` runs nightly", "`co rem` runs nightly"),
        ("src/app.py fails", "src/app.py fails"),
        ("waiting on review", "Waiting on review"),
        ("iOS builds pass", "iOS builds pass"),
        ("camelCase stays", "camelCase stays"),
        *[(word + " is pending", word + " is pending")
          for word in [r"src\app", "app.py", "task_id", "a`b", "user@example.com", "ref:main", "issue#2", "v2"]],
        ("équipe ready", "Équipe ready"),
        ("", ""),
    ]
    script = "\n".join([
        functions, 'const REM = {owner: "people/owner.md"}, youify = text => text;',
        'const known = r => ({summary: ""});',
        'const section = (r, name) => name === "where it stands" && r.statement ? {text: "- 2026-10-16 — " + r.statement} : null;',
        'const cases = ' + json.dumps(cases) + ';',
        'console.log(JSON.stringify(cases.map(([text]) => [capFirst(text),',
        'memoryStatement({path: "projects/pilot.md", category: "projects", statement: text})])));',
    ])
    for (text, expected), (capitalised, lead) in zip(cases, _run_reader_js(script)):
        assert capitalised == expected, text
        assert lead == expected.replace("`", "").replace("#", ""), text


def test_snapshot_uses_stated_org_names_without_changing_notebook(tmp_path):
    from connectonion.rem.reader import snapshot

    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    pages = {
        "orgs/brightlane-example-1.md": "# brightlane.example\n\nBrightlane's legal identity is recorded.\n",
        "orgs/connectonion-com-2.md": "# connectonion.com\n\nAn agent framework.\n",
        "orgs/harbourpost-example-3.md": "# harbourpost.example\n\nNo name stated.\n\n## Sources\n- HarbourPost archived mail\n",
        "orgs/stonefield-example-4.md": "# stonefield.example\n\nStone Field manages properties.\n",
        "orgs/named.md": "# An existing title\n\nConnectOnion operates here.\n",
        "projects/domain.md": "# brightlane.example\n\nBrightlane operates here.\n",
        "people/alice.md": "# Alice\n\n## Facts\n- Company: [ConnectOnion](../orgs/connectonion-com-2.md) [3]\n",
        "people/bob.md": "# Bob\n\n- Company: [An older name](../orgs/brightlane-example-1.md) [1]\n",
    }
    for path, text in pages.items():
        notebook.write(path, text)
    before = {p.relative_to(tmp_path).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in tmp_path.rglob("*") if p.is_file()}

    records = {r["path"]: r for r in snapshot(tmp_path)["records"]}
    for path, name, domain in [("orgs/brightlane-example-1.md", "Brightlane", "brightlane.example"),
                               ("orgs/connectonion-com-2.md", "ConnectOnion", "connectonion.com"),
                               ("orgs/stonefield-example-4.md", "Stone Field", "stonefield.example")]:
        assert records[path]["title"] == name
        assert records[path]["domain"] == domain
        assert records[path]["text"] == pages[path]
    assert records["orgs/harbourpost-example-3.md"]["title"] == "harbourpost.example"
    assert "domain" not in records["orgs/harbourpost-example-3.md"]
    assert records["orgs/named.md"]["title"] == "An existing title"
    assert "domain" not in records["orgs/named.md"]
    assert records["projects/domain.md"]["title"] == "brightlane.example"
    assert "domain" not in records["projects/domain.md"]
    assert before == {p.relative_to(tmp_path).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("domain, text, expected", [
    ("stonefield.example", "Stone Field manages properties.", "Stone Field"),
    ("connectonion.com", "Connectonion began. ConnectOnion grew. ConnectOnion ships.", "ConnectOnion"),
    ("brightlane.example", "Brightlane’s legal identity.", "Brightlane"),
    ("onetwothreefourfive.com", "One Two Three Four Five operates here.", ""),
    ("stonefield.example", "Stone and Field are separate words.", ""),
    ("brightlane.example", "brightlane is lowercase.", ""),
    ("brightlane.example", "No name.\n\n## Sources\nBrightlane is only a source.\n\n## History\nNothing new.", ""),
])
def test_org_prose_name_matches_capitalised_runs_and_most_frequent_spelling(domain, text, expected):
    from connectonion.rem.reader import _org_name

    assert _org_name(domain, f"# {domain}\n\n{text}\n") == expected


def test_org_company_name_uses_the_most_common_linked_company_fact():
    from connectonion.rem.reader import _org_company_name

    values = ["Older name", "connectonion.com", "connectonion.com", "ConnectOnion", "ConnectOnion"]
    records = [{"path": f"people/{i}.md", "category": "people",
                "text": f"# Person {i}\n\n- Company: [{value}](../orgs/co.md) [3]\n"}
               for i, value in enumerate(values)]
    assert _org_company_name("orgs/co.md", records) == "ConnectOnion"
    assert _org_company_name("orgs/other.md", records) == ""


@pytest.mark.parametrize("protocol", ["file:", "about:"])
def test_copy_path_keeps_the_notebook_root(tmp_path, protocol):
    root = tmp_path / "owner's notebook"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice\n")
    page = render(root)
    data = json.loads(re.search(r"const REM = (.*);", page).group(1))
    record = next(r for r in data["records"] if r["path"] == "people/alice.md")
    # Execute the generated handlers with only the clipboard and footer DOM stubbed.
    copy = re.search(r"pathBtn.onclick = .*", page).group(0)
    # D-60 (build 3b review): Reader settings no longer prints a re-open command; only the path copy remains.
    assert not [line for line in page.splitlines() if "settings.appendChild" in line and "remCommand(" in line]
    script = "\n".join([
        "const REM = " + json.dumps(data) + "; const r = " + json.dumps(record) + ";",
        "const location = {protocol: " + json.dumps(protocol) + "};",
        "const result = {}, pathBtn = {};",
        "const copyToClipboard = path => result.path = path;",
        "const el = (tag, attrs) => attrs.text;",
        "const settings = {appendChild: text => result.footer = text};",
        copy, "pathBtn.onclick(); console.log(JSON.stringify(result));",
    ])
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed; it runs the reader's JavaScript")
    privacy = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0)
                        for name in ["privatePassages", "unlabelled", "hasPrivacy"])
    privacy += "\n" + re.search(r"function privateTopicHidden\(.*?\}", TEMPLATE.read_text(), re.S).group(0)
    script = privacy + "\n" + script
    # stdin, not -e: Linux caps one argument at 128 KB and the template is larger.
    script = "const UI = {en: {}}; let uiLanguage = 'en';\n" + re.search(r"function t\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + re.search(r"function uiLocale\(.*?\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + script
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"path": str(root / record["path"])}


def test_render_embeds_records_and_neutralizes_markup(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).write("people/alice.md", HOSTILE)
    Notebook(tmp_path).write("decisions/markdown.md", "# Markdown over a database\n\nSee [Alice](../people/alice.md).")
    page = render(tmp_path)
    assert "people/alice.md" in page and "decisions/markdown.md" in page
    # Note text reaches the page only as JSON data; no raw tag from a note may appear as markup.
    assert "<script>alert(1)" not in page
    assert "<img src=x" not in page
    assert page.count("</script>") == page.count("<script")
    assert "as_of" in page


def test_the_snapshot_carries_the_package_version_for_the_sidebar_footer(tmp_path, monkeypatch):
    """The sidebar footer reads "co 1.9.3" from the page's own data, in the live reader and the file snapshot alike."""
    import connectonion
    prepare(tmp_path)
    monkeypatch.setattr(connectonion, "__version__", "9.8.7")
    for live in (False, True):
        page = render(tmp_path, live=live, local=True)
        data = json.loads(re.search(r"const REM = (.*?);\nwindow\.REM", page, re.S).group(1))
        assert data["version"] == "9.8.7"


def test_render_does_not_export_uncited_session_window_text(tmp_path):
    from connectonion.rem.files import state_path, write_json

    prepare(tmp_path)
    Notebook(tmp_path).write("people/alice.md", "# Alice\n\nA short, cited page.\n")
    cache = state_path(tmp_path, "session-windows/example.json")
    write_json(cache, {"items": [{"source": "codex:example:123", "text": "private uncited session marker"}]})

    assert "private uncited session marker" not in render(tmp_path)


def test_snapshot_shows_dead_running_run_as_interrupted(tmp_path, monkeypatch):
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.reader import snapshot
    from connectonion.rem.service import run_logs, running_marker

    prepare(tmp_path)
    write_json(state_path(tmp_path, "runs/run_dead.json"), {
        "started_at": "2026-10-16T00:00:00+00:00", "outcome": "running", **running_marker()})
    monkeypatch.setattr("connectonion.rem.service._alive", lambda pid: False)

    assert snapshot(tmp_path)["logs"][0]["outcome"] == "interrupted"
    assert run_logs(tmp_path)[0]["outcome"] == "running"


def test_reader_lists_unreviewed_mail_contacts_without_making_empty_pages(tmp_path):
    from connectonion.rem.files import state_path, write_json
    prepare(tmp_path)
    write_json(state_path(tmp_path, "map.json"), {
        "all_history": True, "people": [],
        "without_page": [{"address": "leah@example.org", "name": "Leah Bell", "mails": 1,
                          "sent": 1, "received": 0, "last": "1998-06-01", "subject": "private subject"}],
        "errors": [{"source": "outlook", "stage": "metadata-window", "error": "ReadTimeout"}]})
    rows, coverage = contact_candidates(tmp_path)
    assert rows == [{"name": "Leah Bell", "email": "leah@example.org", "last": "1998-06-01",
                     "mails": 1, "sent": 1, "received": 0}]
    assert coverage["incomplete"] and coverage["scope"] == "all available history since 1970"
    assert "private subject" not in render(tmp_path)
    assert Notebook(tmp_path).list("people") == []


def test_render_is_self_contained_with_no_remote_assets(tmp_path):
    page = render(tmp_path)
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', page)
    assert "<link" not in page  # styles are inline; a stylesheet would be a fetch
    assert "@import" not in page


def test_render_before_start_shows_not_started_and_creates_nothing(tmp_path):
    root = tmp_path / "rem"
    page = render(root)
    assert "Not started" in page
    assert not root.exists()


def test_write_reader_lands_outside_the_notebook_and_leaves_notes_untouched(tmp_path):
    prepare(tmp_path)
    note = tmp_path / "notes" / "idea.md"
    Notebook(tmp_path).write("notes/idea.md", "# Idea\n")
    before = sorted((p.relative_to(tmp_path).as_posix(), p.stat().st_mtime_ns)
                    for p in tmp_path.rglob("*") if p.is_file())
    page = write_reader(tmp_path)
    assert page.is_file()
    assert tmp_path not in page.parents  # rendered output is not inside the collected tree
    if os.name != "nt":
        assert oct(page.stat().st_mode & 0o777) == "0o600"
    after = sorted((p.relative_to(tmp_path).as_posix(), p.stat().st_mtime_ns)
                   for p in tmp_path.rglob("*") if p.is_file())
    assert before == after
    assert note.read_text() == "# Idea\n"
    assert Notebook(tmp_path).list() == ["notes/idea.md"]  # the page is not a record


def test_write_reader_refuses_to_follow_a_planted_symlink(tmp_path, monkeypatch):
    """The page name is predictable, so a symlink planted there must not become a write elsewhere."""
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    try:
        os.symlink(victim, reader_path(tmp_path / "rem"))
    except OSError as error:
        if os.name == "nt" and getattr(error, "winerror", None) == 1314:
            pytest.skip("symlinks require Windows Developer Mode or elevation")
        raise
    with pytest.raises(OSError):
        write_reader(tmp_path / "rem")
    assert victim.read_text() == "keep"


def test_write_reader_replaces_its_snapshot_without_posix_only_flags(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    root = tmp_path / "rem"
    first = write_reader(root)
    first.write_text("old snapshot")
    second = write_reader(root)
    assert second == first
    assert "old snapshot" not in second.read_text()
    assert list(tmp_path.glob("co-rem-*.html")) == [second]


def test_open_reader_launches_the_file_uri_only_when_asked(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: opened.append(url) or True)
    page = open_reader(tmp_path, launch=False)
    assert opened == []
    page = open_reader(tmp_path, launch=True)
    assert opened == [page.as_uri()]
    assert opened[0].startswith("file://")


def test_summary_values_hide_only_empty_placeholders():
    page = TEMPLATE.read_text(encoding="utf-8")
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["plainLine", "knownValue"])
    unfilled = next(line for line in page.splitlines() if line.startswith("const UNFILLED_LINE ="))
    cases = [None, "", "  ", "Unknown", "unknown", "Unknown.", "—", "Unknown — not verified.",
             "Unknown — not verified. The latest session confirms a changed owner.", "Avery Lin", 0]
    result = _run_reader_js("\n".join([functions, unfilled, "const youify = text => text;",
                                     "console.log(JSON.stringify(" + json.dumps(cases) + ".map(knownValue))); "]))
    assert result == [False] * 8 + [True] * 3




def test_source_focus_candidates_exclude_unreachable_controls():
    page = TEMPLATE.read_text(encoding="utf-8")
    function = re.search(r"function evidenceControls\(.*?\n\}", page, re.S).group(0)
    result = _run_reader_js("\n".join([
        function,
        'const getComputedStyle = node => ({visibility: node.visibility || "visible"});',
        'const cases = [{id: "close"}, {id: "disabled", disabled: true}, {id: "negative", tab: -1},',
        '{id: "aria-hidden", hidden: true}, {id: "hidden-ancestor", hidden: true},',
        '{id: "no-layout", rects: []}, {id: "invisible", visibility: "hidden"}, {id: "last"}];',
        'const controls = cases.map(c => ({...c, tabIndex: c.tab ?? 0, matches: () => !!c.disabled,',
        'closest: () => c.hidden ? {} : null, getClientRects: () => c.rects || [{}]}));',
        'console.log(JSON.stringify(evidenceControls({querySelectorAll: () => controls}).map(c => c.id)));',
    ]))
    assert result == ["close", "last"]


def test_reader_template_javascript_compiles():
    script = TEMPLATE.read_text(encoding="utf-8").split("<script>", 1)[1].split("</script>", 1)[0]
    assert _run_reader_js("new Function(" + json.dumps(script) + "); console.log(true);") is True


def test_project_thread_direction_requires_an_explicit_debtor():
    page = TEMPLATE.read_text(encoding="utf-8")
    functions = page[page.index('let OWING = null;'):page.index('const DIRECTION_LABEL =')]
    cases = {
        '2026-10-13: You asked to revisit a title.': 'plain',
        '2026-10-13: Requested confirmation of the plan.': 'plain',
        'Avery promised to send a draft.': 'mine',
        'The user owes Mara an answer.': 'mine',
        'Mara owes you feedback.': 'theirs',
        'Waiting on Fernhill for a test inbox; promised 2026-09-12.': 'theirs',
        'Promised a draft; owner is unclear.': 'plain',
    }
    script = '\n'.join([
        'const REM = {owner: "people/avery.md"};',
        'const byPath = () => ({title: "Avery Lin"});', functions,
        'console.log(JSON.stringify(' + json.dumps(list(cases)) + '.map(projectDirection)));',
    ])
    assert _run_reader_js(script) == list(cases.values())


def test_activity_disclosure_filters_and_refreshes_private_rows():
    page = TEMPLATE.read_text(encoding="utf-8")
    activity = page[page.index('function activityDisclosure('):page.index('\nfunction record(')]
    script = r'''
      let hidePrivate = false;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        dataset: {type: attrs['data-type']},
        classList: {contains: name => (attrs.class || '').split(' ').includes(name), toggle() {}},
        appendChild(child) { this.children.push(child); },
        append(...nodes) { this.children.push(...nodes); },
        setAttribute(key, value) { this[key] = value; },
        querySelectorAll() { return this.children; }
      });
      const document = {documentElement: {classList: {contains: () => hidePrivate}}};
      const section = () => ({text: ''});
      const historyItems = () => Array.from({length: 9}, (_, i) => ({day: '2026-09-0' + (9-i), text: String(i)}));
      const historyRowContent = text => el('p', {class: Number(text) < 2 ? 'privacy-only' : ''});
      const activityType = text => Number(text) < 7 ? 'Decision' : 'Conversation';
      const threadDate = day => day;
      const privateHistoryNotice = () => el('p', {class: 'private-history-notice'});
    ''' + activity + r'''
      const panel = activityPanel({path: 'orgs/example.md'});
      const filters = panel.children.find(n => n.class === 'activity-filters');
      const list = panel.children.find(n => n.class === 'activity-list');
      const more = panel.children.find(n => n.class === 'btn-action activity-more');
      const shown = () => list.children.filter(n => !n.hidden).length;
      const states = [[shown(), more.textContent, more.hidden]];
      more.onclick(); states.push([shown(), more.textContent, more.hidden]);
      hidePrivate = true; list.refreshActivity();
      states.push([shown(), more.textContent, more.hidden]);
      more.onclick(); states.push([shown(), more.textContent, more.hidden]);
      filters.children.find(b => b.text === 'Conversation 2').onclick();
      states.push([shown(), more.textContent, more.hidden]);
      console.log(JSON.stringify({states, noticeNext: panel.children[panel.children.indexOf(list)+1].class}));
    '''
    assert _run_reader_js(script) == {
        'states': [[5, 'Show all 9', False], [9, 'Show less', False],
                   [7, 'Show less', False], [5, 'Show all 7', False], [2, 'Show all 2', True]],
        'noticeNext': 'private-history-notice',
    }


def test_unquoted_inline_html_never_parses_a_dom():
    page = TEMPLATE.read_text(encoding="utf-8")
    function = re.search(r"function quoteSpans\(.*?\n\}", page, re.S).group(0)
    inputs = ["plain prose", "<em>formatted prose</em>", "", "a &amp; b",
              '<a href="#r=sessions%2Fexample.md">Session</a>',
              '<span class="private" data-level="personal">Labelled prose</span>',
              '<code title="a long identifier">identifier</code>']
    # No document exists in Node: even attempting to build a DOM fails this test.
    assert _run_reader_js(function + "\nconsole.log(JSON.stringify(" + json.dumps(inputs)
                          + ".map(quoteSpans)));") == inputs


def test_thread_priority_uses_only_explicit_deadlines_and_blocking_words():
    page = TEMPLATE.read_text(encoding="utf-8")
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["blocksWork", "blockerTag", "threadAge", "dueLabel", "threadDate", "fmtDate", "age", "daysSince"])
    cases = [
        {"text": "Please review the draft.", "since": "2026-10-17"},
        {"text": "This blocks the launch.", "since": "2026-10-17"},
        {"text": "The launch is blocked.", "since": "2026-10-17"},
        {"text": "Blocking the export.", "since": "2026-10-17"},
        {"text": "Review before we can launch.", "since": "2026-10-17"},
        {"text": "Review before lunch.", "since": "2026-10-17", "due": "2026-10-23"},
        {"text": "Unblocked already.", "since": "2026-09-01", "due": "2026-09-10"},
    ]
    result = _run_reader_js("\n".join([
        functions, 'const REM = {as_of: "2026-10-20"}, DAY_MS = 86400000;',
        'const calendarDay = text => text.slice(0, 10);',
        'const el = (tag, attrs) => attrs;',
        'console.log(JSON.stringify(' + json.dumps(cases)
        + '.map(t => ({age: threadAge(t), tag: blockerTag(t)}))));',
    ]))
    assert [row["age"] for row in result] == ["3 days"] * 5 + ["3 days · due Oct 23", "49 days · overdue · Sep 10"]
    assert [bool(row["tag"]) for row in result] == [False, True, True, True, True, False, False]


@pytest.mark.parametrize('languages', [['zh', 'en'], ['en', 'zh']])
def test_interface_language_prefers_supported_non_english_and_leaves_record_prose_alone(tmp_path, monkeypatch, languages):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build

    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    monkeypatch.setattr('connectonion.rem.languages.owner_languages', lambda root: {'languages': languages, 'from': 'detected from your own mail and sessions'})
    page = render(build(tmp_path / 'rem', datetime(2026, 10, 1, tzinfo=timezone.utc)), local=True)
    data = json.loads(re.search(r'const REM = (.*);', page).group(1))
    interface = page[page.index('let uiLanguage ='):page.index('function setInterfaceLanguage(')]
    script = '\n'.join([
        '(function() {', 'const REM = ' + json.dumps(data) + ';', interface,
        'const original = REM.records.find(r => r.path === "people/mara-ostrowski.md").text;',
        'const labels = [t("People"), t("Between you")];',
        'uiLanguage = "en"; labels.push(t("People"));',
        'REM.your_languages = ["en", "zh"];',
        'console.log(JSON.stringify({labels, original}));', '})();',
    ])
    result = _run_reader_js(script)
    assert result['labels'] == ['人物', '我们之间', 'People']
    assert result['original'] == next(r['text'] for r in data['records'] if r['path'] == 'people/mara-ostrowski.md')


@pytest.mark.parametrize('storage', [
    "Object.defineProperty(globalThis, 'localStorage', {get() { throw Error('blocked'); }});",
    "globalThis.localStorage = {getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); }};",
    "delete globalThis.localStorage;",
])
def test_reader_preferences_survive_unavailable_or_throwing_storage(storage):
    function = re.search(r'function readerStorage\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js('\n'.join([
        function, storage,
        '(async () => { console.log(JSON.stringify([await readerStorage("co-rem-ui-language"),',
        'await readerStorage("co-rem-ui-language", "zh")])); })();',
    ]))
    assert result == [None, None]


def test_dynamic_reader_chrome_translates_without_changing_english():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['age', 'dueLabel', 'threadDate', 'fmtDate', 'citationDate', 'chipLabel'])
    result = _run_reader_js('\n'.join([
        '(() => { let uiLanguage = "en";', interface, functions,
        'const REM = {as_of: "2026-10-20"}, calendarDay = day => day;',
        'const daysSince = day => Number(day), citationSource = () => "", citationId = () => "";',
        'const sourceChannel = () => "";',
        'const labels = () => [age("10"), age("1"), age("0"), citationDate({}, "99"),',
        'dueLabel({due: "2026-10-19"}), dueLabel({due: "2026-10-21"}),',
        't("Read {n} items", {n: 240}), t("Rewrote {n} pages", {n: 7}),',
        't("{n} runs", {n: 10}), t("{n} written of {m}", {n: 3, m: 6, unit: " 人"})];',
        'const en = labels(); uiLanguage = "zh"; const zh = labels();',
        'console.log(JSON.stringify({en, zh})); })();',
    ]))
    assert result['en'] == ['10 days', '1 day', 'today', 'source 99', 'overdue · Yesterday', 'due Oct 21',
                            'Read 240 items', 'Rewrote 7 pages', '10 runs', '3 written of 6']
    assert result['zh'] == ['10 天', '1 天', '今天', '来源 99', '已逾期 · 昨天', '到期 10月21日',
                            '阅读了 240 项', '改写了 7 页', '10 次运行', '6 人中，3 人有内容']


@pytest.mark.parametrize('source', ['unbroken' * 80 + ':fixture', 'gmail:fixture', ''],
                         ids=['long-source', 'undated-mail', 'missing'])
def test_undated_quiet_citation_uses_number_instead_of_source_label(source):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['citationDate', 'calendarDay', 'fmtDate'])
    result = _run_reader_js('\n'.join([
        functions, 'const REM = {source_context: {}};',
        'const citationSource = () => ' + json.dumps(source) + ', citationId = citationSource;',
        'const chipLabel = () => ' + json.dumps(source) + ';',
        'const labels = [citationDate({}, "99")];',
        'REM.source_context[' + json.dumps(source) + '] = {time: "2026-10-20"};',
        'labels.push(citationDate({}, "99")); console.log(JSON.stringify(labels));',
    ]))
    assert result == ['source 99', 'Oct 20']


def test_reader_browser_evaluate_strings_compile():
    import ast
    scripts = []
    for path in sorted((TEMPLATE.parents[2] / 'tests/e2e/cli').glob('test_rem*reader*browser.py')):
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'evaluate' and node.args
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                scripts.append({'file': path.name, 'line': node.lineno, 'source': node.args[0].value})
    assert scripts
    script = '\n'.join([
        'const vm = require("node:vm"), scripts = ' + json.dumps(scripts) + ';',
        'for (const script of scripts) new vm.Script(script.source, {filename: script.file + ":" + script.line});',
        'console.log(JSON.stringify(scripts.length));',
    ])
    assert _run_reader_js(script) == len(scripts)


@pytest.mark.parametrize('languages,browser,expected', [
    (['en', 'zh'], 'en-AU', 'zh'), (['ja', 'en', 'zh'], 'en-AU', 'zh'),
    (['en'], 'zh-CN', 'zh'), ([], 'zh-TW', 'zh'),
    (['ja', 'en'], 'ja-JP', 'en'), ([], 'en-AU', 'en'),
])
def test_reader_interface_language_default(languages, browser, expected):
    page = TEMPLATE.read_text()
    default = page[page.index('let uiLanguage ='):page.index('let morePeopleColumns =')]
    result = _run_reader_js('\n'.join([
        '(() => { const REM = {your_languages: ' + json.dumps(languages) + '};',
        'const navigator = {language: ' + json.dumps(browser) + '};', default,
        'console.log(JSON.stringify(uiLanguage)); })();',
    ]))
    assert result == expected


def test_changed_field_matches_raw_facts_before_display_formatting():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['changedValue', 'factText', 'plainLine'])
    script = '\n'.join([
        '(() => {', functions, 'const youify = value => value;',
        'const r = {path: "people/avery-lin.md"};',
        'let items; const parseFacts = () => new Map([["First contact", items]]);',
        'const firstBuild = () => false; let memoryPass = {claims: [{record: r.path, field: "first contact",',
        'before: "2026-09-01", after: "2026-10-01"}]};',
        'const check = () => { const classes = [];',
        'const node = {textContent: "1 Oct 2026", classList: {add: value => classes.push(value)}};',
        'changedValue(node, r, "First contact"); return {classes, title: node.title}; };',
        'items = [{value: "2026-10-01", qualifier: ""}]; const date = check();',
        'items = [{value: "2026-10-02", qualifier: ""}]; const superseded = check();',
        'items = [{value: "https://example.com", qualifier: "work"}, {value: "https://example.com/pilot", qualifier: ""}];',
        'memoryPass.claims[0].after = "https://example.com (work); https://example.com/pilot";',
        'const multiple = check(); memoryPass.claims = []; const older = check();',
        'console.log(JSON.stringify({date, superseded, multiple, older})); })();',
    ])
    result = _run_reader_js(script)
    assert result['date'] == {'classes': ['changed-value'], 'title': 'Changed last night: 2026-09-01 → 2026-10-01'}
    assert result['multiple']['classes'] == ['changed-value']
    assert result['superseded'] == result['older'] == {'classes': []}


def test_update_markers_follow_latest_pass_in_the_invented_notebook(tmp_path, monkeypatch):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    from connectonion.rem.reader import snapshot
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build

    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    data = snapshot(build(tmp_path / 'rem', datetime(2026, 10, 1, 12, tzinfo=timezone.utc)))
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['lastPass', 'firstBuild', 'runTime', 'sameClaim', 'updatedMarker'])
    result = _run_reader_js('\n'.join([
        '(() => { const REM = ' + json.dumps(data) + ';', functions,
        'const HOUR = 3600e3, FAILED = /^(failed|abandoned|error|refused|timeout)/i;',
        re.search(r'^const STAMP = .*$', page, re.M).group(0),
        'const byPath = path => REM.records.find(r => r.path === path);',
        'const listedRecords = () => REM.records, byActivity = () => 0, sourceName = value => value;',
        'const el = (tag, attrs, children) => ({...attrs, children});',
        'const memoryPass = lastPass();',
        'console.log(JSON.stringify({changed: memoryPass.changed.map(r => r.path).sort(),',
        'mara: updatedMarker(byPath("people/mara-ostrowski.md")),',
        'eyebrow: updatedMarker(byPath("people/mara-ostrowski.md"), true),',
        'tomas: updatedMarker(byPath("people/tomas-reyes.md"))})); })();',
    ]))
    assert result['changed'] == ['orgs/fernhill-labs.md', 'people/avery-lin.md',
                                 'people/mara-ostrowski.md', 'projects/harbour.md']
    assert result['mara'] == {'class': 'fresh-label', 'text': 'last night',
                              'title': "Updated in last night's pass"}
    assert result['eyebrow']['children'][0]['text'] == '●'
    assert result['eyebrow']['children'][1] == 'updated last night'
    assert result['tomas'] is None


def test_record_freshness_labels_translate_without_changing_english():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    labels = ['last activity', 'file updated', 'last mapped session', 'last name match',
              'archived messages', 'last night', "Updated in last night's pass"]
    result = _run_reader_js('\n'.join([
        '(() => { let uiLanguage = "en";', interface,
        'const labels = ' + json.dumps(labels) + ';',
        'const en = labels.map(label => t(label)); uiLanguage = "zh";',
        'console.log(JSON.stringify({en, zh: labels.map(label => t(label))})); })();',
    ]))
    assert result['en'] == labels
    assert result['zh'] == ['最近动态', '文件更新于', '最近会话', '最近名称匹配',
                            '条存档消息', '昨夜', '昨夜整理时更新']


def test_audited_chrome_uses_category_nouns_and_keeps_english_labels():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['categoryCount', 'usageCaption', 'refusalReason', 'sourceLabel', 'threadDate', 'fmtDate', 'calendarDay'])
    result = _run_reader_js('\n'.join([
        '(() => { let uiLanguage = "zh";', interface, functions,
        'const REM = {source_context: {"claude-code:12345678-1234-1234-1234-123456789abc:1": {time: "2026-09-03T12:00:00Z"}}};',
        'const categories = ["people", "orgs", "projects", "skills", "decisions", "principles"];',
        'const zh = categories.map(c => categoryCount(c, {written: 3, mapped: 6}, 6));',
        'const emptyCounts = categories.map(c => categoryCount(c, null, 3));',
        'const labels = [t("Waiting on you"), t("Current context"), t("daily-update"),',
        'usageCaption({count: 2, last: "2026-10-10"}),',
        'refusalReason("Changed page has no numbered evidence references"),',
        'refusalReason("Missing or duplicate citation: 22"),',
        'sourceLabel("claude-code:12345678-1234-1234-1234-123456789abc:1"), sourceLabel("claude-code:" + "a".repeat(50))];',
        'uiLanguage = "en";',
        'const en = categories.map(c => categoryCount(c, {written: 3, mapped: 6}, 6));',
        'console.log(JSON.stringify({zh, emptyCounts, labels, en, englishReason: refusalReason("Missing or duplicate citation: 22")})); })();',
    ]))
    units = ['人', '个组织', '个项目', '项', '项', '条']
    assert result['zh'] == [f'6 {unit}中，3 {unit}有内容' for unit in units]
    assert result['emptyCounts'] == [f'3 {unit}' for unit in units]
    assert result['en'] == ['3 written of 6'] * 6
    assert result['labels'] == ['等你处理', '当前背景', '每日更新', '2 次技能名称匹配 · 最近 10月10日 · 版本未验证',
                                '改动的页面缺少编号来源引用', '缺失或重复的引用：22', 'Claude Code 会话 · 9月3日', 'claude-code:aaaaaaaa…']
    assert result['englishReason'] == 'Missing or duplicate citation: 22'


def test_activity_translates_known_refusals_before_joining_separate_errors():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['refusalReason', 'unwritten'])
    errors = ['Missing section: Facts', 'Cited local file needs a file: source ID and SHA-256: 22',
              'Fact without a citation: Role; cite the message it came from, or write Unknown',
              'Page cites only the page itself and the coverage note; nothing about the subject was read']
    result = _run_reader_js('\n'.join([
        '(() => { let uiLanguage = "zh";', interface, functions,
        'const run = {refusals: [{record: "people/avery-lin.md", errors: ' + json.dumps(errors) + '}]};',
        'const zh = unwritten(run)[0].why; uiLanguage = "en";',
        'console.log(JSON.stringify({zh, en: unwritten(run)[0].why})); })();',
    ]))
    assert result['en'] == '; '.join(errors)
    assert result['zh'] == ('缺少章节：Facts；引用本地文件须有 file: 来源 ID 与 SHA-256：22；'
                            '事实缺少引用：Role；请引用原消息，或填写 Unknown；'
                            '页面仅引用自身与覆盖记录，未阅读主题相关材料')


@pytest.mark.parametrize('source,dated,expected', [
    ('outlook:123456789abc:Returned client agreement.pdf', True,
     'outlook:123456789abc:Returned client agreement.pdf'),
    ('outlook:' + 'a' * 40 + ':Returned client agreement.pdf', False,
     'outlook:' + 'a' * 40 + ':Returned client agreement.pdf'),
    ('gmail:123456789abc', True, 'gmail:123456789abc'),
    ('claude-code:human-readable-session-name:1', True, 'claude-code:human-readable-session-name:1'),
    ('codex:12345678-1234-1234-1234-123456789abc:2', True, 'Codex session · Sep 3'),
    ('claude-code:12345678-1234-1234-1234-123456789abc:2', True, 'Claude Code session · Sep 3'),
    ('codex:12345678-1234-1234-1234-123456789abc:2', False, 'codex:12345678…:2'),
    ('file:' + 'b' * 32, True, 'file:bbbbbbbb…'),
    ('gmail:' + 'c' * 31, False, 'gmail:' + 'c' * 31),
])
def test_source_labels_only_shorten_opaque_segments(source, dated, expected):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['sourceLabel', 'threadDate', 'fmtDate', 'calendarDay'])
    context = {source: {'time': '2026-09-03T12:00:00Z'}} if dated else {}
    result = _run_reader_js('\n'.join([
        functions, 'const REM = {source_context: ' + json.dumps(context) + '};',
        'console.log(JSON.stringify(sourceLabel(' + json.dumps(source) + ')));',
    ]))
    assert result == expected


def test_reader_near_duplicate_obligations_keep_direction_dates_and_sources():
    page = TEMPLATE.read_text()
    functions = page[page.index('function obligationWords('):page.index('function threadCounterpart(')]
    raw = re.search(r'function rawSection\(.*?\n\}', page, re.S).group(0)
    script = r'''
      const REM = {source_context: {}}, COMMENT = /<!--[\s\S]*?-->/g, DAY_MS = 86400000;
    ''' + raw + functions + r'''
      const entry = (name, text, source = 'gmail:letter', day = '2026-09-30', dir = 'mine') => ({
        r: {path: 'people/' + name + '.md', text: '# ' + name + '\n\n## Sources\n- [1] ' + source},
        t: {text, since: day, dir}
      });
      const a = entry('mara', 'You owe a Letter of Support draft with contribution questions [1].');
      const b = entry('tomas', 'Please send a support letter draft with contribution questions [1].', 'gmail:other', '2026-10-01');
      const c = entry('ines', 'A completely reworded request [1].');
      const groups = threadGroups([a, b, c]);
      const bridge = threadGroups([a, {...a, t: {...a.t, since: '2026-10-06'}},
        {...a, t: {...a.t, since: '2026-10-12'}}]);
      REM.source_context = {'gmail:one': {source: 'gmail', thread: 'fixture-thread'},
        'gmail:two': {source: 'gmail', thread: 'fixture-thread'}};
      const evidence = item => obligationEvidence(item);
      console.log(JSON.stringify({
        grouped: groups.map(group => group.map(entry => entry.r.path)),
        bridge: bridge.map(group => group.length),
        sharedThread: sameObligation(evidence(entry('mara', 'Travel itinerary [1].', 'gmail:one')),
          evidence(entry('ines', 'Please check invoices [1].', 'gmail:two'))),
        opposite: sameObligation(evidence(a), evidence({...b, t: {...b.t, dir: 'theirs'}})),
        older: sameObligation(evidence(a), evidence({...b, t: {...b.t, since: '2026-10-08'}})),
        quoteOnly: sameObligation(evidence(entry('mara', 'Invoice audit “send the details” [1].')),
          evidence(entry('tomas', 'Travel itinerary “send the details” [1].', 'gmail:travel'))),
        unresolved: sameObligation(evidence(entry('mara', 'First request [9].')),
          evidence(entry('tomas', 'Unrelated invoice [9].')))
      }));
    '''
    result = _run_reader_js(script)
    assert result == {'grouped': [['people/mara.md', 'people/tomas.md'], ['people/ines.md']],
                      'bridge': [2, 1], 'sharedThread': False,
                      'opposite': False, 'older': False, 'quoteOnly': False, 'unresolved': False}


def test_reader_language_swap_reuses_parsing_and_restores_original():
    page = TEMPLATE.read_text()
    swap = re.search(r'function swapLanguage\(.*?\n\}', page, re.S).group(0)
    parsing = page[page.index('const UNKNOWN_LINE ='):page.index('function mappedContact(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['splitTrailers', 'plainLine'])
    script = parsing + functions + swap + r'''
      const FACTS = new Map(), SESSION_TEXT = new Map(), youify = text => text;
      const r = {path: 'people/avery-lin.md', category: 'people', title: 'Avery Lin',
        text: '# Avery Lin\n\nAn original lead [1].',
        translations: {zh: '# Avery Lin\n\n中文摘要 [1].'}};
      const summaries = [known(r).summary];
      swapLanguage(r, 'zh'); summaries.push(known(r).summary);
      swapLanguage(r, ''); summaries.push(known(r).summary);
      swapLanguage(r, 'ja'); summaries.push(known(r).summary);
      console.log(JSON.stringify(summaries));
    '''
    assert _run_reader_js(script) == ['An original lead.', '中文摘要.', 'An original lead.', 'An original lead.']


def test_reader_skills_group_and_search_reveals_rare_matches():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['skillGroups', 'skillUsage'])
    script = r'''
      const el = (tag, attrs = {}, children = []) => ({tag, value: "", ...attrs, children,
        appendChild(child) { this.children.push(child); },
        append(...nodes) { this.children.push(...nodes); },
        set textContent(value) { this.children = []; }
      });
      const label = () => 'Skills', row = r => ({text: r.title});
      const daysSince = day => (new Date('2026-10-01') - new Date(day)) / 86400000;
    ''' + functions + r'''
      const names = ['weekly-brief', 'invoice-check', 'lark-mail', 'lark-doc', 'lark-calendar', 'talk-outline'];
      const items = names.map((title, i) => ({title, path: 'skills/catalog/' + title + '.md',
        text: 'Invoked 3 times in the last 180 days; last on ' + (i < 2 ? '2026-09-30' : i < 5 ? '2026-08-15' : '2026-01-01')}));
      const box = skillGroups(items), find = box.children[0], content = box.children[1];
      const groups = content.children.map(n => n.tag === 'details' ? [n.children[0].text, !!n.open] :
        [n.children[0].children[0], n.children[1].children.map(row => row.text)]);
      find.value = 'talk-outline'; find.oninput();
      const searched = content.children[0];
      console.log(JSON.stringify({groups, searched: [searched.children[0].text, searched.open,
        searched.children[1].children.map(row => row.text)]}));
    '''
    assert _run_reader_js(script) == {
        'groups': [['Used in the last 30 days', ['weekly-brief', 'invoice-check']],
                   ['lark', ['lark-calendar', 'lark-doc', 'lark-mail']], ['Rarely used (1)', False]],
        'searched': ['Rarely used (1)', True, ['talk-outline']]}


def test_reader_translated_relationship_takes_precedence_over_index_prose():
    page = TEMPLATE.read_text()
    parsing = page[page.index('const UNKNOWN_LINE ='):page.index('// ---------- the sheet:')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['splitTrailers', 'swapLanguage'])
    script = parsing + functions + r'''
      const REM = {}, SESSION_TEXT = new Map(), youify = text => text;
      const r = {path: 'people/avery-lin.md', title: 'Avery Lin', category: 'people',
        index: {how_known: 'Original indexed relationship'},
        text: '# Avery Lin\n\n## Our relationship\n- An original relationship [1].',
        translations: {zh: '# Avery Lin\n\n## Our relationship\n- 中文相识经过 [1].'}};
      const values = [facts(r).how];
      swapLanguage(r, 'zh'); values.push(facts(r).how);
      swapLanguage(r, ''); values.push(facts(r).how);
      console.log(JSON.stringify(values));
    '''
    assert _run_reader_js(script) == ['Original indexed relationship', '中文相识经过.', 'Original indexed relationship']


@pytest.mark.parametrize('separator', ['；', ';', '：', ':', '—'])
def test_reader_waiting_summary_trims_chinese_separators(separator):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['morningWords', 'withoutDateClutter', 'plainLine', 'capFirst', 'threadWords'])
    result = _run_reader_js(functions + r'''
      const inCategory = () => [], youify = text => text;
      const r = {title: 'Avery Lin'}, separator = ''' + json.dumps(separator) + r''';
      uiLanguage = 'zh';
      const chinese = morningWords('请签署试点协议' + separator + ' ，、；：— 后续安排明天讨论 [4]', r);
      uiLanguage = 'en';
      console.log(JSON.stringify([chinese,
        morningWords('Review the draft: keep this clause — and this one; discuss tomorrow [4]', r)]));
    ''')
    assert result == [{'words': '请签署试点协议' + separator + ' ，、；：— 后续安排明天讨论', 'context': '[4]'},
                      {'words': 'Review the draft: keep this clause — and this one; discuss tomorrow', 'context': '[4]'}]


def test_reader_parsed_facts_cache_follows_language_override_and_text_changes():
    page = TEMPLATE.read_text()
    parsing = page[page.index('const UNKNOWN_LINE ='):page.index('// ---------- the sheet:')]
    result = _run_reader_js(parsing + r'''
      const r = {path: 'people/avery.md', text: '# Avery\n\n## Facts\n- Role: Professor [1]\n- Company: Example Lab [1]\n',
        translations: {zh: '# Avery\n\n## Facts\n- Role: 理学院教授 [1]\n- Company: 示例实验室（历史任职） [1]\n'}};
      uiLanguage = 'zh';
      const chinese = parseFacts(r), reused = parseFacts(r) === chinese;
      uiLanguage = 'en';
      const english = parseFacts(r);
      uiLanguage = 'zh';
      const restored = parseFacts(r) === chinese;
      r.readLanguage = '';
      const override = parseFacts(r) === english;
      delete r.readLanguage;
      r.translations.zh = r.translations.zh.replace('理学院教授', '副教授');
      console.log(JSON.stringify({role: chinese.get('Role'), company: chinese.get('Company'),
        english: english.get('Role')[0].value, reused, restored, override,
        updated: parseFacts(r).get('Role')[0].value}));
    ''')
    assert result == {'role': [{'value': '理学院教授', 'qualifier': '', 'citations': ['1']}],
                      'company': [{'value': '示例实验室', 'qualifier': '历史任职', 'citations': ['1']}],
                      'english': 'Professor', 'reused': True, 'restored': True, 'override': True, 'updated': '副教授'}



def test_reader_history_accepts_chinese_colon_and_preserves_citations():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['listItems', 'historyItems'])
    result = _run_reader_js(functions + r'''
      console.log(JSON.stringify(historyItems('- 2026-10-15：Theo Park 发来合同 [3].\n- 2026-10-14: 已确认 [2].')));
    ''')
    assert result == [{'day': '2026-10-15', 'end': '', 'text': 'Theo Park 发来合同 [3].'},
                      {'day': '2026-10-14', 'end': '', 'text': '已确认 [2].'}]


def test_reader_merged_threads_exclude_empty_prose_and_the_rows_own_person():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['threadEntries', 'threadGroups', 'obligationEvidence', 'obligationWords',
                                       'sameObligation', 'plainLine', 'threadWords', 'rawSection'])
    result = _run_reader_js(functions + r'''
      const REM = {owner: 'people/ellis.md'}, COMMENT = /<!--[\s\S]*?-->/g, DAY_MS = 86400000;
      const youify = text => text;
      const records = [
        {path: REM.owner, title: 'Avery Lin', category: 'people'},
        {path: 'people/mara.md', title: 'Mara Ostrowski', category: 'people'},
        {path: 'people/mara-alias.md', title: 'Mara Ostrowski', category: 'people'},
        {path: 'people/mia-chen.md', title: 'Mia Chen', category: 'people'}
      ];
      const inCategory = () => records, listedRecords = () => records;
      const threads = r => ({items: r.items});
      for (const r of records) {
        r.text = '# ' + r.title + '\n\n## Sources\n- [1] gmail:shared';
        r.items = [{text: 'You owe Mara Ostrowski a signed agreement [1].', dir: 'mine', since: '2026-10-15'}];
      }
      records[0].items = [{text: ' ', originalText: 'You owe Mara Ostrowski a signed agreement [1].', dir: 'mine', since: '2026-10-16'},
        {text: 'You owe Mia Chen [1]', dir: 'mine', since: '2026-10-15'},
        {text: '[1].', dir: 'mine', since: '2026-10-16'}];
      records[1].items.push({...records[1].items[0]});
      const merged = threadEntries();
      console.log(JSON.stringify(merged.map(({r, t, also}) => ({person: r.title, text: t.text,
        also: also.map(person => person.title)}))));
    ''')
    assert result == [{'person': 'Mara Ostrowski', 'text': 'You owe Mara Ostrowski a signed agreement [1].',
                       'also': ['Mia Chen']}]


def test_reader_recent_skills_are_capped_and_overflow_keeps_family_groups():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['skillGroups', 'skillUsage'])
    result = _run_reader_js(r'''
      const el = (tag, attrs = {}, children = []) => ({tag, value: '', ...attrs, children,
        appendChild(child) { this.children.push(child); }, append(...nodes) { this.children.push(...nodes); },
        set textContent(value) { this.children = []; }
      });
      const label = () => 'Skills', row = r => ({text: r.title});
      const daysSince = day => (new Date('2026-10-20') - new Date(day)) / 86400000;
    ''' + functions + r'''
      const items = Array.from({length: 16}, (_, i) => ({title: (i < 3 ? 'misc' : 'lark-') + i,
        path: 'skills/catalog/skill-' + i + '.md',
        text: 'Invoked 3 times in the last 180 days; last on 2026-10-' + String(i+1).padStart(2, '0')}));
      const content = skillGroups(items).children[1];
      console.log(JSON.stringify(content.children.map(group => [group.children[0].children[0],
        group.children[1].children.map(row => row.text)])));
    ''')
    assert result == [['Used in the last 30 days', ['lark-15', 'lark-14', 'lark-13', 'lark-12', 'lark-11',
                                                  'lark-10', 'lark-9', 'lark-8', 'lark-7', 'lark-6']],
                      ['lark', ['lark-3', 'lark-4', 'lark-5']], ['Other', ['misc0', 'misc1', 'misc2']]]


@pytest.mark.parametrize('marker', ['Now:', 'Now：', '现在：'])
def test_reader_insight_labels_tolerate_chinese_punctuation(marker):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['memoryStatement', 'newestStanding', 'plainLine', 'listItems', 'capFirst'])
    result = _run_reader_js(functions + r'''
      const REM = {}, youify = text => text;
      const section = (r, name) => name === 'insight' ? {text: '- ' + r.marker + ' 已完成交付 [1].'} : null;
      const known = () => ({summary: ''});
      console.log(JSON.stringify(memoryStatement({path: 'people/arthur.md', category: 'people',
        marker: ''' + json.dumps(marker) + r'''})));
    ''')
    assert result == '已完成交付.'


@pytest.mark.parametrize('separator', [': ', '：', '： ', ' — '])
def test_reader_project_standing_tolerates_date_colon_without_space(separator):
    page = TEMPLATE.read_text()
    function = re.search(r'function newestStanding\(.*?\n\}', page, re.S).group(0)
    result = _run_reader_js(function + r'''
      const REM = {}, section = () => ({text: ''' + json.dumps('- 2026-10-15' + separator + '已经交付 [1].') + r'''});
      console.log(JSON.stringify(newestStanding({path: 'projects/launch.md', category: 'projects'})));
    ''')
    assert result == '已经交付 [1].'


@pytest.mark.parametrize('text,expected', [
    ('Earlier finding! Dr. Mara gives examples, e.g. support letters',
     'Dr. Mara gives examples, e.g. support letters'),
    ('Earlier question? You owe Mara a draft: “I will send it. Please wait!” (2026-10-14)',
     'You owe Mara a draft: “I will send it. Please wait!” (2026-10-14)'),
    ('Earlier finding; A separate supported clause', 'A separate supported clause'),
    ('Version 3.5 uses example.test: keep this, and that.',
     'Version 3.5 uses example.test: keep this, and that.'),
    ('前文。需要草稿：保留说明，及细节', '需要草稿：保留说明，及细节'),
    ('前文！「请等待。稍后答复！」（日期）需要草稿', '「请等待。稍后答复！」（日期）需要草稿'),
    ('前文？需要草稿', '需要草稿'),
    ('前文；需要草稿', '需要草稿'),
])
def test_reader_evidence_boundaries_preserve_english_and_add_cjk(text, expected):
    function = re.search(r'function sentenceEnds\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + '\nconst text = ' + json.dumps(text) + r''';
      console.log(JSON.stringify(text.slice(sentenceEnds(text).at(-1)).trim()));
    ''')
    assert result == expected


@pytest.mark.parametrize('punctuation', ['.', '!', '?', ';', ':', ',', '。', '！', '？', '；', '：', '，'])
@pytest.mark.parametrize('brackets,space', [('[]', ' '), ('[]', ''), ('［］', ' '), ('［］', '')])
def test_reader_privacy_passages_keep_chinese_tags_with_their_words(punctuation, brackets, space):
    label = brackets[0] + 'personal' + brackets[1]
    secret = '私密日期' + space + label + ' [13]' + punctuation
    text = '公开介绍。' + secret + '用户还需进行秘密后续联系' + space + label + '。公开结尾。'
    result = _run_reader_js('const text = ' + json.dumps(text) + r''';
      const passages = [];
      const publicText = privatePassages(text, (passage, level) => { passages.push([passage, level]); return ''; });
      console.log(JSON.stringify({passages, publicText, labelled: hasPrivacy(text)}));
    ''')
    assert result['publicText'] == '公开介绍。公开结尾。'
    assert len(result['passages']) == 2
    assert all(level == 'personal' for passage, level in result['passages'])
    assert result['labelled']


def test_reader_privacy_plain_summaries_preserve_public_words_links_and_inline_code():
    page = TEMPLATE.read_text()
    plain = re.search(r'function plainLine\(.*?\n\}', page, re.S).group(0)
    text = ('公开介绍。秘密文件 `case.txt` 和 [同事](people/secret.name.md)[sensitive] [1]。'
            '秘密日期。 [personal] [13]用户秘密后续联系[personal]。公开结尾。')
    result = _run_reader_js(plain + '\nconst youify = text => text;\nconst text = ' + json.dumps(text) + r''';
      console.log(JSON.stringify({plain: plainLine(text), original: plainLine(text, true),
        stripped: unlabelled(text)}));
    ''')
    assert result['plain'] == result['stripped'] == '公开介绍。公开结尾。'
    assert '[personal]' in result['original'] and '秘密文件' in result['original']


@pytest.mark.parametrize('secret', [
    '秘密的报价是3.5万元[personal]。',
    '“秘密一。秘密二”[personal]。',
    '「秘密一！秘密二？」［sensitive］。',
    '"秘密一。秘密二"[personal]。',
    '秘密网址https://secret.example/path[personal]。',
    '秘密地址secret@example.test[sensitive]。',
    '秘密资料 [同事](people/secret.name.md) 和 `case.txt`[personal]。',
])
def test_reader_privacy_does_not_split_quotes_decimals_or_addresses(secret):
    text = '公开介绍。' + secret + '公开结尾。'
    result = _run_reader_js('const text = ' + json.dumps(text) + r''';
      const passages = [];
      const publicText = privatePassages(text, passage => { passages.push(passage); return ''; });
      console.log(JSON.stringify({publicText, passages}));
    ''')
    assert result['publicText'] == '公开介绍。公开结尾。'
    assert result['passages'] == [secret]


def test_reader_session_search_removes_labelled_passages_before_indexing_and_truncating():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['sessionPreview', 'sessionText', 'sessionExcerpt'])
    result = _run_reader_js(functions + r'''
      const SESSION_TEXT = new Map();
      const r = {path: 'sessions/fixture.md', title: 'Public session',
        session_summary: '公开摘要。秘密摘要[personal]。',
        text: '## What you typed\n公开问题。秘密问题［personal］。\n## Final reply\n秘密答复[sensitive]。公开答复。'};
      console.log(JSON.stringify({text: sessionText(r), excerpt: sessionExcerpt(r, ['秘密'])}));
    ''')
    assert '秘密' not in json.dumps(result, ensure_ascii=False)
    assert result['text']['you'] == '公开问题。'
    assert result['text']['agent'] == '公开答复。'


@pytest.mark.parametrize('secret', [
    '"秘密引语。秘密后半句"[personal]。',
    '“秘密引语！秘密后半句”［sensitive］。',
    '秘密的报价是3.5万元[personal]。',
    '秘密地址secret@example.test[sensitive]。',
    '秘密条件 & 更多条件[personal]。',
])
def test_reader_inline_privacy_wraps_the_full_passage_after_html_escaping(secret):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['esc', 'inline'])
    html = _run_reader_js(functions + r'''
      const youify = text => text, quoteSpans = text => text,
        uncertainCitations = text => text, tetherCitations = text => text;
      console.log(JSON.stringify(inline('公开介绍。' + ''' + json.dumps(secret) + r''' + '公开结尾。', 'fixture.md')));
    ''')
    assert html.count('class="private"') == 1
    assert html.startswith('公开介绍。<span class="private"')
    assert html.endswith('</span>公开结尾。')
    assert not re.search(r'[\[［](personal|sensitive)[\]］]', html)
    from xml.etree.ElementTree import fromstring
    root = fromstring('<p>' + html + '</p>')
    assert len(root) == 1 and root[0].get('class') == 'private'
    assert root.text + root[0].tail == '公开介绍。公开结尾。'


def test_reader_classifies_a_full_session_reply_before_truncating_its_preview():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['sessionFinalReply', 'sessionQuote'])
    result = _run_reader_js(functions + r'''
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children, appendChild() {}});
      const sessionUnquote = text => text, sessionSection = r => r;
      const sessionButton = () => ({});
      const full = '秘密'.repeat(700) + '［personal］。';
      const result = sessionFinalReply(full);
      console.log(JSON.stringify(result.children[1]));
    ''')
    assert result['class'] == 'session-quote private'
    assert len(result['textContent']) == 601
    assert result['sessionFullText'].endswith('［personal］。')


def test_written_thread_dates_and_evidence_backed_request_groups():
    page = TEMPLATE.read_text()
    names = ['writtenDatePattern', 'writtenDates', 'threads', 'listItems', 'isCalm', 'direction', 'projectDirection', 'owing', 'rawSection',
             'threadEntries', 'obligationWords', 'obligationEvidence', 'sameObligation', 'threadGroups']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = _run_reader_js(functions + r'''
      const REM = {as_of: '2026-10-20T12:00:00Z', owner: 'people/avery-lin.md'}, DAY_MS = 86400000;
      const COMMENT = /<!--[\s\S]*?-->/g, calendarDay = value => value.slice(0, 10), daysSince = () => 0;
      let OWING = null;
      const byPath = () => ({title: 'Avery Lin'}), plainLine = text => text, threadWords = text => text;
      let records = [];
      const listedRecords = () => records;
      const entry = (path, text, n = 4, source = 'outlook:aa11bb22cc33') => ({
        path, title: path.startsWith('people') ? 'Theo Park' : 'Northgate University',
        category: path.split('/')[0], text: '# Page\n\n## Open threads\n- ' + text + '\n\n## Sources\n- [' + n + '] ' + source
      });
      records = [entry('people/theo-park.md', 'T3 capstone agreement: Theo asks the user to fill in the collaborator details, sign the execution section and reply all by 2026-10-23 [15][16].', 15),
        entry('orgs/northgate-university.md', 'Northgate asked the user to complete and sign the capstone agreement by 23 October 2026. [32][33]', 32)];
      const a = threadEntries().map(({t, also}) => ({due: t.due, copies: also.length}));
      records = [entry('people/theo-park.md', 'Theo — send the meeting link the user requested on 2026-09-03 [4].'),
        entry('orgs/northgate-university.md', 'The user asked Theo to send a Meet link on Sep 3 [4].'),
        entry('projects/harbour.md', 'The user requested a meeting link on Sept 3; whether it was sent is unknown [4].')];
      const b = threadEntries().map(({t, also}) => ({since: t.since, copies: also.length}));
      records = [entry('orgs/northgate-university.md', 'Mia Chen requested written approval to upload client code to LLMs for planning; no approval is supplied. [43]', 43),
        entry('people/mia-chen.md', 'The team, through Mia Chen, said on 2026-10-17 that written approval is required before uploading client code to LLMs; the user owes the team a decision [2].', 2)];
      const c = threadEntries().map(({r, t, also}) => ({path: r.path, dir: t.dir, copies: also.length}));
      records = [entry('people/theo-park.md', 'Theo Park — sign the agreement by 23 Oct [4].'),
        entry('orgs/northgate-university.md', 'Theo Park — send the invoice for September by 23 Oct [4].')];
      REM.records = [...records, {title: 'Theo Park', category: 'people'}];
      const negative = threadEntries().length;
      records = [entry('people/theo-park.md', 'Theo Park promised on 2026-08-31 to send the first work-package draft covering milestones, staffing, dependencies, delivery, scope and costs [4].'),
        entry('orgs/northgate-university.md', 'Northgate University promised a standalone Work Package draft on 2026-08-31 detailing research objectives, methods, resources, evaluation and acceptance [4].')];
      REM.records = records;
      const evidence = records.map(r => obligationEvidence({r, t: threads(r).items[0]}));
      const overlap = [...evidence[0].words].filter(word => evidence[1].words.has(word)).length;
      const coefficient = overlap / Math.min(...evidence.map(item => item.words.size));
      const workPackage = threadEntries().map(({t, also}) => ({since: t.since, copies: also.length}));
      const undated = sameObligation({...evidence[0], day: ''}, {...evidence[1], day: ''});
      const crossDirection = sameObligation({...evidence[0], dir: 'plain'}, {...evidence[1], dir: 'mine'});
      records = [entry('people/theo-park.md', 'You owe Theo Park a Harbour sprint budget forecast covering staffing allocations [4].'),
        entry('orgs/northgate-university.md', 'You owe Theo Park a Harbour sprint security checklist covering access permissions [4].')];
      REM.records = records;
      const undatedRequests = threadEntries().length;
      const byPerson = ['You owe a reply requested by Theo Park on Sep 3; due October 23, 2026 [4].',
        'You owe a reply requested by Theo Park, due October 23, 2026 [4].'].map(text => threads(entry('people/theo-park.md', text)).items[0].due);
      const dates = writtenDates('23 October 2026; October 23, 2026; 23 Oct; Sep 3; Sept 3; March 3');
      const due = threads(entry('people/theo-park.md', 'The user owes a review, since Sep 3, due October 23, 2026 [4].')).items[0];
      REM.as_of = '2026-01-10T12:00:00Z';
      console.log(JSON.stringify({a, b, c, negative, workPackage, coefficient, undated, crossDirection, undatedRequests,
        byPerson, dates, due: [due.since, due.due], rollover: writtenDates('Dec 20')}));
    ''')
    assert result == {
        'a': [{'due': '2026-10-23', 'copies': 1}],
        'b': [{'since': '2026-09-03', 'copies': 2}],
        'c': [{'path': 'people/mia-chen.md', 'dir': 'mine', 'copies': 1}], 'negative': 2,
        'workPackage': [{'since': '2026-08-31', 'copies': 1}], 'coefficient': 1 / 3,
        'undated': False, 'crossDirection': False, 'undatedRequests': 2,
        'dates': ['2026-10-23', '2026-10-23', '2026-10-23', '2026-09-03', '2026-09-03', '2026-03-03'],
        'due': ['2026-09-03', '2026-10-23'], 'byPerson': ['2026-10-23', '2026-10-23'], 'rollover': ['2025-12-20']}


@pytest.mark.parametrize('blocked', [False, True])
def test_done_threads_filter_today_and_counts_without_changing_record_threads(blocked):
    page = TEMPLATE.read_text()
    names = ['doneKey', 'doneStorageKey', 'threadStorageKey', 'isDone', 'saveThreadState', 'setDone', 'shortHash', 'readerStorage', 'todayEntries', 'threadCounts']
    functions = '\n'.join(re.search(r'(?:async )?function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = _run_reader_js(functions + 'const blocked = ' + json.dumps(blocked) + ';' + r'''
      const REM = {root: '/fixture/notebook', as_of: '2026-10-20T12:00:00Z'}, DAY_MS = 86400000;
      let threadStates = {}, pendingThreads = {}, saved = {}, rendered = 0;
      const navigator = {platform: "test"};
      const localStorage = {setItem: (key, value) => { if (blocked) throw new Error('Storage blocked'); saved[key] = value; }};
      const render = () => rendered++, doneNotice = () => {}, window = {scrollY: 0, scrollTo() {}};
      const document = {getElementById: () => null}, calendarDay = value => value.slice(0, 10);
      const make = (text, dir, due = '', since = '') => ({r: {path: 'people/theo-park.md'}, t: {text, dir, due, since}});
      const entries = [make('You owe the signed agreement', 'mine', '2026-10-18'),
        make('You owe the draft', 'mine', '2026-10-20'), make('They owe a link', 'theirs', '', '2026-10-20'),
        make('Old thread', 'mine', '', '2026-10-19'), make('Future thread', 'mine', '2026-10-23'),
        {...make('Quiet thread', 'theirs', '2026-09-01'), t: {text: 'Quiet thread', dir: 'theirs', due: '2026-09-01', quiet: true}}];
      const threadEntries = () => entries;
      REM.today_queue = [0, 1, 2, 4].map(i => ({key: doneKey(entries[i]), section: 'today'}));
      (async () => {
        const before = todayEntries(entries).length;
        setDone(entries[0], true);
        await Promise.resolve(); await Promise.resolve();
        const marked = {today: todayEntries(entries).length, counts: threadCounts(), saved: Object.values(saved).map(JSON.parse),
          sameTranslation: doneKey({...entries[0], t: {...entries[0].t, originalText: entries[0].t.text, text: '已翻译'}}) === doneKey(entries[0])};
        setDone(entries[0], false);
        await Promise.resolve(); await Promise.resolve();
        console.log(JSON.stringify({before, marked, after: todayEntries(entries).length, open: threadCounts().mine,
          stored: Object.values(saved).map(JSON.parse), rendered, records: entries.length}));
      })();
    ''')
    assert result['before'] == result['after'] == 4
    assert result['marked']['today'] == 3
    assert result['marked']['counts'] == {'mine': 3, 'theirs': 1, 'other': 0, 'quiet': 1, 'open': 4}
    assert result['marked']['saved'] == [] if blocked else len(result['marked']['saved'][0]['states']) == 1
    assert result['marked']['sameTranslation']
    assert result['open'] == 4
    assert result['stored'] == [] if blocked else result['stored'][0]['states'] == {}
    assert result['rendered'] == 2 and result['records'] == 6


@pytest.mark.parametrize('enabled', [True, False])
def test_no_reply_draft_note_shows_the_reason_instead_of_a_pending_draft(enabled):
    function = re.search(r'function draftNote\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js('const REM = ' + json.dumps({'status': {'worker': {'enabled': enabled}}}) + ';\n' + function + r'''
      const el = (tag, attrs) => ({tag, ...attrs});
      console.log(JSON.stringify(draftNote({status: 'no_reply', gist: '需要你到场，已等3天。'})));
    ''')
    assert result['text'] == 'No reply needed: 需要你到场，已等3天。'
    assert result['class'] == 'quiet-line'


def test_no_reply_actions_offer_completion_without_another_reply():
    function = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
                         for name in ['threadActions', 'threadDraft'])
    result = _run_reader_js(function + r'''
      const REM = {drafts: [{status: 'no_reply', provider: 'gmail', thread: 'mail:gmail:pilot'}]};
      const isDone = () => false, setDone = () => {}, primaryAction = () => ({text: 'Draft the reply'});
      const obligationEvidence = () => ({ids: new Set(['thread:gmail:mail:gmail:pilot'])});
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      console.log(JSON.stringify(threadActions({t: {}})));
    ''')
    assert [node['text'] for node in result['children'] if node] == ['Mark done']


@pytest.mark.parametrize('renderer', ['threadRow'])
def test_no_reply_reason_is_visible_in_open_threads_and_the_person_ledger(renderer):
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
                          for name in [renderer, 'draftNote'])
    result = _run_reader_js(functions + r'''
      const REM = {owner: 'people/owner.md'}, DIRECTION_LABEL = {mine: 'Waiting on you'};
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const draft = {status: 'no_reply', gist: '需要你到场，已等3天。'}, threadDraft = () => draft;
      const inline = text => text, threadWords = text => text, withoutDateClutter = text => text, capFirst = text => text, privateFallback = node => node;
      const threadActions = () => null, age = () => '', threadAge = () => '', blockerTag = () => null, daysSince = () => 1;
      const r = {path: 'people/fern.md'}, thread = {text: 'You owe Fern a response.', dir: 'mine'};
    ''' + f'console.log(JSON.stringify({renderer}(r, thread, false)));')
    assert 'No reply needed: 需要你到场，已等3天。' in json.dumps(result, ensure_ascii=False)


def test_thread_actions_show_drafts_and_discarded_state_without_copy_prompt():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['threadActions', 'primaryAction', 'threadUrl', 'mailtoLink', 'draftNowButton', 'threadDraft', 'draftNote', 'replyDraftCard'])
    result = _run_reader_js(functions + "\nconst icon = () => null, groupLate = () => 0, liveHere = () => !!REM.live; const translationPending = () => false; const kindBadge = () => null, threadKind = () => null;\n" + r'''
      const REM = {live: true, drafts: [{thread: 'mail:gmail:pilot', provider: 'gmail', status: 'prepared',
        to: 'avery@example.com', subject: 'Re: Pilot', body: 'I will review the pilot.'}], status: {worker: {enabled: true}}};
      const isDone = () => false, setDone = () => {}, obligationEvidence = () => ({ids: new Set(['thread:gmail:mail:gmail:pilot'])});
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const mailbox = address => ({address, name: 'Avery'}), personByAddress = () => null;
      const href = r => '#r=' + r.path;
      let contact = {address: 'avery@example.com', subject: 'Pilot', name: 'Avery'};
      const threadContact = () => contact;
      const entry = {r: {path: 'people/avery.md'}, t: {dir: 'mine'}};
      const prepared = replyDraftCard(threadDraft(entry)), actions = threadActions(entry);
      contact = null;
      const fallback = threadActions(entry);
      REM.drafts[0].status = 'discarded';
      const discarded = draftNote(threadDraft(entry));
      REM.drafts[0].status = 'pending';
      const pending = draftNote(threadDraft(entry));
      REM.status.worker.enabled = false;
      const paused = draftNote(threadDraft(entry));
      REM.drafts[0].status = 'sent';
      console.log(JSON.stringify({prepared, actions, fallback, discarded, pending, paused, sent: draftNote(threadDraft(entry))}));
    ''')
    assert result['prepared']['class'] == 'mailcard'
    actions = result['prepared']['children'][4]['children']  # [head, body, why, choices, actions, status]
    # Send is the one green; writing full screen, editing in Gmail and Skip wait behind 更多 (D-120).
    buttons = [actions[-1], *actions[0]['children'][1]['children']]
    assert [button['text'] for button in buttons if button['tag'] == 'button'] == [
        'Send', 'Write full screen', 'Edit in Gmail', 'Skip']
    assert result['actions']['children'][0]['href'] == '#r=people/avery.md&h=open-threads'
    assert result['actions']['children'][0]['text'] == 'Open the page'  # no archived thread identity
    assert result['actions']['children'][1]['text'] == 'Mark done'
    assert result['fallback']['children'][0]['text'] == 'Open the page'
    assert result['fallback']['children'][0]['href'] == '#r=people/avery.md&h=open-threads'
    assert result['discarded']['text'] == 'Draft discarded'
    assert result['pending']['text'] == 'Reply draft queued for tonight'
    assert result['paused']['text'] == 'Reply draft pending — background updates off'
    assert result['sent']['text'] == 'Sent'
    assert 'Copy prompt' not in json.dumps(result)


def test_person_card_prepared_draft_replaces_primary_action_with_mailcard():
    page = TEMPLATE.read_text()
    functions = re.search(r'const STEPS = .*?;', page).group(0) + '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['personCard', 'cardHead', 'cardItem', 'stripMarksDone', 'ownerLine', 'cardDraft', 'stepAction', 'notDoneAction', 'cardStep', 'groupStep', 'mailboxLink', 'threadUrl',
                                       'taskResult', 'threadDraft', 'draftNote', 'replyDraftCard', 'draftNowButton', 'mailtoLink'])
    result = _run_reader_js(functions + "\nconst icon = () => null, groupLate = () => 0, liveHere = () => !!REM.live; const translationPending = () => false; const kindBadge = () => null, threadKind = () => ({kind: 'gmail', channel: 'Gmail', thread: 'mail:gmail:pilot', mail: true});\n" + r'''
      const draft = {id: 'pilot-reply', thread: 'mail:gmail:pilot', provider: 'gmail', status: 'prepared',
        to: 'avery@example.com', from: 'owner@example.com', subject: 'Re: Pilot',
        body: 'I will send the review tomorrow.', gist: '明天发出审阅意见。', why: '先确认收到，再给出明确的回复时间。'};
      const REM = {live: true, as_of: '2026-10-30', drafts: [draft], today_queue: [{key: 'avery', keys: ['avery'], reply: {state: 'queued', provider: 'gmail', thread: 'mail:gmail:pilot'}}]};
      const doneKey = () => 'avery';
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const isDone = () => false, setDone = () => {}, obligationEvidence = () => ({ids: new Set(['thread:gmail:mail:gmail:pilot'])});
      const mailbox = address => ({address, name: 'Avery'}), personByAddress = () => null;
      const threadContact = () => ({address: draft.to, name: 'Avery', subject: 'Pilot'});
      const morningWords = () => ({words: 'Review the pilot.', context: ''});
      const contactFields = () => [], company = () => '', calendarDay = day => day;
      const href = r => '#r=' + r.path, threadWho = r => r.title, blockerTag = () => null, alsoOn = () => null;
      const queuedReply = () => REM.today_queue[0].reply, looksDone = () => false, approvalTask = () => null, overdueDays = () => 0;
      const handedLine = () => null, rowTask = () => null, handOff = () => null;
      const firstName = r => r.title.split(' ')[0], threadAge = () => 'due today', CHECK_ICON = '', roleSummary = text => text;
      const entry = {r: {path: 'people/avery.md', title: 'Avery Lin'}, t: {dir: 'mine', text: 'Review the pilot.'}};
      const group = {r: entry.r, entries: [entry]};
      const prepared = personCard(group, true);
      REM.drafts = [];
      console.log(JSON.stringify({prepared, withoutDraft: personCard(group, true)}));
    ''')
    card = result['prepared']
    assert card['data-step'] == 'send'
    mail = card['children'][2]['children'][1]
    assert mail['class'] == 'mailcard'
    assert [pill['text'] for pill in mail['children'][0]['children'][0]['children']] == ['Mail', 'Lark', 'WhatsApp']
    assert mail['children'][0]['children'][1]['children'][0]['text'] == 'To'
    # D-10: the CC row is always there, and says when nobody is copied.
    assert [cell['text'] for cell in mail['children'][0]['children'][2]['children']] == ['CC', 'No one']
    assert mail['children'][0]['children'][3]['children'][1]['text'] == 'Re: Pilot'
    assert mail['children'][1]['children'][0]['text'] == 'I will send the review tomorrow.'
    gist = mail['children'][1]['children'][1]
    assert gist['class'] == 'mail-gist' and gist['children'][1]['text'] == '明天发出审阅意见。'
    # Build 3b review: Why this reply sits under the owner's-language reading, beside the letter.
    why = gist['children'][2]
    assert why['class'] == 'mail-why' and '先确认收到，再给出明确的回复时间。' in why['children'] and mail['children'][2] is None
    assert mail['children'][3] is None  # no question for the owner, so no choice rows above Send
    assert mail['children'][4]['children'][-1]['text'] == 'Send'
    assert 'mailto:' not in json.dumps(card)
    # Without a draft the primary drafts in place using its archived identity.
    actions = result['withoutDraft']['children'][3]['children'][0]
    assert actions['class'] == 'draft-now' and actions['children'][0]['text'] == 'Draft now'
    assert actions['children'][0]['class'] == 'btn-act'
    assert 'mailto:' not in json.dumps(actions)
    assert 'Copy prompt' not in json.dumps(result)


def _words(node):
    """The words a serialised reader node reads as, children in order (the poster splits its sentence)."""
    if isinstance(node, str):
        return node
    return (node or {}).get('text', '') + ''.join(_words(child) for child in (node or {}).get('children', []))


def test_night_card_counts_people_and_burns_each_face_by_days_overdue_and_translates_find():
    """N3 (D-123): the count of people waiting is the display element; each face wears a fuse burnt by days overdue."""
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['nightCard', 'faceStrip', 'fusedFace', 'groupLate', 'todayCrumb'])
    result = _run_reader_js('(() => { let uiLanguage = "en";\n' + interface + 'const RING = 314.16;\n' + functions + r'''
      const REM = {as_of: '2026-10-20'}, calendarDay = day => day, threadWho = r => r.title, threadAge = () => 'new', icon = () => null, nightChart = () => null;
      const overdueDays = thread => thread.due && thread.due < REM.as_of ? Math.round((Date.parse(REM.as_of) - Date.parse(thread.due)) / 86400000) : 0;
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children: children.filter(Boolean)});
      const face = name => ({tag: 'span', text: name.slice(0, 2), children: [], append(node) { this.children.push(node); }});
      const groups = [{r: {path: 'a', title: 'Ada'}, entries: [{t: {since: '2026-10-20'}}, {t: {due: '2026-10-18'}}]},
        {r: {path: 'b', title: 'Bea'}, entries: [{t: {due: '2026-10-19'}}, {t: {due: '2026-10-23'}}]},
        {r: {path: 'c', title: 'Cy'}, entries: [{t: {since: '2026-10-20'}}]}];
      const card = nightCard(groups, 'b'), quiet = nightCard([], null);
      const faces = card.children[0].children[0].children[1].children, date = todayCrumb();
      uiLanguage = 'zh';
      const zh = nightCard(groups, 'b');
      console.log(JSON.stringify({count: card.children[0].children[0].children[0].children.map(c => c.text),
        faces: faces.map(f => [f['aria-pressed'], f.children[1].text, f.children[1].class, f.children[0].children[0].html.includes('class="burn"')]),
        quiet: quiet.children[0].children[0].children[0].children.map(c => c.text), solo: card.children[0].class,
        zh: zh.children[0].children[0].children[0].children.map(c => c.text), zhLate: zh.children[0].children[0].children[1].children[0].children[1].text,
        date, find: t('Find')}));
    })();''')
    assert result['count'] == ['3', 'people waiting on you']
    # Days overdue in red under the face, the ring burnt; a face with nothing overdue says its age and has no burn.
    assert result['faces'] == [['false', '2 d', 'dd late', True], ['true', '1 d', 'dd late', True], ['false', 'new', 'dd', False]]
    assert result['quiet'] == ['0', 'Nobody is waiting on you today.']
    assert result['solo'] == 'nb solo'  # no logs and no drafts: no chart is drawn, the faces take the card
    assert result['zh'] == ['3', '人在等你'] and result['zhLate'] == '2 天'
    assert result['date'] == 'Tue, 20 October'
    assert result['find'] == '查找'


def test_seven_distinct_review_threads_keep_overdue_due_soon_and_new_counts():
    """The round-seven browser fixture shares a citation, but has seven requests."""
    page = TEMPLATE.read_text()
    names = ['writtenDatePattern', 'writtenDates', 'threads', 'listItems', 'isCalm',
             'direction', 'owing', 'rawSection', 'threadEntries', 'obligationWords',
             'obligationEvidence', 'sameObligation', 'threadGroups', 'todayEntries', 'personGroups', 'nightCard', 'faceStrip', 'fusedFace', 'groupLate']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = _run_reader_js(functions + r'''
      const DAY_MS = 86400000, COMMENT = /<!--[\s\S]*?-->/g;
      const REM = {as_of: '2026-10-20T12:00:00Z', records: []};
      const calendarDay = value => value.slice(0, 10), daysSince = () => 0;
      let OWING = null;
      const byPath = path => REM.records.find(r => r.path === path), listedRecords = () => REM.records;
      const plainLine = text => text, threadWords = text => text, isDone = () => false;
      const threadWho = r => r.title, RING = 314.16;
      const icon = () => null, nightChart = () => null, threadAge = () => 'new', overdueDays = () => 0;
      const face = name => ({tag: 'span', text: name, append() {}});
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children: children.filter(Boolean)});
      const pairs = ['budget forecast', 'product outline', 'contract revision', 'receipt bundle', 'design proposal', 'renewal summary'];
      const lines = pairs.map((words, i) => '- You owe Mara a review of the ' + words
        + '; due ' + (i === 0 ? '2026-10-18' : '2026-10-20') + ' [4].');
      lines.push('- You owe Mara an access decision; since 2026-10-20 [4].');
      REM.records = [{path: 'people/mara-ostrowski.md', title: 'Mara Ostrowski', category: 'people',
        text: '# Mara\n\n## Open threads\n' + lines.join('\n') + '\n\n## Sources\n- [4] outlook:shared'}];
      const entries = threadEntries(), doneKey = entry => entry.r.path + '\n' + entry.t.text;
      REM.today_queue = entries.map(entry => ({key: doneKey(entry), section: 'today'}));
      const today = todayEntries(entries);
      console.log(JSON.stringify({parsed: threads(REM.records[0]).items.length,
        merged: entries.length, today: today.length,
        headline: nightCard(personGroups(today), null).children[0].children[0].children[0]}));
    ''')
    # Seven asks from one person are one card: one person is waiting.
    assert _words(result.pop('headline')) == '1person waiting on you'
    assert result == {'parsed': 7, 'merged': 7, 'today': 7}


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_mapped_gaps_keep_count_while_written_pages_name_remaining_sections(language):
    page = TEMPLATE.read_text()
    notice = page[page.index('  if (k.missing.length) {'):page.index('\n  const foot = el("div", { class: "page-foot"')]
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js('UI.zh = ' + ui + '; uiLanguage = ' + json.dumps(language) + ';\n' + r'''
      const REM = {status: {worker: {enabled: true}}}, r = {}, deep = {};
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children}), youify = text => text;
      const rows = [], main = {insertBefore: node => rows.push(node)}, column = {appendChild: node => rows.push(node)};
      const k = {status: 'Mapped', missing: ['Insight', 'Who they are']};
    ''' + notice + r'''
      k.status = 'Partly investigated';
    ''' + notice + r'''
      console.log(JSON.stringify(rows));
    ''')
    mapped, written = result
    assert mapped['children'][0]['text'] == ('此页已排入今晚队列' if language == 'zh' else 'Page queued for tonight')
    assert mapped['children'][-1]['text'] == (
        '调查后会写出 2 个章节。' if language == 'zh'
        else '2 sections will be written when it is investigated.')
    assert written['children'][-1]['text'] == (
        '仍不明确：Insight, Who they are.' if language == 'zh' else 'Still unknown: Insight, Who they are.')


def test_today_includes_three_day_boundary_and_preserves_shared_page_context():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['todayEntries', 'threadAge', 'cardHead', 'cardItem', 'stripMarksDone', 'morningWords', 'withoutDateClutter'])
    result = _run_reader_js(functions + "\nconst icon = () => null, groupLate = () => 0, liveHere = () => !!REM.live; const translationPending = () => false; const kindBadge = () => null, threadKind = () => null;\n" + r'''
      const threadWho = r => r.title, overdueDays = () => 0;
      const REM = {as_of: '2026-10-30'}, DAY_MS = 86400000, calendarDay = day => day;
      const r = {path: 'people/theo-park.md', title: 'Theo Park'}, also = [{path: 'orgs/northgate-university.md'}];
      const make = (text, due = '', since = '', extra = {}) => ({r, also, t: {text, due, since, dir: 'mine', ...extra}});
      const entries = [make('overdue', '2026-10-29'), make('today', '2026-10-30'),
        make('three days', '2026-11-02'), make('four days', '2026-11-03'),
        make('new', '', '2026-10-30', {dir: 'theirs'}), make('old', '', '2026-10-29'),
        make('done', '2026-10-30'), make('quiet', '2026-10-01', '', {quiet: true}),
        make('undirected', '2026-10-30', '', {dir: 'plain'})];
      const isDone = entry => entry.t.text === 'done', doneKey = entry => entry.r.path + '\n' + entry.t.text;
      REM.today_queue = [0, 1, 2, 4, 6].map(i => ({key: doneKey(entries[i]), section: 'today'}));
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children, classList: {add() {}}}), href = page => page.path;
      const capFirst = text => text, threadWords = text => text, plainLine = text => text;
      const privateFallback = node => node, inline = text => text, threadActions = () => null;
      const contactFields = () => [], company = () => '', blockerTag = () => null;
      const threadDraft = () => null, draftNote = () => null;
      const age = () => '', taskResult = () => null, roleSummary = text => text, CHECK_ICON = '';
      const handedLine = () => null, rowTask = () => null, handOff = () => null; const dueLabel = thread => 'due ' + thread.due, alsoOn = pages => ({also: pages});
      const quoted = make('You owe Theo a Letter of Support draft; “Please include the contribution details.” [4].', '2026-11-02');
      const dated = make('Review the pilot (2026-10-30) — due 2026-11-02, overdue; open as of 2026-10-30', '2026-11-02');
      console.log(JSON.stringify({selected: todayEntries(entries).map(entry => entry.t.text),
        row: cardHead({r, entries: [entries[2]]}, 0), also: cardItem(entries[2], false), quoted: cardItem(quoted, false),
        dated: cardItem(dated, false), datedHead: cardHead({r, entries: [dated]}, 0)}));
    ''')
    assert result['selected'] == ['overdue', 'today', 'three days', 'new']
    assert result['row']['children'][4]['text'] == 'due 2026-11-02'  # after the card's hover actions
    assert result['also']['children'][2]['children'][1]['also'] == [{'path': 'orgs/northgate-university.md'}]
    quoted = result['quoted']['children']
    assert 'Letter of Support draft' in quoted[0]['text']
    assert '“Please include the contribution details.”' in quoted[0]['text']
    assert quoted[0]['children'][0]['html'] == '[4]'
    assert result['dated']['children'][0]['text'] == 'Review the pilot'
    assert result['datedHead']['children'][4]['text'] == 'due 2026-11-02'


def test_claim_values_use_only_current_cached_facts_for_chinese_after():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['parseFacts', 'topLevelParts', 'rawSection', 'factText', 'plainLine',
                                       'originalMark', 'claimValue', 'overnightChange', 'changeCard'])
    result = _run_reader_js(functions + r'''
      UI.zh = {Original: '原文', 'No Chinese translation yet; showing original': '尚无中文译文，显示原文', role: '职位'};
      const PARSED_FACTS = new Map(), COMMENT = /<!--[\s\S]*?-->/g, youify = text => text;
      const translationPending = () => false; const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const r = {path: 'people/mara-ostrowski.md', title: 'Mara Ostrowski', readLanguage: '',
        text: '# Mara Ostrowski\n\n## Facts\n- Role: **Head of Partnerships** (work); Pilot lead [2]\n',
        translations: {zh: '# Mara Ostrowski\n\n## Facts\n- Role: 合作负责人（工作）; 试点负责人 [2]\n'}};
      const byPath = () => r, href = r => '#r=' + r.path;
      const claim = {record: r.path, field: 'role', before: 'Partnerships lead',
        after: 'Head of Partnerships (work); Pilot lead', sources: ['2']};
      uiLanguage = 'zh';
      const translated = overnightChange(claim), card = changeCard(claim);
      const stale = claimValue({...claim, after: 'Old role'}, r, true);
      const absent = claimValue(claim, {...r, translations: {}}, true);
      const missingField = claimValue(claim, {...r, translations: {zh: '## Facts\n- Email: mara@fernhill.example'}}, true);
      uiLanguage = 'en';
      const english = overnightChange(claim);
      console.log(JSON.stringify({translated, card, stale, absent, missingField, english}));
    ''')
    before, _, after = result['translated']['children'][2]['children']
    # The 原文 mark sits beside the struck value, not inside the strike-through.
    assert before['children'][0] == {'tag': 'del', 'text': 'Partnerships lead', 'children': []}
    assert before['children'][1] == {'tag': 'span', 'class': 'lang-status', 'text': '原文',
                                      'title': '尚无中文译文，显示原文', 'children': []}
    assert after['children'] == [{'tag': 'span', 'text': '合作负责人 (工作); 试点负责人', 'children': []}, None]
    assert result['translated']['children'][1]['text'] == ' · 职位'
    assert result['card']['children'][2]['children'][1] == before
    assert result['card']['children'][3]['children'][1] == after
    for key in ['stale', 'absent', 'missingField']:
        assert result[key]['children'][1]['text'] == '原文'
    assert result['stale']['children'][0]['text'] == 'Old role'
    assert result['absent']['children'][0]['text'] == 'Head of Partnerships (work); Pilot lead'
    en_before, _, en_after = result['english']['children'][2]['children']
    assert en_before['children'] == [{'tag': 'del', 'text': 'Partnerships lead', 'children': []}, None]
    assert en_after['children'] == [{'tag': 'span', 'text': 'Head of Partnerships (work); Pilot lead', 'children': []}, None]
    assert '原文' not in json.dumps(result['english'], ensure_ascii=False)


def test_unknown_is_localised_only_on_display_paths():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['esc', 'inline', 'plainLine', 'displayLine', 'parseFacts', 'topLevelParts', 'rawSection'])
    result = _run_reader_js(functions + r'''
      UI.zh = {Unknown: '未知'};
      const PARSED_FACTS = new Map(), COMMENT = /<!--[\s\S]*?-->/g;
      const youify = text => text, quoteSpans = text => text,
        uncertainCitations = text => text, tetherCitations = text => text, shortHash = text => text;
      const text = '审阅结果：Unknown。是否已回复仍为 Unknown。';
      const r = {path: 'people/mara-ostrowski.md', text: '## Facts\n- Phone: Unknown\n'};
      uiLanguage = 'zh';
      const zh = {inline: inline(text), plain: displayLine(text), parsed: parseFacts(r).get('Phone'),
        raw: plainLine(text), code: inline('`Unknown`')};
      uiLanguage = 'en';
      console.log(JSON.stringify({zh, en: [inline(text), displayLine(text)], text, markdown: r.text}));
    ''')
    original = '审阅结果：Unknown。是否已回复仍为 Unknown。'
    assert result['zh'] == {'inline': '审阅结果：未知。是否已回复仍为 未知。',
                            'plain': '审阅结果：未知。是否已回复仍为 未知。',
                            'parsed': [], 'raw': original, 'code': '<code>Unknown</code>'}
    assert result['en'] == [original, original] and result['text'] == original
    assert result['markdown'] == '## Facts\n- Phone: Unknown\n'


def test_summary_line_strips_only_leading_insight_labels():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['plainLine', 'displayLine', 'summaryLine'])
    result = _run_reader_js(functions + r'''
      const youify = text => text;
      const labels = ['Now:', '**Now:**', '**Pattern**:', 'At stake:', 'Changed:', '现在：', '规律：', '关键所在：', '变化：'];
      console.log(JSON.stringify({stripped: labels.map(label => summaryLine('- ' + label + ' waiting on review [2]')),
        kept: summaryLine('Discuss the Pattern: now'), raw: plainLine('Now: waiting on review')}));
    ''')
    assert result['stripped'] == ['waiting on review'] * 9
    assert result['kept'] == 'Discuss the Pattern: now'
    assert result['raw'] == 'Now: waiting on review'


def test_dates_inside_a_sentence_use_the_pages_calendar_format():
    """The org lede printed "allocated the teams on 2026-09-23" on a page that says 10月29日 everywhere else."""
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['datesInProse', 'calendarDate', 'calendarDay'])
    result = _run_reader_js(functions + r'''
      const REM = {as_of: '2026-11-09T10:00:00Z', status: {timezone: 'UTC'}};
      uiLanguage = 'zh';
      const english = datesInProse('The university allocated the teams on 2026-09-23 and met on 2025-11-29.');
      const chinese = datesInProse('学校在 2026-09-23 分好了组。');
      uiLanguage = 'en';
      console.log(JSON.stringify([english, chinese, datesInProse('Allocated on 2026-11-08.')]));
    ''')
    # One language per line: the date speaks the sentence's language, whatever the interface is in.
    assert result[0] == 'The university allocated the teams on Sep 23 and met on Nov 29, 2025.'
    assert result[1] == '学校在 9月23日 分好了组。'
    assert result[2] == 'Allocated on Nov 8.'  # a date in a sentence is never "Yesterday"


def test_role_lede_is_the_title_and_parse_facts_splits_like_facts_py():
    """The lede read "Events Coordinator (Entrepreneurship; email signature through 2026-10-29) +1"."""
    from connectonion.rem.facts import values
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['parseFacts', 'topLevelParts', 'roleLede', 'plainLine'])
    line = 'Events Coordinator (Entrepreneurship; email signature through 2026-10-29); Mentor [3]'
    result = _run_reader_js(functions + r'''
      const PARSED_FACTS = new Map(), el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: children.filter(Boolean)});
      const rawSection = page => page.text, inline = text => text, youify = text => text, roleSummary = () => null;
      const r = {path: 'people/tamsin.md', text: '- Role: ' + LINE + '\n'};
      const items = parseFacts(r).get('Role');
      console.log(JSON.stringify({items, lede: roleLede(items, LINE, r.path)}));
    '''.replace('LINE + ', json.dumps(line) + ' + ').replace('items, LINE,', 'items, ' + json.dumps(line) + ','))
    assert [{k: i[k] for k in ('value', 'qualifier')} for i in result['items']] == [{k: v[k] for k in ('value', 'qualifier')} for v in values(line)]
    assert result['lede']['children'][0]['html'] == 'Events Coordinator (Entrepreneurship)'
    assert result['lede']['children'][1]['text'] == ' +1'
    assert 'email signature through 2026-10-29' in result['lede']['title']


def test_role_lede_keeps_when_a_role_ended_or_started():
    """"Product Owner (until 2025-06); Advisor" read "Product Owner +1": a past role as if current."""
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['topLevelParts', 'roleLede', 'plainLine'])
    result = _run_reader_js(functions + r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: children.filter(Boolean)});
      const inline = text => text, youify = text => text, roleSummary = () => null;
      const lede = (value, qualifier) => roleLede([{value, qualifier}, {value: 'Advisor', qualifier: ''}], value, '').children[0].html;
      console.log(JSON.stringify([lede('Product Owner', 'until 2025-06'), lede('Engineer', 'since 2024'), lede('Founder', 'former'),
        lede('Mentor', '2019–2021'), lede('Events Coordinator', 'Entrepreneurship; email signature through 2026-10-29'), lede('Lead', 'observed in mail')]));
    ''')
    assert result == ['Product Owner (until 2025-06)', 'Engineer (since 2024)', 'Founder (former)', 'Mentor (2019–2021)',
                      'Events Coordinator (Entrepreneurship)', 'Lead']


def test_chinese_interface_never_assumes_a_single_persons_gender():
    """"他说过的话" headed a woman's quotes. A single person is 对方 (or their name), never 他/她;
    the words that only look gendered (其他, 他人, 他们 for a plural) are allowed."""
    page = TEMPLATE.read_text()
    table = page[page.index('const UI = {'):page.index('function t(')]
    values = re.findall(r'"(?:[^"\\]|\\.)*":\s*"((?:[^"\\]|\\.)*)"', table)
    allowed = re.compile(r'其他|他人|他们|她们')
    gendered = [value for value in values if re.search(r'[他她]', allowed.sub('', value))]
    assert gendered == [], gendered


def test_role_summary_shows_first_and_count_with_full_title():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['roleSummary', 'topLevelParts', 'plainLine'])
    result = _run_reader_js(functions + r'''
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children});
      const youify = text => text, inline = text => text, privateFallback = node => node;
      const roles = 'Head of Partnerships; Pilot lead; Research liaison';
      console.log(JSON.stringify([roleSummary(roles, ''), roleSummary('Pilot lead', ''),
        roleSummary('Public role; Secret role [sensitive]', ''),
        roleSummary('Events coordinator (Founders space; Startup week); Mentor; Judge; Panel host', '')]));
    ''')
    assert result[0]['title'] == 'Head of Partnerships; Pilot lead; Research liaison'
    assert result[0]['children'][0]['html'] == 'Head of Partnerships'
    assert result[0]['children'][1]['text'] == ' +2'  # neutral: no word in either language (one language per line)
    # A semicolon inside brackets belongs to its role: the first role is shown whole, never cut mid-parenthesis.
    assert result[3]['children'][0]['html'] == 'Events coordinator (Founders space; Startup week)'
    assert result[3]['children'][1]['text'] == ' +3'
    assert result[0]['children'][1]['class'] == 'role-more'
    assert result[1]['children'][1] is None
    assert result[2]['title'] == ''  # No private words in a tooltip.
    assert '[sensitive]' in result[2]['children'][0]['html']


def test_category_lede_joins_counts_after_translated_punctuation():
    page = TEMPLATE.read_text()
    function = re.search(r'function ledeSeparator\(.*?\n\}', page, re.S).group(0)
    result = _run_reader_js(function + r'''
      const lines = ['这是谁？上次聊到哪了？', '已完成。', '怎么做！', 'Who is this?', 'Written.', 'Ready!', '人物'];
      uiLanguage = 'zh'; const zh = lines.map(text => text + ledeSeparator(text) + '已撰写 84 / 84 人');
      uiLanguage = 'en'; const en = ['Who is this?', 'People'].map(text => text + ledeSeparator(text) + '84 written');
      console.log(JSON.stringify({zh, en}));
    ''')
    assert result['zh'][0] == '这是谁？上次聊到哪了？ 已撰写 84 / 84 人'
    assert all(' · ' not in line for line in result['zh'][:-1])
    assert result['zh'][-1] == '人物 · 已撰写 84 / 84 人'
    assert result['en'] == ['Who is this? 84 written', 'People. 84 written']


def test_all_builtin_facts_and_sheet_labels_have_chinese_entries():
    page = TEMPLATE.read_text()
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    labels = re.search(r'const FACT_LABELS = (\{.*?\n\});', page, re.S).group(1)
    columns = re.search(r'const COLUMNS = (\{.*?\n\});', page, re.S).group(1)
    # Column rendering closures are defined but never called here.
    result = _run_reader_js('UI.zh = ' + ui + '; const FACT_LABELS = ' + labels + '; const COLUMNS = ' + columns + r''';
      const labels = [...new Set([...Object.values(FACT_LABELS).flat(),
        ...Object.values(COLUMNS).flat().map(column => column.label), 'Facts', '— not found'])];
      uiLanguage = 'zh';
      console.log(JSON.stringify(labels.filter(label => /[A-Za-z]/.test(t(label)))));
    ''')
    assert result == []


def test_changed_role_keeps_full_list_tooltip_inside_change_tooltip():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['personSub', 'roleSummary', 'roleLede', 'topLevelParts', 'changedValue', 'factText', 'plainLine'])
    result = _run_reader_js(functions + r"""
      const role = '合作负责人; 试点负责人; 研究联络人', original = 'Head of Partnerships; Pilot lead; Research liaison';
      const r = {path: 'people/mara-ostrowski.md'};
      const facts = () => ({role}), personOrg = () => null, personProject = () => null, knownValue = Boolean;
      const youify = text => text, inline = text => text, privateFallback = node => node;
      const parseFacts = () => new Map([['Role', original.split('; ').map(value => ({value, qualifier: ''}))]]);
      const firstBuild = () => false; const memoryPass = {claims: [{record: r.path, field: 'role', before: 'Partnerships lead', after: original}]};
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        childNodes: children, classList: {add() {}},
        appendChild(node) { this.children.push(node); }, append(text) { this.children.push(text); }});
      console.log(JSON.stringify(personSub(r)));
    """)
    changed = result['children'][0]
    compact_role = changed['children'][0]
    assert changed['title'].startswith('Changed last night:')
    assert compact_role['title'] == '合作负责人; 试点负责人; 研究联络人'


@pytest.mark.parametrize('value, tail', [
    ('Head of the Pilot Programme', 'Programme'), ('试点项目负责人', '人'), ('合作负责人。', '人。'),
])
def test_fact_citations_stay_with_the_last_word_or_chinese_character(value, tail):
    page = TEMPLATE.read_text()
    function = re.search(r'function factValue\(.*?\n\}', page, re.S).group(0)
    result = _run_reader_js(function + r'''
      const inline = text => text, softBreaks = node => node;
      const citeChip = n => '<a class="cite">' + n + '</a>';
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        get firstChild() { return this.children[0]; }, get childNodes() { return this.children; },
        appendChild(node) { this.children.push(node); }});
      const NodeFilter = {SHOW_TEXT: 4};
      const document = {
        createTreeWalker(node) {
          const text = {data: node.html, parentElement: {closest: () => null}};
          let seen = false;
          return {currentNode: text, nextNode() { if (seen) return false; seen = true; return true; }};
        },
        createRange() {
          let text, offset;
          return {setStart(node, start) { text = node; offset = start; }, setEnd() {},
            extractContents() { return text.data.slice(offset); }};
        }
      };
      console.log(JSON.stringify(factValue({value: ''' + json.dumps(value) + r''', citations: ['2'], qualifier: ''}, 'people/theo-park.md')));
    ''')
    tether = result['children'][-1]
    assert tether['class'] == 'fact-tail'
    assert tether['children'][0] == tail
    assert tether['children'][1]['html'] == '<a class="cite">2</a>'
    assert '.fact-tail { white-space: nowrap; }' in page


def test_cached_chinese_facts_reach_every_compact_value_path(tmp_path, monkeypatch):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    from connectonion.rem.reader import snapshot

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    data = snapshot(build(tmp_path / 'rem', datetime(2026, 10, 20, 12, tzinfo=timezone.utc), zh=True))
    mara = next(r for r in data['records'] if r['path'] == 'people/mara-ostrowski.md')
    # An English index and a previously selected English page must not override the interface's values.
    mara['shown'] = ''
    mara['index'] = {'role': 'Old role', 'location': 'Old harbour town'}
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in [
        'parseFacts', 'topLevelParts', 'rawSection', 'facts', 'contactFields', 'company', 'contactStrip', 'personSub', 'roleLede', 'personOrg', 'personProject',
        'factList', 'peopleCardMeta', 'roleSummary', 'topLevelParts', 'plainLine', 'threadDate', 'fmtDate', 'calendarDay', 'threadWho', 'threadAge', 'cardHead', 'stripMarksDone', 'translatedRelationBasis',
        'relationCard', 'localizedRelation', 'resolve', 'originalMark'])
    labels = page[page.index('const FACT_LABELS ='):page.index('function legacyFact(')]
    columns = re.search(r'const COLUMNS = (\{.*?\n\});', page, re.S).group(0)
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js(functions + "\nconst icon = () => null, groupLate = () => 0, liveHere = () => !!REM.live; const translationPending = () => false; const kindBadge = () => null, threadKind = () => null;\n" + labels + columns + '\nUI.zh = ' + ui + r''';
      const PARSED_FACTS = new Map(), FACTS = new Map(), COMMENT = /<!--[\s\S]*?-->/g;
      const r = ''' + json.dumps(mara) + r''';
      const REM = {as_of: '2026-10-20'};
      const known = () => ({last: '', summary: ''}), section = () => null, historyItems = () => [];
      const listItems = () => [], threads = () => ({items: [], calm: false});
      const youify = text => text, inline = text => text, softBreaks = node => node, privateFallback = node => node;
      const changedValue = node => node, mappedContact = () => false, legacyFact = () => [], knownValue = Boolean;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        get childNodes() { return this.children; },
        get textContent() { return (this.text || this.html || '') + this.children.map(n => typeof n === 'string' ? n : n?.textContent || '').join(''); },
        appendChild(node) { this.children.push(node); }, append(...nodes) { this.children.push(...nodes); },
        querySelectorAll() { return []; }, querySelector() { return null; }});
      const panel = (title, children) => el('section', {title}, children);
      const factValue = item => el('span', {text: item.value});
      const textCell = text => el('span', {text}), dateCell = () => null;
      const href = r => r.path, singular = () => '', byPath = path => path === r.path ? r : null;
      const morningWords = () => ({words: '', context: ''}), threadActions = () => null, alsoOn = () => null;
      const age = () => '', blockerTag = () => null, threadDraft = () => null, draftNote = () => null;
      const english = facts(r);
      uiLanguage = 'zh';
      const f = facts(r), role = COLUMNS.people.find(c => c.key === 'role').cell(r, f);
      const relation = relationCard(localizedRelation({path: r.path, via: r.path, kind: 'linked',
        basis: 'Role: Head of Partnerships', sources: []}, 'orgs/fernhill-labs.md'), 'orgs/fernhill-labs.md');
      console.log(JSON.stringify({english: english.role, role: f.role, location: f.location,
        paths: {facts: factList(r), subtitle: personSub(r), contact: contactStrip(r), table: role,
          phone: peopleCardMeta(r, f), home: cardHead({r, entries: [{t: {text: '', since: ''}}]}, 0), relation}}));
    ''')
    assert result['english'] == 'Head of Partnerships'
    assert result['role'] == '合作负责人'
    assert result['location'] == '新西兰惠灵顿'
    for name, output in result['paths'].items():
        rendered = json.dumps(output, ensure_ascii=False)
        assert '合作负责人' in rendered, name
        assert 'Head of Partnerships' not in rendered, name
    assert '新西兰惠灵顿' in json.dumps(result['paths']['facts'], ensure_ascii=False)


def test_record_header_dates_appear_once_and_strip_dates_are_localized():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in [
        'recordEyebrow', 'leadRow', 'recordFacts', 'fmtDate', 'calendarDay', 'daysSince', 'age'])
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js(functions + '\nUI.zh = ' + ui + r''';
      const REM = {as_of: '2026-10-20', owner: 'people/avery-lin.md'}, DAY_MS = 86400000;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        appendChild(node) { this.children.push(node); }, append(...nodes) { this.children.push(...nodes); }});
      const known = () => ({last: '2026-10-17', status: 'Written'}), threads = () => ({items: [], calm: false});
      const section = () => null, categoryHref = () => '', categoryName = () => '', updatedMarker = () => null;
      const statusPill = () => null, originalMark = () => null, translationMark = () => null, mappedContact = () => false;
      const knownValue = Boolean, changedValue = node => node, inline = text => text, plainLine = text => text;
      const localPath = text => text;
      const facts = () => ({last: '2026-10-17', sessions: 4, repo: '/work/harbour', domain: 'fernhill.example'});
      const r = {path: 'projects/harbour.md', category: 'projects', translations: {zh: ''}, updated: '2026-10-19'};
      const output = {};
      for (const language of ['en', 'zh']) {
        uiLanguage = language;
        output[language] = ['projects', 'orgs'].map(category => {
          r.category = category;
          return {eyebrow: recordEyebrow(r, false), lead: leadRow(r), strip: recordFacts(r)};
        });
        r.category = 'people'; output[language].push(recordFacts(r));
      }
      console.log(JSON.stringify(output));
    ''')
    for language, date in [('en', '3 days ago'), ('zh', '3 天前')]:
        for record in result[language][:2]:
            header = json.dumps([record['eyebrow'], record['lead']], ensure_ascii=False)
            assert header.count(date) == 1
            assert '2026-10-17' not in header
            assert 'file updated' not in json.dumps(record['eyebrow'])
            assert '2026-10-17' not in json.dumps(record['strip'])
        # A strip date that isn't represented in the record header is still localized.
        assert date in json.dumps(result[language][2], ensure_ascii=False)
    assert '3 天前' in json.dumps(result['zh'][1]['lead'], ensure_ascii=False)


def test_purpose_expansion_controls_are_independent_and_keep_collapse_available():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['expansionButton', 'refreshFocusExpansion'])
    result = _run_reader_js(functions + r''';
      const statements = ['what-it-is', 'focus-statement'].map(id => {
        const classes = new Set(['clamped']);
        return {id, scrollHeight: 180, clientHeight: 80, classList: {
          contains: value => classes.has(value),
          toggle(value) { if (classes.has(value)) { classes.delete(value); return false; }
            classes.add(value); return true; }}};
      });
      const el = (tag, attrs) => ({...attrs, setAttribute(k, v) { this[k] = v; },
        getAttribute(k) { return this[k]; }});
      const controls = statements.map(statement => expansionButton(statement, 'Read full purpose'));
      const document = {querySelectorAll: () => controls,
        getElementById: id => statements.find(statement => statement.id === id)};
      refreshFocusExpansion();
      const visible = controls.every(control => !control.hidden);
      controls[0].onclick();
      const expanded = controls[0]['aria-expanded'] === 'true' && controls[0].textContent === 'Show less'
        && !statements[0].classList.contains('clamped') && statements[1].classList.contains('clamped');
      statements[0].clientHeight = statements[0].scrollHeight;
      statements[1].clientHeight = statements[1].scrollHeight;
      refreshFocusExpansion();
      const shortHidden = !controls[0].hidden && controls[1].hidden;
      controls[0].onclick();
      console.log(JSON.stringify({visible, expanded, shortHidden,
        collapsed: controls[0]['aria-expanded'] === 'false' && controls[0].textContent === 'Read full purpose'
          && statements[0].classList.contains('clamped')}));
    ''')
    assert result == dict(visible=True, expanded=True, shortHidden=True, collapsed=True)


@pytest.mark.parametrize('days, inputs, expected', [
    (None, 1, '提供的会话样本未能确认项目当前的工作。'),
    (7, 1, '7 天的会话样本未能确认项目当前的工作。'),
    (None, 0, '本次调查没有为此项目分配编程会话输入。'),
    (7, 0, '本次 7 天的调查没有为此项目分配编程会话输入。'),
])
def test_project_coverage_limit_has_chinese_copy(days, inputs, expected):
    page = TEMPLATE.read_text()
    function = re.search(r'function projectLimit\(.*?\n\}', page, re.S).group(0)
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js('UI.zh = ' + ui + '; uiLanguage = "zh";\nconst r = ' + json.dumps({
        'category': 'projects', 'project_coverage': {'days': days, 'inputs_read': inputs}}) + ';\n' + function + r'''
      const known = () => ({status: 'Investigated'}), newestStanding = () => '', section = () => null;
      const el = (tag, attrs) => attrs;
      console.log(JSON.stringify(projectLimit(r).text));
    ''')
    assert result == expected


def test_relation_cards_use_translated_origin_lines_and_mark_original_fallback():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['translatedRelationBasis', 'relationCard', 'localizedRelation', 'resolve', 'originalMark'])
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js(functions + '\nUI.zh = ' + ui + r'''; uiLanguage = 'zh';
      const origin = {path: 'orgs/fernhill-labs.md', title: 'Fernhill Labs', category: 'orgs', translations: {zh:
        '# Fernhill Labs\n## People here\n- [Theo Park](../people/theo-park.md) — 代表试点团队确认了计划 [2].\n\n## Sources\n- [2] mail:invented'}};
      const person = {path: 'people/theo-park.md', title: 'Theo Park', category: 'people'};
      const byPath = path => [origin, person].find(r => r.path === path), href = r => r.path;
      const youify = text => text, singular = () => '', inline = text => text;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        appendChild(node) { this.children.push(node); }});
      const link = {path: person.path, via: origin.path, basis: 'Theo Park — confirmed the plan [2].', kind: 'linked', sources: ['2']};
      const forward = relationCard(localizedRelation(link, origin.path), origin.path),
        reverse = relationCard(localizedRelation({...link, path: origin.path, kind: 'linked from'}, person.path), person.path);
      origin.translations.zh = '# Fernhill Labs\n## Sources\n- [Theo Park](../people/theo-park.md) — 来源说明不是关系。';
      const missingLine = relationCard(localizedRelation(link, origin.path), origin.path);
      delete origin.translations;
      const missingCache = relationCard(localizedRelation(link, origin.path), origin.path);
      console.log(JSON.stringify({forward, reverse, missingLine, missingCache}));
    ''')
    for direction in ['forward', 'reverse']:
        basis = result[direction]['children'][0]['children'][2]
        assert basis['text'] == 'Theo Park — 代表试点团队确认了计划 .'
        assert '[2]' not in basis['text']
        assert result[direction]['children'][0]['children'][3] is None
    assert result['reverse']['children'][1]['children'][0]['children'][0] == '来自 '
    for fallback in ['missingLine', 'missingCache']:
        basis = result[fallback]['children'][0]['children'][2]
        assert basis['text'] == 'Theo Park — confirmed the plan [2].'
        assert result[fallback]['children'][0]['children'][3]['text'] == '原文'


def test_chinese_connected_context_collapses_repeated_origin_without_borrowing_claims():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['translatedRelationBasis', 'localizedRelation', 'dedupeRelationSnippets',
                                       'connectedContext', 'relationCard', 'relationDisclosure', 'resolve', 'plainLine', 'privateTopicHidden'])
    result = _run_reader_js(functions + r'''
      UI.zh = {}; uiLanguage = 'zh';
      const origin = {path: 'orgs/fernhill-labs.md', category: 'orgs', title: 'Fernhill Labs',
        translations: {zh: '# Fernhill Labs\n- [Theo Park](../people/theo-park.md) 和 [Mia Chen](../people/mia-chen.md) 共同审阅了试点计划 [2].'}};
      const theo = {path: 'people/theo-park.md', category: 'people', title: 'Theo Park', translations: {zh: ''}};
      const mia = {path: 'people/mia-chen.md', category: 'people', title: 'Mia Chen', translations: {zh: '# Mia Chen\n负责核对试点团队的下一步安排。'}};
      origin.relations = [theo, mia].map(r => ({path: r.path, via: origin.path, kind: 'linked',
        basis: 'Theo Park and Mia Chen reviewed the pilot plan.', sources: ['2']}));
      const byPath = path => [origin, theo, mia].find(r => r.path === path);
      const known = r => ({intro: r === mia ? '负责核对试点团队的下一步安排。' : '负责试点。'}), facts = () => ({});
      const youify = text => text, inline = text => text, singular = () => '', href = r => r.path;
      const originalMark = () => ({text: '原文'});
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        appendChild(node) { this.children.push(node); }});
      console.log(JSON.stringify(connectedContext(origin)));
    ''')
    cards = result['children'][2]['children']
    snippets = [card['children'][0]['children'][2] for card in cards]
    assert snippets[0]['text'] == 'Theo Park 和 Mia Chen 共同审阅了试点计划 .'
    assert snippets[1] is None
    assert cards[1]['children'][1]['children'][1]['html'] == '[2]'
    assert '负责核对试点团队的下一步安排' not in str(cards)
    assert all(card['children'][0]['children'][3] is None for card in cards)


def test_first_build_uses_fixture_pass_window_and_first_run_copy(tmp_path, monkeypatch):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    from connectonion.rem.reader import snapshot

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    root = build(tmp_path / 'rem', datetime(2026, 10, 20, 12, tzinfo=timezone.utc), zh=True)
    runs = sorted((root / '.state/runs').glob('*.json'), key=lambda p: json.loads(p.read_text())['started_at'])
    for run in runs[:-1]:
        run.unlink()
    data = snapshot(root)
    assert len(data['logs']) == 1
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in [
        'runTime', 'lastPass', 'firstBuild', 'sameClaim', 'scheduleState', 'nightlyUpdatesOff',
        'passSummary', 'morningBrief', 'recallPrompt', 'translationNotice'])
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js('const REM = ' + json.dumps(data) + '; UI.zh = ' + ui + ';\n' + functions + r'''
      const HOUR = 3600e3, FAILED = /^(failed|abandoned)/, STAMP = /^Investigation:[^\n]*$/m;
      const byPath = path => REM.records.find(r => r.path === path), listedRecords = () => REM.records;
      const byActivity = () => 0, sourceName = value => value, calendarDay = value => value.slice(0, 10);
      const translationPending = () => false; const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        appendChild(node) { this.children.push(node); }});
      const inline = value => value, sectionHead = text => ({text}), commandChip = command => ({command});
      const remCommand = args => 'co rem ' + args;
      REM.status = {state: 'Stopped — background maintenance is off'};
      const first = firstBuild(), header = passSummary(), brief = morningBrief(), recall = recallPrompt();
      REM.status.state = 'Running in background (launchd)';
      const scheduled = morningBrief();
      uiLanguage = 'zh';
      const zhHeader = passSummary();
      const cached = REM.records.filter(r => r.translations?.zh).map(r => ({...r, translations: {...r.translations}}));
      for (const r of REM.records) delete r.translations;
      const notice = translationNotice();
      REM.records = [...cached.slice(0, 2), ...REM.records.filter(r => ['people', 'orgs', 'projects'].includes(r.category) && !cached.some(c => c.path === r.path)).slice(0, 2)];
      const enough = translationNotice();
      REM.logs.push({...REM.logs[0], started_at: '2026-10-01T01:00:00Z'});
      const returning = firstBuild();
      REM.logs = [];
      console.log(JSON.stringify({first, header, brief, recall, scheduled, zhHeader, notice, enough,
        returning, noPass: firstBuild()}));
    ''')
    assert result['first'] is True and result['returning'] is False and result['noPass'] is False
    assert result['header']['children'][0].startswith('Built today: read ')
    assert result['brief']['children'][1]['text'] == 'Your notebook was just built. Overnight changes appear here after the next update.'
    assert result['brief']['children'][2]['children'] == [{'tag': 'p', 'text': 'Nightly updates are off.', 'children': []}]
    assert len(result['scheduled']['children']) == 2
    assert result['recall'] is None
    assert result['zhHeader']['children'][0].startswith('今天建立：读取 ')
    assert result['notice']['text'] == '打开页面时会翻译成中文。'
    assert result['enough'] is None


def test_a_busy_day_does_not_make_an_old_notebook_look_new(tmp_path, monkeypatch):
    """The page carries the latest 20 runs; 33 runs in one day hid every older one,
    and a weeks-old notebook said "Your notebook was just built"."""
    import sys
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    from connectonion.rem.reader import snapshot

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    root = build(tmp_path / 'rem', datetime(2026, 10, 20, 12, tzinfo=timezone.utc), zh=True)
    runs = sorted((root / '.state/runs').glob('*.json'), key=lambda p: json.loads(p.read_text())['started_at'])
    latest = json.loads(runs[-1].read_text())
    started = datetime.fromisoformat(latest['started_at'])
    for n in range(1, 26):
        run = {**latest, 'id': f'run_busy_{n:02d}', 'started_at': (started - timedelta(minutes=10 * n)).isoformat()}
        (root / f'.state/runs/run_busy_{n:02d}.json').write_text(json.dumps(run))
    data = snapshot(root)
    assert len(data['logs']) <= 21
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['runTime', 'lastPass', 'firstBuild', 'sameClaim'])
    result = _run_reader_js('const REM = ' + json.dumps(data) + ';\n' + functions + r'''
      const HOUR = 3600e3, FAILED = /^(failed|abandoned)/, STAMP = /^Investigation:[^\n]*$/m;
      const byPath = path => REM.records.find(r => r.path === path), listedRecords = () => REM.records;
      const sourceName = value => value, byActivity = () => 0, calendarDay = value => value.slice(0, 10);
      console.log(JSON.stringify({first: firstBuild()}));
    ''')
    assert result['first'] is False


def test_schedule_reader_states_are_short_and_translated():
    page = TEMPLATE.read_text()
    function = re.search(r'function scheduleState\(.*?\n\}', page, re.S).group(0)
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js('UI.zh = ' + ui + '; uiLanguage = "zh";\n' + function + r'''
      console.log(JSON.stringify(['Not started', 'Stopped — background maintenance is off',
        'Not scheduled here — another notebook', 'Running in background (launchd); next slot unknown',
        'Background needs attention — last pass failed'].map(state => t(scheduleState({state})))));
    ''')
    assert result[:3] == ['后台更新未开启'] * 3
    assert result[3:] == ['夜间更新已开启', '后台更新需要处理']


def test_owner_thread_surfaces_use_your_page_without_counterpart_metadata():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['threadWho', 'cardHead', 'stripMarksDone', 'threadRow', 'withoutDateClutter'])
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js(functions + "\nconst icon = () => null, groupLate = () => 0, liveHere = () => !!REM.live; const translationPending = () => false; const kindBadge = () => null, threadKind = () => null;\n" + '\nUI.zh = ' + ui + r''';
      const REM = {owner: 'people/theo-park.md', as_of: '2026-10-20'};
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children, classList: {add() {}}});
      const href = r => '#r=' + r.path, morningWords = () => ({words: 'Review the pilot.', context: ''});
      const contactFields = () => [{label: 'Role', value: 'Pilot lead'}], company = () => 'Northgate University';
      const roleSummary = value => value, calendarDay = day => day, dueLabel = () => '', threadActions = () => null;
      const privateFallback = node => node, inline = text => text, plainLine = text => text, alsoOn = () => null;
      const threadAge = () => '', threadDate = day => day, blockerTag = () => null, singular = () => 'person', daysSince = () => 0;
      const age = () => '', threadDraft = () => null, draftNote = () => null;
      const DIRECTION_LABEL = {mine: 'You owe'};
      const owner = {path: REM.owner, title: 'Theo Park'}, person = {path: 'people/mia-chen.md', title: 'Mia Chen'};
      const thread = {text: 'You owe a pilot review.', since: '2026-10-20', dir: 'mine'};
      const renderRows = r => ({today: cardHead({r, entries: [{r, t: thread}]}, 0), open: threadRow(r, thread, true)});
      const en = renderRows(owner), counterpart = renderRows(person);
      uiLanguage = 'zh';
      console.log(JSON.stringify({en, zh: renderRows(owner), counterpart}));
    ''')
    for lang, who in [('en', 'Your page'), ('zh', '你的页面')]:
        rows = result[lang]
        head = rows['today']['children']
        assert head[1]['text'] == who
        assert head[1]['href'] == '#r=people/theo-park.md'
        assert head[2] is None
        assert rows['open']['children'][1]['children'][1]['children'][0]['text'] == who
    head = result['counterpart']['today']['children']
    assert head[1]['text'] == 'Mia Chen'
    # N3: the organisation is a chip (its mark, its name); the role is the chip's title, not a third phrase.
    assert head[2]['children'][1] == 'Northgate University' and head[2]['title'] == 'Pilot lead'


@pytest.mark.parametrize('configured', [True, False])
def test_reader_exposes_language_origin_and_home_display_root(tmp_path, monkeypatch, configured):
    from pathlib import Path
    from connectonion.rem.config import set_config
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.reader import snapshot
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: tmp_path))
    root = tmp_path / '.co/owner notebook/rem'
    prepare(root)
    write_json(state_path(root, 'map.json'), {'owner': {'languages': {'languages': ['zh', 'en']}}})
    if configured:
        set_config(root, ['languages', 'zh,en'])
    data = snapshot(root)
    assert data['root_display'] == '~/.co/owner notebook/rem' and not data['default_root']
    assert data['your_languages'] == ['zh', 'en']
    assert data['languages_from'] == ('set' if configured else 'detected')
    outside = tmp_path / 'outside'
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: outside))
    assert snapshot(root)['root_display'] == str(root)
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: root.parents[1]))
    # Default root uses the plain command, independent of the display path.
    default_root = Path.home() / '.co/rem'
    prepare(default_root)
    assert snapshot(default_root)['default_root']


@pytest.mark.parametrize('origin', ['detected', 'set'])
def test_reader_languages_setting_is_visible_inside_disclosure_and_read_only(origin):
    page = TEMPLATE.read_text()
    function = re.search(r'function notebookLanguages\(.*?\n\}', page, re.S).group(0)
    result = _run_reader_js('const REM = ' + json.dumps({'your_languages': ['zh', 'en'], 'languages_from': origin}) + ';\n'
        + function + r'''
        const nativeName = tag => ({zh: '中文', en: 'English'})[tag];
        const el = (tag, attrs, children) => ({tag, ...attrs, children});
        const remCommand = args => 'co rem ' + args, copyToClipboard = () => {};
        console.log(JSON.stringify(notebookLanguages()));
    ''')
    assert result['children'][0]['text'] == 'Notebook languages: 中文 · English — ' + origin
    # D-60/D-103 (build 3b review): REM detects the languages; there is no command to copy beside them.
    assert len(result['children']) == 1 and 'co rem' not in json.dumps(result)
    settings = re.search(r'function renderSettings\(.*?\n\}', page, re.S).group(0)
    assert 'notebookLanguages(),' in settings  # one row of the settings sheet


def test_translation_notice_is_one_quiet_line_for_missing_written_pages():
    function = re.search(r'function translationNotice\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      UI.zh = {};
      const REM = {logs: [], records: [
        {path: 'people/avery-lin.md', category: 'people', written: true, translations: {zh: '译文'}},
        ...Array.from({length: 20}, (_, n) => ({path: 'projects/mapped-' + n + '.md', category: 'projects', written: false}))]};
      const listedRecords = () => REM.records, remCommand = args => 'co rem ' + args;
      const commandChip = command => ({command}), el = (tag, attrs, children) => ({...attrs, children});
      uiLanguage = 'zh';
      const mapped = translationNotice();
      delete REM.records[0].translations;
      const missing = translationNotice();
      REM.logs = [{phase: 'daily-translation', pages: [{page: 'people/avery-lin.md', outcome: 'failed', error: 'fixture refusal'}]}];
      const failed = translationNotice();
      REM.logs.unshift({phase: 'init-translation', pages: []});
      const last = translationNotice();
      REM.status = {worker: {enabled: true}};
      const queued = translationNotice();
      uiLanguage = 'en';
      console.log(JSON.stringify({mapped, missing, failed, last, queued, english: translationNotice()}));
    ''')
    assert result['mapped'] is None and result['english'] is None
    for state in ['missing', 'failed', 'last', 'queued']:
        prefix = '1 page could not be translated. ' if state == 'failed' else ''
        assert result[state]['text'] == prefix + 'Pages are translated when you open them.'
        assert 'children' not in result[state]


def test_reader_keeps_latest_translation_summary_after_many_page_runs(tmp_path, monkeypatch):
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.reader import snapshot
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'runs/run_summary.json'), {
        'started_at': '2026-10-21T00:00:00+00:00', 'phase': 'init-translation', 'pages': [
            {'page': 'people/avery-lin.md', 'outcome': 'failed'}]})
    for n in range(25):
        write_json(state_path(tmp_path, f'runs/run_page{n}.json'), {
            'started_at': f'2026-10-21T00:01:{n:02d}+00:00', 'phase': 'translate', 'outcome': 'completed'})
    assert any(log['phase'] == 'init-translation' for log in snapshot(tmp_path)['logs'])


@pytest.mark.parametrize('tag', ['zh-TW', 'zh-CN'])
def test_chinese_interface_uses_the_owners_regional_cached_prose(tag):
    page = TEMPLATE.read_text()
    cache = re.search(r'function cacheChineseInterface\(.*?\n\}', page, re.S).group(0)
    notice = re.search(r'function translationNotice\(.*?\n\}', page, re.S).group(0)
    result = _run_reader_js('const REM = ' + json.dumps({'your_languages': ['en', tag], 'logs': [], 'records': [
        {'path': 'people/avery-lin.md', 'category': 'people', 'written': True, 'translations': {tag: '草稿。'}}]}) + ';\n'
        + cache + '\n' + notice + r'''
        const listedRecords = () => REM.records;
        cacheChineseInterface(); uiLanguage = 'zh';
        console.log(JSON.stringify({translated: REM.records[0].translations.zh, notice: translationNotice()}));
    ''')
    assert result == {'translated': '草稿。', 'notice': None}


def test_settings_say_nightly_updates_are_off_without_a_command():
    """D-60 (build 3b review): Reader settings states the schedule in words, never a command to type."""
    page = TEMPLATE.read_text()
    function = re.search(r'function remStateWords\(.*?\n\}', page, re.S).group(0)
    result = _run_reader_js(function + r'''
        const nightlyUpdatesOff = () => true, scheduleState = () => '', fmtTime = time => time;
        console.log(JSON.stringify(remStateWords({next_run: '02:00'})));
    ''')
    assert result == 'Nightly updates are off.'


def test_citation_dates_share_the_notebook_local_calendar_and_reader_format():
    names = ['calendarDay', 'fmtDate', 'fmtTime', 'shortDate', 'citationDate', 'chipLabel', 'messageMeta']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0) for name in names)
    result = _run_reader_js(functions + r'''
      const REM = {status: {timezone: 'Australia/Sydney'}, as_of: '2026-10-28', source_context: {
        'outlook:example': {time: '2026-10-26T13:17:00Z', source: 'outlook', sender: 'Nora'}}};
      const citationSource = () => 'outlook:example — 2026-10-26', citationId = () => 'outlook:example';
      const sourceChannel = text => text, sourceSender = context => context.sender;
      console.log(JSON.stringify([fmtDate('2026-10-27'), shortDate('2026-10-27'), citationDate({}, '1'),
        chipLabel({}, '1'), fmtTime('2026-10-26T13:17:00Z'), messageMeta(REM.source_context['outlook:example'])]));
    ''')
    assert result[:3] == ['Yesterday'] * 3
    assert all('Yesterday' in text for text in result[3:])


def test_conversation_windows_are_scoped_to_sources_on_the_current_page():
    function = re.search(r'function conversationFor\(.*?\n\}', TEMPLATE.read_text(), re.S)
    # This projection is needed even when two pages cite the same session.
    assert function, 'The reader has no page-scoped conversation projection'
    result = _run_reader_js(function.group(0) + r'''
      const REM = {source_context: {'codex:example:3': {thread: 'session:example'}}, conversations: {
        'session:uncited': {anchors: {}, windows: {'other:100': ['100']}, messages: [{id: '100'}]},
        'session:example': {subject: 'Example', total: 1358, cited_ids: ['3', '100'], anchors: {'codex:example:3': '3'},
          windows: {'codex:example:3': ['1', '2', '3', '4', '5'], 'codex:example:100': ['99', '100']},
          messages: [1, 2, 3, 4, 5, 99, 100].map(i => ({id: String(i)}))}}};
      const sourceList = r => r.sources.map(text => ({text})), sourceId = text => text;
      const r = {sources: ['codex:example:3']};
      console.log(JSON.stringify([conversationFor(r, 'session:example'), conversationFor(r, 'session:uncited')]));
    ''')
    assert [m['id'] for m in result[0]['messages']] == ['1', '2', '3', '4', '5']
    assert result[0]['cited_ids'] == ['3']
    assert result[1] is None


def test_page_navigation_closes_the_conversation_dialog():
    page = TEMPLATE.read_text()
    listener = re.search(r'window.addEventListener\("hashchange", \(\) => \{\s*document.getElementById\("conversation-dialog"\)\?\.close\(\);\s*\}\);', page)
    assert listener, 'Conversation dialog has no navigation cleanup'
    result = _run_reader_js(r'''
      const callbacks = [], dialog = {open: true, close() {this.open = false;}};
      const document = {getElementById: () => dialog}, window = {addEventListener: (event, callback) => callbacks.push(callback)};
    ''' + listener.group(0) + r'''
      callbacks[0](); console.log(JSON.stringify(dialog.open));
    ''')
    assert result is False


def test_redundant_investigation_badge_is_omitted_and_owner_stays_out_of_people():
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\}', TEMPLATE.read_text(), re.S).group(0)
                          for name in ['listedRecords', 'inCategory', 'privateTopicHidden'])
    pill = re.search(r'function statusPill\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(functions + '\n' + pill + r'''
      const REM = {owner: 'people/owner.md', records: [
        {path: 'people/owner.md', category: 'people'}, {path: 'people/nora.md', category: 'people'}]};
      const ACTIVITY = new Set(), known = () => ({status: 'Investigated'}), moon = () => null;
      const el = (tag, attrs, children) => ({tag, ...attrs, children});
      console.log(JSON.stringify([inCategory("people").map(r => r.path), statusPill(REM.records[1])]));
    ''')
    assert result == [['people/nora.md'], None]


def test_neighbor_cited_on_another_page_is_not_highlighted_as_this_pages_citation():
    function = re.search(r'function conversationFor\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      const REM = {source_context: {'outlook:hash': {thread: 'mail:example'}}, conversations: {
        'mail:example': {cited_ids: ['native:3', 'native:4'], anchors: {'outlook:hash': 'native:3'},
          windows: {'outlook:hash': ['native:2', 'native:3', 'native:4']},
          messages: [2, 3, 4].map(i => ({id: 'native:' + i}))}}};
      const sourceList = () => [{text: 'outlook:hash'}], sourceId = text => text;
      console.log(JSON.stringify(conversationFor({}, 'mail:example').cited_ids));
    ''')
    assert result == ['native:3']


def test_unfiltered_sheet_count_is_a_total_instead_of_a_perfect_ratio():
    count = next(line.strip() for line in TEMPLATE.read_text().splitlines() if 'count.textContent = ' in line and 'rows.length' in line)
    result = _run_reader_js(r'''
      const count = {}, rows = [1, 2, 3], items = [1, 2, 3];
    ''' + count + r'''
      console.log(JSON.stringify(count.textContent));
    ''')
    assert result == '3 pages'


def test_source_find_uses_the_panel_scroll_that_reserves_mail_header_space():
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
                          for name in ['sourceFind'])
    result = _run_reader_js(functions + r'''
      const panel = {}, nodes = [], scrolls = [];
      const el = (tag, attrs, children) => {const node = {tag, ...attrs, children, scrollIntoView() {}}; nodes.push(node); return node;};
      const quote = {innerHTML: 'Original', replaceChildren() {}, closest: () => panel};
      const document = {createTextNode: text => ({text})};
      const scrollEvidenceSpan = (target, mark) => scrolls.push({correctPanel: target === panel, text: mark.text});
      sourceFind('Earlier text. The cited example. Later text.', quote);
      const input = nodes.find(n => n.tag === 'input'); input.value = 'cited example'; input.oninput();
      console.log(JSON.stringify(scrolls));
    ''')
    assert result == [{'correctPanel': True, 'text': 'cited example'}]


def test_owner_stays_in_obligation_inputs_when_removed_from_people_rows():
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\}', TEMPLATE.read_text(), re.S).group(0)
                          for name in ['listedRecords', 'inCategory', 'privateTopicHidden'])
    result = _run_reader_js(functions + r'''
      const REM = {owner: 'people/owner.md', records: [
        {path: 'people/owner.md', category: 'people'}, {path: 'people/nora.md', category: 'people'}]};
      const ACTIVITY = new Set();
      console.log(JSON.stringify({taskInputs: listedRecords().map(r => r.path), people: inCategory('people').map(r => r.path)}));
    ''')
    assert result == {'taskInputs': ['people/owner.md', 'people/nora.md'], 'people': ['people/nora.md']}


def test_project_mobile_row_omits_the_redundant_investigated_label():
    function = re.search(r'function nameCell\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      const translationPending = () => false; const el = (tag, attrs, children = []) => ({tag, ...attrs, children});
      const known = r => ({status: r.status}), moon = () => null, href = () => '#', updatedMarker = () => null;
      const labels = ['Investigated', 'Mapped'].map(status => nameCell({category: 'projects', title: 'Example', status}, {}, false)
        .children.filter(n => n?.class === 'mobile-status-label').map(n => n.text));
      console.log(JSON.stringify(labels));
    ''')
    assert result == [[], []]


def test_conversation_reopens_at_the_cited_message_instead_of_old_scroll_position():
    function = re.search(r'function openConversation\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      const scrolls = [], cited = {scrollIntoView: options => scrolls.push(options)};
      const dialog = {scrollTop: 999, append() {}, appendChild() {}, addEventListener() {}, showModal() {}, querySelector: () => cited};
      const document = {getElementById: () => dialog};
      const el = (tag, attrs, children) => ({tag, ...attrs, children, focus() {}});
      const byPath = () => null, sourceSender = () => 'You';
      const conversationFor = () => ({subject: 'Example', cited_ids: ['example:3'], messages: [{id: 'example:3', sender: 'You', excerpt: 'Cited example.'}]});
      openConversation({}, 'example', {focus() {}});
      console.log(JSON.stringify({scrollTop: dialog.scrollTop, scrolls}));
    ''')
    assert result == {'scrollTop': 0, 'scrolls': [{'block': 'center'}]}


def test_omitted_status_leaves_no_empty_field_or_header_separator():
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
                          for name in ['recordEyebrow', 'sidePanels'])
    result = _run_reader_js(functions + r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children, append(...nodes) {this.children.push(...nodes);}});
      const known = () => ({}), categoryHref = () => '#', categoryName = () => 'Projects', updatedMarker = () => null, translationMark = () => null;
      const statusPill = () => null, factList = () => null, panel = (text, children) => el('section', {text}, children);
      const r = {category: 'projects', text: '# Example'};
      console.log(JSON.stringify({separators: recordEyebrow(r, false).children.filter(n => n?.class === 'sep').map(n => n.text),
        fields: sidePanels(r, {}).flatMap(p => p.children[0].children.filter(n => n?.tag === 'dt').map(n => n.text))}));
    ''')
    assert result == {'separators': [], 'fields': []}


def test_plain_words_date_grammar_uses_notebook_year_and_week_boundary():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['calendarDay', 'fmtDate', 'threadDate', 'shortDate'])
    result = _run_reader_js(functions + r'''
      const REM = {as_of: '2026-11-07T01:00:00Z', status: {timezone: 'Australia/Sydney'}};
      uiLanguage = 'zh';
      const dates = ['2026-11-07', '2026-11-06', '2026-11-04', '2026-10-31', '2026-10-30', '2025-10-23'];
      console.log(JSON.stringify([fmtDate, threadDate, shortDate].map(format => dates.map(format))));
    ''')
    assert result == [['今天', '昨天', '3 天前', '7 天前', '10月30日', '2025年10月23日']] * 3


@pytest.mark.parametrize('text, expected', [
    ('2026-10-23: You owe Mara the signed plan — (2026-10-23) — due 2026-10-25, overdue; open as of 2026-11-03 [2].',
     '2026-10-23: You owe Mara the signed plan — due 2026-10-25, overdue.'),
    ('Acceptance is not recorded — open as of 2026-10-27 [3].', 'Acceptance is not recorded.'),
    ('请确认计划 (2026-10-23) [W4]。', '请确认计划。'),
])
def test_plain_words_headlines_remove_dates_status_and_inline_citation_numbers(text, expected):
    function = re.search(r'function withoutDateClutter\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    assert _run_reader_js(function + '\nconsole.log(JSON.stringify(withoutDateClutter(' + json.dumps(text) + ')));') == expected


def test_debt_age_ignores_observation_dates_and_uses_latest_request_evidence():
    page = TEMPLATE.read_text()
    names = ['threads', 'writtenDates', 'writtenDatePattern', 'calendarDay', 'daysSince', 'rawSection', 'listItems', 'isCalm']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = _run_reader_js(functions + r'''
      const REM = {as_of: '2026-11-07', source_context: {
        'gmail:request': {time: '2026-10-08T10:00:00Z'},
        'gmail:reminder': {time: '2026-10-23T10:00:00Z'}}}, DAY_MS = 86400000;
      const COMMENT = /<!--[\s\S]*?-->/g, UNKNOWN_TEXT = /^Unknown$/;
      const direction = () => 'mine';
      const record = text => ({path: 'people/mara.md', category: 'people', text: '# Mara\n\n## Open threads\n- ' + text +
        '\n\n## Sources\n- [1] gmail:request\n- [2] gmail:reminder\n'});
      console.log(JSON.stringify([
        threads(record('You owe Mara a signed plan; requested on 2026-10-08; last moved 2026-11-03; open as of 2026-11-07 [1].')).items[0].since,
        threads(record('You owe Mara a signed plan; requested on 2026-10-08; open as of 2026-11-07 [1] [2].')).items[0].since
      ]));
    ''')
    assert result == ['2026-10-08', '2026-10-23']


def test_primary_surfaces_have_no_command_copy_controls():
    page = TEMPLATE.read_text()
    for name in ['morningBrief', 'category', 'contactDirectory', 'record', 'threadActions', 'translationNotice']:
        function = re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
        assert 'commandChip(' not in function, name
        assert not re.search(r't\("(?:Copy (?:prompt|command|setup|review)|Prepare in terminal)', function), name
    strip = re.search(r'function contactStrip\(.*?\n\}', page, re.S).group(0)
    assert 'copyToClipboard' not in strip


def test_session_previews_hide_paths_including_paths_with_spaces():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['sessionExcerpt', 'sessionText', 'sessionPreview'])
    result = _run_reader_js(functions + r'''
      const SESSION_TEXT = new Map();
      const r = {path: 'sessions/fiction.md', title: 'Plan review', text: '',
        session_summary: 'Reviewed `/Users/fiction/Library/Application Support/work/plan.md` and /private/tmp/fiction.txt with Mara.'};
      console.log(JSON.stringify([sessionExcerpt(r, []), sessionExcerpt(r, ['Mara'])]));
    ''')
    assert all('/Users' not in row['text'] and '/private' not in row['text'] and 'Application Support' not in row['text'] for row in result)
    assert all('Mara' in row['text'] for row in result)


def test_chinese_missing_page_queues_its_translation_once_only_in_the_live_reader():
    function = re.search(r'function translationQueued\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      uiLanguage = 'zh';
      const REM = {live: true}, requests = [], fetch = (url, options) => requests.push({url, ...JSON.parse(options.body)});
      const r = {path: 'people/mara.md', category: 'people', title: 'Mara', text: 'English obligation sentence.'};
      const live = [translationQueued(r), translationQueued(r)];
      const native = ['zh', 'zh-CN', 'zh-TW'].map(written_in => translationQueued({...r, written_in}));
      const translated = translationQueued({...r, path: 'people/ida.md', translations: {zh: 'x'}});
      REM.live = false;
      const offline = translationQueued({...r, path: 'people/noa.md'});
      console.log(JSON.stringify({live, native, translated, offline, requests}));
    ''')
    assert result['live'] == [True, True]
    assert result['native'] == [False] * 3 and result['translated'] is False and result['offline'] is False
    assert result['requests'] == [{'url': '/rem/translation-request', 'page': 'people/mara.md', 'language': 'zh'}]


def test_session_preview_preserves_web_links_while_hiding_local_paths():
    function = re.search(r'function sessionPreview\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    text = 'Reviewed https://example.test/plan with Mara; files: /work/plan.md ~/notes/plan.md ./src/plan.py src/plan.py C:\\work\\plan.md.'
    result = _run_reader_js(function + '\nconsole.log(JSON.stringify(sessionPreview(' + json.dumps(text) + ')));')
    assert 'https://example.test/plan' in result
    assert all(path not in result for path in ['/work', '~/notes', './src', 'src/plan.py', 'C:\\work'])


def test_person_and_today_use_the_same_merged_obligation_and_source_record():
    function = re.search(r'function personEntries\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r"""
      const r = {path: 'people/mara.md'}, origin = {path: 'people/avery.md'};
      const current = {dir: 'mine', text: 'You owe Mara the signed plan [2].', since: '2026-10-23'};
      const threadEntries = () => [{r: origin, t: current, also: [r], members: [{r: origin, t: current}, {r, t: {text: 'Mara copy.'}}]},
        {r, t: {dir: 'third', text: 'Fern owes Avery.'}}, {r: origin, t: {dir: 'mine', text: 'Unrelated.'}, also: []}];
      const doneKey = entry => entry.t.text;
      // The page's copy is already merged; the new request is not projected yet; a third-party line stays out.
      const threads = () => ({items: [{dir: 'mine', text: 'Mara copy.'}, {dir: 'theirs', text: 'Mara owes the export.'}, {dir: 'third', text: 'Quinn owes Tomás.'}]});
      console.log(JSON.stringify(personEntries(r).map(entry => [entry.r.path, entry.t.text])));
    """)
    assert result == [['people/avery.md', 'You owe Mara the signed plan [2].'], ['people/mara.md', 'Mara owes the export.']]


def test_plain_words_drops_observation_stamps_and_the_due_suffix_the_card_header_already_shows():
    function = re.search(r'function withoutDateClutter\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    text = 'Feedback on the Sprint 1 demo — “I will watch the demo and send feedback that week.” (2026-10-23) — due 2026-10-25, overdue.'
    script = function + '\nconsole.log(JSON.stringify([withoutDateClutter(' + json.dumps(text) + ', {since: "2026-10-23", due: "2026-10-25"}), withoutDateClutter(' + json.dumps(text) + ')]));'
    with_header, bare = _run_reader_js(script)
    assert with_header == 'Feedback on the Sprint 1 demo — “I will watch the demo and send feedback that week.”.'
    assert 'due 2026-10-25' in bare and '(2026-10-23)' not in bare


@pytest.mark.parametrize('text, expected', [
    ('她在等你提供收据；从 2026-10-08 起尚未交齐，她将在 2026-11-09 前报税。', '她在等你提供收据；从 2026-10-08 起尚未交齐，她将在 2026-11-09 前报税。'),
    ('等 Fernhill 提供测试收件箱；承诺于 2026-10-23。', '等 Fernhill 提供测试收件箱；承诺于 2026-10-23。'),
    ('她负责合作事务 [1]。最近联系：2026-11-06，邮件 [2]。', '她负责合作事务。'),
    ('You owe Mara the signed plan [4]. Last contact: 2026-11-06 [6].', 'You owe Mara the signed plan.'),
    ('She said "open as of 2026-11-09 [2]"; meet on 2026-11-10.', 'She said "open as of 2026-11-09 [2]"; meet on 2026-11-10.'),
    ("She said 'It's open as of 2026-11-09'.", "She said 'It's open as of 2026-11-09'."),
    ('She said ‘It’s open as of 2026-11-09’.', 'She said ‘It’s open as of 2026-11-09’.'),
    ('她说：“自 2026-11-09 起等你，最近联系：2026-11-10 [2]。”', '她说：“自 2026-11-09 起等你，最近联系：2026-11-10 [2]。”'),
    ('Review from 2026-11-09 until 2026-11-12; deliver by 2026-11-13.', 'Review from 2026-11-09 until 2026-11-12; deliver by 2026-11-13.'),
])
def test_plain_words_removes_date_connectors_and_redundant_contact_clauses(text, expected):
    function = re.search(r'function withoutDateClutter\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    assert _run_reader_js(function + '\nconsole.log(JSON.stringify(withoutDateClutter(' + json.dumps(text) + ')));') == expected


def test_plain_words_only_removes_since_when_the_card_shows_its_age():
    function = re.search(r'function withoutDateClutter\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      const text = 'Waiting since 2026-10-08; meet on 2026-11-09.';
      console.log(JSON.stringify([withoutDateClutter(text), withoutDateClutter(text, {since: '2026-10-08'}),
        withoutDateClutter(text, {since: '2026-10-10'}),
        withoutDateClutter('她在等收据；从 2026-10-08 起尚未交齐，将在 2026-11-09 前报税。', {since: '2026-10-08'})]));
    ''')
    assert result == ['Waiting since 2026-10-08; meet on 2026-11-09.', 'Waiting; meet on 2026-11-09.',
                      'Waiting since 2026-10-08; meet on 2026-11-09.', '她在等收据；尚未交齐，将在 2026-11-09 前报税。']


@pytest.mark.parametrize('text, expected', [
    ('Since 2026-10-02, fern owes the discovery findings.', 'Fern owes the discovery findings.'),
    ('Since 2026-10-02; mara owes the plan.', 'Mara owes the plan.'),
    ('Since 2026-10-02: avery owes the plan.', 'Avery owes the plan.'),
    ('Since 2026-10-02 — mara owes the plan.', 'Mara owes the plan.'),
    ('Mara owes the plan, since 2026-10-02, and the findings.', 'Mara owes the plan, and the findings.'),
    ('Mara owes the plan ; since 2026-10-02 ; send it tomorrow.', 'Mara owes the plan; send it tomorrow.'),
    ('Mara owes the plan, since 2026-10-02.', 'Mara owes the plan.'),
    ('Mara owes the plan — since 2026-10-02', 'Mara owes the plan'),
    ('从 2026-10-02 起，等待确认计划。', '等待确认计划。'),
    ('从 2026-10-02 起；等待确认计划。', '等待确认计划。'),
    ('从 2026-10-02 起：等待确认计划。', '等待确认计划。'),
    ('等待计划，从 2026-10-02 起，尚未交齐。', '等待计划，尚未交齐。'),
    ('等待计划 ；从 2026-10-02 起 ；尚未交齐。', '等待计划；尚未交齐。'),
    ('等待计划；从 2026-10-02 起。', '等待计划。'),
    ('等待计划：从 2026-10-02 起', '等待计划'),
    ('(2026-10-02), mara owes the plan [1].', 'Mara owes the plan.'),
    ('Since 2026-10-02 [1], fern owes the plan.', 'Fern owes the plan.'),
    ('Since 2026-10-02, [1] fern owes the plan.', 'Fern owes the plan.'),
    ('Mara owes the plan, since 2026-10-02 [1], and the findings.', 'Mara owes the plan, and the findings.'),
    ('从 2026-10-02 起 [1]，等待计划。', '等待计划。'),
    ('[1], fern owes the plan.', 'Fern owes the plan.'),
    ('Mara owes the plan, [1], and the findings.', 'Mara owes the plan, and the findings.'),
    ('Last contact: 2026-10-02. mara owes the plan.', 'Mara owes the plan.'),
    ('Since 2026-10-02, “leave , , and ; untouched”; mara owes the plan.',
     '“leave , , and ; untouched”; mara owes the plan.'),
])
def test_plain_words_repairs_orphan_punctuation_after_metadata_removal(text, expected):
    function = re.search(r'function withoutDateClutter\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    script = function + '\nconsole.log(JSON.stringify(withoutDateClutter(' + json.dumps(text) + ', {since: "2026-10-02"})));'
    assert _run_reader_js(script) == expected


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_person_stats_strip_names_mail_first_contact_reply_time_and_who_wrote_last(language):
    page = TEMPLATE.read_text()
    ui = page[page.index('const UI = {'):page.index('function t(')].strip()
    ui = ui.replace('const UI = ', 'Object.assign(UI, ', 1)[:-1] + ');'
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['personStats', 'replyDuration', 'firstName', 'fmtDate', 'calendarDay'])
    result = _run_reader_js(ui + functions + r"""
      uiLanguage = """ + json.dumps(language) + r""";
      const REM = {as_of: '2026-11-08T12:00:00Z'};
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const facts = () => ({mails: 9, first: '2026-09-23', last: '2026-11-07'});
      const relationship = {weekly_messages: [...Array(50).fill(0), 20, 32], last_mail: '2026-11-07T12:00:00Z', reply_seconds_owner: 37269, last_from_you: false};
      const personFuseData = () => ({wait: '2026-11-07'});
      const stats = personStats({title: 'Mara Ostrowski', index: {relationship}});
      const bare = personStats({title: 'Fern Ivy', index: null});
      console.log(JSON.stringify([stats.children.map(cell => [cell.children[0].text, cell.children[1].text, cell.class]), bare.children.length]));
    """)
    # The first exchange sits under the contact rhythm (N3); the last one is red while their mail waits on you.
    expected = {'en': [['52', 'mails this year', ''], ['10 hours', 'your median reply', ''], ['Yesterday', 'Mara wrote last', 'late']],
                'zh': [['52', '封邮件往来 · 一年内', ''], ['10 小时', '你的回复中位数', ''], ['昨天', 'Mara 最后来信', 'late']]}
    assert result[0] == expected[language]
    assert result[1] == 2


@pytest.mark.parametrize('language', ['en', 'zh'])
@pytest.mark.parametrize('code', ['blocked', 'repeated_failure'])
def test_schedule_failure_header_uses_interface_language(language, code):
    page = TEMPLATE.read_text()
    ui = page[page.index('const UI = {'):page.index('function t(')].strip()
    ui = ui.replace('const UI = ', 'Object.assign(UI, ', 1)[:-1] + ');'
    function = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in ['scheduleFailure', 'turnTrouble'])
    result = _run_reader_js(ui + function + r'''
      uiLanguage = ''' + json.dumps(language) + r''';
      const waitingMore = () => null, threadWho = r => r.title;
      const REM = {as_of: '2026-11-07', status: {schedule_failure: {code: ''' + json.dumps(code) + r''', evidence: 'exit 124'}}};
      const lastPass = () => null, firstBuild = () => false, calendarDay = day => day;
      const el = (tag, attrs, children = []) => ({tag, ...attrs, children});
      const line = scheduleFailure();
      console.log(JSON.stringify([line.text, line.title]));
    ''')
    text, title = result
    # D-71 (polish): the runner's raw English stays out of the line, in the reader's language or not;
    # it is kept on the title for whoever debugs it.
    assert 'exit 124' not in text and title == 'exit 124'
    # D-60 (build 3b review): the next step is said in words, never as a command to type.
    assert 'co rem' not in text
    expected = {('zh', 'blocked'): '上一轮定时任务被挡住了，没有跑完，正在等阻塞解除。',
                ('en', 'blocked'): 'The last scheduled round could not finish and is waiting for its blocker to clear.',
                ('zh', 'repeated_failure'): '最近两轮定时任务都没有跑完；REM 会自动重试。',
                ('en', 'repeated_failure'): 'The last two scheduled rounds did not finish; REM retries them automatically.'}
    assert text == expected[(language, code)]


def test_quiet_threads_on_home_show_the_thread_words_even_before_translation():
    function = re.search(r'function quietThreads\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const href = r => '#r=' + r.path, threadWho = () => 'Fern', threadPreview = text => text, alsoOn = () => null, age = () => '3 days';
      const threadRow = () => null;
      const entries = [{r: {path: 'people/fern.md'}, t: {quiet: true, text: 'Still waiting on the slides.', since: '2026-11-01'}}];
      console.log(JSON.stringify(quietThreads(entries, 1, true)));
    ''')
    assert 'Still waiting on the slides.' in json.dumps(result)
    assert 'Gone quiet' in json.dumps(result)


def test_today_keeps_safe_failure_recovery_without_runner_payload():
    from connectonion.rem.reader import _today_data

    shell = _today_data({'records': [], 'drafts': [], 'source_context': {}, 'logs': [
        {'phase': 'init', 'outcome': 'failed', 'error': 'Failed to authenticate: 403 private payload'},
        {'phase': 'init', 'outcome': 'failed', 'error': 'TimeoutError: private payload'},
        {'phase': 'init-translation', 'pages': [{'page': 'people/mara.md', 'outcome': 'failed'}]},
    ]})
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
                          for name in ['failureSummary', 'translationNotice'])
    result = _run_reader_js(functions + '\nconst REM = ' + json.dumps(shell) + ';\n' + r'''
      REM.owner = 'people/owner.md';
      const known = () => ({status: 'Investigated'}), listedRecords = () => [{written: true, category: 'people'}];
      const el = (tag, attrs) => attrs;
      const failure = failureSummary({failed: REM.brief_logs.slice(0, 2), changed: []});
      uiLanguage = 'zh'; UI.zh = {};
      console.log(JSON.stringify([failure.text, translationNotice().text]));
    ''')
    assert 'Model access was refused. Restore access before retrying.' in result[0]
    assert 'A request timed out.' in result[0]
    assert 'No memory pages were written' in result[0]
    assert result[1].startswith('1 page could not be translated.')
    assert 'private payload' not in json.dumps(shell)


def test_threads_use_current_original_and_preserve_translated_deadline():
    names = ['threads', 'rawSection', 'listItems', 'isCalm', 'writtenDates', 'writtenDatePattern', 'calendarDay', 'daysSince']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0) for name in names)
    result = _run_reader_js(functions + r'''
      const REM = {as_of: '2026-10-03', source_context: {}}, DAY_MS = 86400000;
      const COMMENT = /<!--[\s\S]*?-->/g, UNKNOWN_TEXT = /^Unknown$/, direction = () => 'mine';
      const r = {path: 'people/mara.md', category: 'people', original: '# Mara\n\n## Open threads\n- You owe Mara the old plan.\n',
        text: '# Mara\n\n## Open threads\n- You owe Mara the draft; requested 2026-10-01; due 2026-10-03 [1].\n'};
      const current = threads(r).items[0];
      r.original = r.text; r.shown = 'zh';
      r.text = '# Mara\n\n## Open threads\n- 请交初稿 [1]。\n';
      const translated = threads(r).items[0];
      r.shown = ''; r.text = '# Mara\n\n## Open threads\nUnknown. Historical requests do not establish pending work.\n';
      console.log(JSON.stringify([current, translated, threads(r).items.length]));
    ''')
    assert result[0]['due'] == result[1]['due'] == '2026-10-03'
    assert result[0]['since'] == result[1]['since'] == '2026-10-01'
    assert result[1]['text'] == '请交初稿 [1]。'
    assert result[2] == 0


def test_reviewed_facts_use_updated_english_instead_of_saved_original():
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
                          for name in ['parseFacts', 'topLevelParts', 'rawSection'])
    result = _run_reader_js(functions + r'''
      const PARSED_FACTS = new Map(), COMMENT = /<!--[\s\S]*?-->/g;
      const r = {path: 'people/mara.md', original: '# Mara\n\n## Facts\n- Role: Old CEO\n',
        text: '# Mara\n\n## Facts\n- Role: Programme manager (historical current unknown) [1]\n- Company: Unknown\n'};
      console.log(JSON.stringify([...parseFacts(r)]));
    ''')
    assert result == [['Role', [{'value': 'Programme manager', 'qualifier': 'historical current unknown', 'citations': ['1']}]],
                      ['Company', []]]


def test_plain_words_preserves_document_dates_and_a_deadline_not_shown_in_meta():
    function = re.search(r'function withoutDateClutter\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      console.log(JSON.stringify([
        withoutDateClutter('You owe Mara the agreement dated (2026-10-03).'),
        withoutDateClutter('Send the plan — due 2026-10-03.', {due: '2026-10-04'}),
        withoutDateClutter('Send the plan — due 2026-10-03.', {due: '2026-10-03'}),
        withoutDateClutter('She asked “Deliver by 2026-10-03 [1]”. [1]')
      ]));
    ''')
    assert result == ['You owe Mara the agreement dated (2026-10-03).',
                      'Send the plan — due 2026-10-03.', 'Send the plan.',
                      'She asked “Deliver by 2026-10-03 [1]”.']


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_undrafted_today_reason_and_action_follow_archived_reply_state(language):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['draftNote', 'primaryAction', 'threadUrl', 'draftNowButton'])
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js(functions + '\nUI.zh = ' + ui + '; uiLanguage = ' + json.dumps(language) + ';\n' + r'''
      const REM = {live: true, status: {worker: {enabled: true}, mailboxes: {outlook: 'last read failed 2026-11-07'}}, today_queue: []};
      const entry = {r: {path: 'people/fern.md'}, t: {text: 'You promised to watch the demo and send feedback.', since: '2026-11-01', dir: 'mine'}};
      const doneKey = () => 'fern', href = () => '#r=fern';
      const threadContact = () => ({address: 'fern@example.test'}), threadKind = () => ({mail: true, kind: 'outlook', channel: 'Outlook', thread: 'mail:outlook:demo'});
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const mailtoLink = () => ({text: 'compose is not a thread'}), fmtDate = day => day;
      const states = ['queued', 'unarchived', 'task'].map(state => {
        REM.today_queue = [{key: 'fern', keys: ['fern'], reply: {state, provider: 'outlook', thread: 'mail:outlook:demo',
          source: 'outlook:demo', last_word_yours: state === 'task', promise: 'watch the demo and send feedback', since: '2026-11-01'}}];
        return {state, note: draftNote(null, entry), action: primaryAction(entry)};
      });
      console.log(JSON.stringify(states));
    ''')
    queued, missing, task = result
    assert queued['action']['children'][0]['text'] == ('现在起草' if language == 'zh' else 'Draft now')
    assert queued['note'] is None  # never "queued for tonight" beside a live Draft now
    assert 'Outlook' in missing['note']['text']
    assert ('上次读取失败' if language == 'zh' else 'last read failed') in missing['note']['text']
    assert ('尚未归档' if language == 'zh' else 'not archived') in missing['note']['text']
    assert ('这是一件事，不是回信' if language == 'zh' else 'this is a task, not a reply') in task['note']['text']
    assert 'watch the demo and send feedback' in task['note']['text'] and '2026-11-01' in task['note']['text']
    for row in (missing, task):
        assert row['action']['text'] == ('打开 Outlook 原会话' if language == 'zh' else 'Open the Outlook thread')
        assert row['action']['href'].startswith('https://outlook.live.com/')
        assert row['action']['class'] == 'btn-quiet'


@pytest.mark.parametrize('live', [False, True])
def test_reply_card_highlights_slots_and_snapshot_replaces_all_live_controls(live):
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
                          for name in ['slotWhat', 'slotChoices', 'replyDraftCard'])
    result = _run_reader_js(functions + 'const REM = {live: ' + json.dumps(live) + r''', drafts: []};
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children, replaceChildren(...nodes) {this.children = nodes;},
        appendChild(node) {this.children.push(node);}});
      const mailbox = address => ({address, name: 'Fern'}), personByAddress = () => null;
      const icon = () => null;
      const remCommand = args => "co rem --root '/tmp/fictional notebook' " + args;
      const commandChip = command => ({tag: 'div', class: 'cmd', text: command});
      const draft = {id: 'demo', provider: 'gmail', to: 'fern@example.test', subject: 'Demo',
        body: 'Hello Fern. 【需要你：演示意见 — date not agreed】\nSecond 【需要你：时间 — date not agreed】'};
      const card = replyDraftCard(draft);
      const nodes = [];
      function visit(node) { if (node && typeof node === 'object') {nodes.push(node); (node.children || []).forEach(visit);} }
      visit(card);
      console.log(JSON.stringify({card, chips: nodes.filter(node => (node.class || '').split(' ').includes('owner-slot')),
        buttons: nodes.filter(node => node.tag === 'button').map(node => node.text),
        commands: nodes.filter(node => node.class === 'cmd')}));
    ''')
    assert len(result['chips']) == 2
    # Build 3b: the yellow "需要你填" box became a row to answer in, named by what REM needs.
    assert [chip['aria-label'] for chip in result['chips']] == ['演示意见', '时间']
    assert all(chip['role'] == 'group' and chip['children'][-1]['tag'] == 'input' for chip in result['chips'])
    if live:
        assert 'Send' in result['buttons'] and 'Write full screen' in result['buttons']
    else:
        # D-60 (build 3b review): a snapshot shows Send disabled and no command; the page says why once.
        assert result['buttons'] == ['Send'] and result['card']['children'][-2]['children'][0]['disabled'] == ''
        assert result['commands'] == []


def test_writer_refuses_slots_and_allows_send_after_owner_fills_them():
    function = re.search(r'function openWriter\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      const nodes = [], sent = [], REM = {};
      const el = (tag, attrs = {}, children = []) => {const node = {tag, ...attrs, children,
        addEventListener() {}, showModal() {}, focus() {}, close() {this.closed = true;}}; nodes.push(node); return node;};
      const mailbox = address => ({address, name: 'Fern'}), document = {body: {appendChild() {}}};
      openWriter({body: 'Feedback: 【需要你：意见 — date not agreed】', to: 'fern@example.test'}, null, body => sent.push(body));
      const send = nodes.find(node => node.tag === 'button' && node.text === 'Send');
      const body = nodes.find(node => node.tag === 'textarea'), dialog = nodes.find(node => node.tag === 'dialog');
      send.onclick();
      const blocked = {sent: sent.length, closed: !!dialog.closed, notice: nodes.some(node => node.textContent === 'Fill the marked part first')};
      body.value = 'The demo is ready.';
      send.onclick();
      console.log(JSON.stringify({blocked, sent}));
    ''')
    assert result['blocked'] == {'sent': 0, 'closed': False, 'notice': True}
    assert result['sent'] == ['The demo is ready.']


def test_today_reader_preserves_python_ranks_for_similar_requests_in_distinct_mail_threads(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from connectonion.rem import drafts, service
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.mail_archive import retain_message
    from connectonion.rem.reader import snapshot
    from connectonion.rem.store import refresh
    prepare(tmp_path)
    moment = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(service, 'now', lambda: moment)
    monkeypatch.setattr(service, 'mail_available', lambda kind: False)
    write_json(state_path(tmp_path, 'map.json'), {'owner': {'record': 'people/owner.md', 'addresses': ['owner@example.test']}})
    for name, ask in [('Fern', 'the signed permit review'), ('Mara', 'the signed permit review'), ('Avery', 'a separate budget decision')]:
        Notebook(tmp_path).write(f'people/{name.lower()}.md', f'# {name}\n\n## Open threads\n'
                                f'- You owe {name} {ask}; due 2026-11-08. [1]\n\n## Sources\n- [1] gmail:{name.lower()}\n')
        retain_message(tmp_path, 'gmail', {'id': name.lower(), 'from': name.lower() + '@example.test',
                       'to': ['owner@example.test'], 'subject': 'Review', 'thread': name.lower(),
                       'date': '2026-11-07T01:00:00+00:00'}, 'Please review.', fetched_at=moment.isoformat())
    refresh(tmp_path)
    data = snapshot(tmp_path, local=True)
    names = ['writtenDatePattern', 'writtenDates', 'threads', 'listItems', 'isCalm', 'direction', 'owing',
             'rawSection', 'threadEntries', 'obligationWords', 'obligationEvidence', 'sameObligation', 'threadGroups', 'todayEntries', 'doneKey', 'shortHash']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0) for name in names)
    result = _run_reader_js(functions + '\nconst REM = ' + json.dumps(data) + ';\n' + r'''
      const DAY_MS = 86400000, COMMENT = /<!--[\s\S]*?-->/g;
      let OWING = null;
      const calendarDay = value => value.slice(0, 10), daysSince = () => 0;
      const byPath = path => REM.records.find(row => row.path === path), listedRecords = () => REM.records;
      const plainLine = text => text, threadWords = text => text, isDone = () => false;
      console.log(JSON.stringify(todayEntries(threadEntries()).map(entry => doneKey(entry))));
    ''')
    assert result == [row['key'] for row in data['today_queue'] if row['section'] == 'today']
    assert {item['record'] for row in drafts.queue(tmp_path)[:2] for item in row['obligations']} == {key.split('\n')[0] for key in result[:2]}


def test_unresolved_mail_alias_opens_recorded_source_instead_of_a_guessed_provider_url():
    function = re.search(r'function primaryAction\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      const REM = {today_queue: [{key: 'fern', reply: {state: 'unarchived', provider: 'outlook', source: 'outlook:123456789abc'}}]};
      const doneKey = () => 'fern', threadKind = () => ({kind: 'outlook', mail: true}), href = () => '#r=fern';
      const el = (tag, attrs) => ({tag, ...attrs});
      console.log(JSON.stringify(primaryAction({r: {}, t: {text: 'You owe Fern a review. [3]'}})));
    ''')
    assert result['text'] == 'Open the recorded source'
    assert result['href'] == '#r=fern&h=src-3'


APPROVAL_DOM = r'''
let todaySent = null;  // the reply Today just sent; approvalUndoBar leaves its undo to Today's row
class ApprovalNode {
  constructor(tag, attrs = {}, children = []) {
    this.tagName = tag; Object.assign(this, attrs); this.children = []; this.listeners = {};
    this.disabled = !!attrs.disabled; this.checked = false; this._text = attrs.text || '';
    this.classList = {contains: name => (this.class || '').split(' ').includes(name)};
    this.append(...children);
  }
  append(...nodes) { for (const n of nodes.filter(n => n != null)) this.appendChild(n); }
  appendChild(n) { this.children.push(n); if (typeof n === 'object') n.parent = this; return n; }
  get textContent() { return this._text + this.children.map(n => typeof n === 'string' ? n : n.textContent).join(''); }
  set textContent(value) { this._text = value; this.children = []; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(n => n !== this); }
  removeAttribute(key) { delete this[key]; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  showModal() { this.open = true; }
  close() { this.open = false; this.listeners.close?.(); }
  querySelectorAll(selector) {
    const names = selector.split(',').map(s => s.trim());
    const matches = n => names.some(s => s.startsWith('.') ? n.classList.contains(s.slice(1)) : s.startsWith('#') ? n.id === s.slice(1) : n.tagName === s);
    return this.children.filter(n => typeof n === 'object').flatMap(n => [...(matches(n) ? [n] : []), ...n.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0]; }
}
const el = (tag, attrs, children) => new ApprovalNode(tag, attrs, children);
const document = {body: el('body'), documentElement: {classList: {contains: () => true}},
  getElementById(id) {return this.body.querySelector('#' + id);}};
const remCommand = command => 'co rem ' + command, render = () => {}, threadStates = {};
const privateFallback = node => node;
let approvalTimer; const setInterval = () => 1, clearInterval = () => {};
const REM = {live: true, drafts: [], approval_pending: [], approval_outcomes: [
  {id: 'reply:fern', kind: 'reply', to: 'fern@example.test', subject: 'Review', body: 'Friday works.', private: true},
  {id: 'reply:elara', kind: 'reply', to: 'elara@example.test', body: '【需要你：日期 — 未约定】', blocked: true},
  {id: 'handled:fern', kind: 'handled', title: 'Fern Vale', text: 'Invite sent.'},
  {id: 'task:fern', kind: 'task', title: 'Fern Vale', text: 'Review pilot.'}]};
const calls = [];
let failUndo = true;
const approvalRequest = async payload => {
  calls.push(payload);
  return {results: payload.ids.map(id => ({id, release_at: new Date(Date.now() + 600000).toISOString(),
    status: payload.action === 'undo' ? (failUndo ? 'error' : 'cancelled') : id.startsWith('handled') ? 'done' : id.startsWith('task') ? 'queued' : 'held',
    ...(payload.action === 'undo' && failUndo ? {error: 'Cancellation failed'} : {})}))};
};
'''


def approval_functions(*names):
    return '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0) for name in names)


def test_approval_sheet_blocks_slots_and_freezes_successful_edits():
    result = _run_reader_js(APPROVAL_DOM + approval_functions('approvalStatus', 'openApprovalSheet', 'approvalUndoBar', 'approveAllWords') + r'''
(async () => {
  openApprovalSheet(REM.approval_outcomes);
  const sheet = document.getElementById('approval-sheet'), checks = sheet.querySelectorAll('input');
  const initially = checks.map(c => [c.checked, c.disabled]);
  const edits = sheet.querySelectorAll('textarea'), saves = sheet.querySelectorAll('button').filter(b => b.textContent === 'Save reply');
  edits[1].value = 'Tuesday works.'; edits[1].oninput(); saves[1].onclick();
  await document.getElementById('approval-confirm').onclick();
  console.log(JSON.stringify({initially, calls, frozen: [...edits, ...saves].every(node => node.disabled),
    privateRows: sheet.querySelectorAll('.private').length, results: sheet.querySelectorAll('.approval-result').map(n => n.textContent)}));
})();
''')
    assert result['initially'] == [[True, False], [False, True], [True, False], [True, False]]
    assert result['calls'][0]['bodies'] == {'reply:elara': 'Tuesday works.'}
    assert result['frozen'] is True
    assert result['privateRows'] == 1
    assert result['results'] == ['Held for 10 minutes', 'Held for 10 minutes', 'Marked done', 'Task queued']


def test_approval_undo_failure_can_be_retried_before_expiry():
    result = _run_reader_js(APPROVAL_DOM + approval_functions('approvalStatus', 'approvalUndoBar', 'approveAllWords') + r'''
(async () => {
  REM.approval_pending = [{...REM.approval_outcomes[0], status: 'held', release_at: new Date(Date.now() + 600000).toISOString()}];
  approvalUndoBar();
  const bar = document.getElementById('approval-undo'), undo = bar.querySelector('button');
  await undo.onclick(); const retryable = !undo.disabled;
  failUndo = false; await undo.onclick();
  console.log(JSON.stringify({retryable, calls, final: bar.textContent, pending: REM.approval_pending}));
})();
''')
    assert result['retryable'] is True
    assert len(result['calls']) == 2
    assert result['final'].startswith('Cancelled') and result['pending'] == []


def test_static_approval_cta_and_durable_failure_copy():
    result = _run_reader_js(APPROVAL_DOM + approval_functions('approvalHeader', 'approveAllWords', 'approvalProblems') + r'''
      REM.live = false;
      REM.approval_pending = [{id:'reply:fern', to:'fern@example.test', status:'error', error:'Timed out'}];
      const header = approvalHeader();
      console.log(JSON.stringify({disabled: header.querySelector('button').disabled, instruction: header.querySelector('code'),
        failures: header.querySelector('.approval-problems').textContent}));
    ''')
    assert result['disabled'] is True and result.get('instruction') is None  # D-60: no command to copy
    assert 'Delivery not confirmed' in result['failures'] and 'Timed out' in result['failures']


def test_approval_header_reads_restored_outcomes_when_reopened():
    result = _run_reader_js(APPROVAL_DOM + approval_functions('approvalHeader', 'approveAllWords', 'approvalProblems') + r'''
      let opened;
      const openApprovalSheet = items => {opened = items.map(item => item.id);};
      const restored = REM.approval_outcomes[0]; REM.approval_outcomes = [];
      const header = approvalHeader();
      REM.approval_outcomes = [restored]; header.querySelector('button').onclick();
      console.log(JSON.stringify(opened));
    ''')
    assert result == ['reply:fern']


def test_static_snapshot_never_offers_live_undo():
    result = _run_reader_js(APPROVAL_DOM + approval_functions('approvalStatus', 'approvalUndoBar', 'approveAllWords') + r'''
      REM.live = false;
      REM.approval_pending = [{id:'reply:fern', status:'held', release_at:new Date(Date.now() + 600000).toISOString()}];
      approvalUndoBar();
      console.log(JSON.stringify({bar:!!document.getElementById('approval-undo'), calls}));
    ''')
    assert result == {'bar': False, 'calls': []}


def test_approval_request_freezes_all_controls_until_response():
    dom = APPROVAL_DOM.replace('const approvalRequest = async payload =>', 'let approvalRequest = async payload =>')
    result = _run_reader_js(dom + approval_functions('approvalStatus', 'openApprovalSheet', 'approvalUndoBar', 'approveAllWords') + r'''
(async () => {
  let settle;
  approvalRequest = payload => new Promise(resolve => {settle = resolve;});
  openApprovalSheet(REM.approval_outcomes);
  const sheet = document.getElementById('approval-sheet');
  const pending = document.getElementById('approval-confirm').onclick();
  const controls = sheet.querySelectorAll('.approval-row').flatMap(row => row.querySelectorAll('input, textarea, button'));
  const frozen = [...controls, document.getElementById('approval-confirm'), sheet.querySelectorAll('button').find(b => b.textContent === 'Close')].every(n => n.disabled);
  settle({results: []}); await pending;
  console.log(JSON.stringify({frozen, restored: !sheet.querySelector('input').disabled}));
})();
''')
    assert result == {'frozen': True, 'restored': True}






def test_session_mentions_skip_regex_scans_for_absent_names(monkeypatch):
    """Large sessions with no candidate name should require no name regex search."""
    from connectonion.rem import sessions
    person = {'path': 'people/fern.md', 'title': 'Fern Vale', 'text': '# Fern Vale'}
    session = {'path': 'sessions/demo.md', 'text': '# Demo\n\n## What you typed\n' + 'cedar implementation details ' * 2000}
    original = sessions.re.search
    compile_original = sessions.re.compile
    scans = []
    class Pattern:
        def __init__(self, compiled):
            self.compiled = compiled
        def search(self, text):
            scans.append(text)
            return self.compiled.search(text)
    def compile_pattern(pattern, *args, **kwargs):
        compiled = compile_original(pattern, *args, **kwargs)
        return Pattern(compiled) if "Fern" in str(pattern) else compiled
    def search(pattern, text, *args, **kwargs):
        if 'Fern' in str(pattern):
            scans.append(pattern)
        return original(pattern, text, *args, **kwargs)
    monkeypatch.setattr(sessions.re, 'search', search)
    monkeypatch.setattr(sessions.re, 'compile', compile_pattern)
    assert sessions.mentions([person], [session]) == {}
    assert scans == []


def test_observed_versions_uses_supplied_records_and_one_metadata_read(tmp_path):
    import hashlib
    import sqlite3
    from connectonion.rem.threads import observed_versions
    state = tmp_path / '.state'
    state.mkdir()
    db = sqlite3.connect(state / 'rem.db')
    db.execute('create table messages (id text, time text, thread text, source text, body_path text)')
    db.executemany('insert into messages values (?,?,?,?,?)', [
        ('gmail:first', '2026-11-01', 't', 'gmail', None),
        ('gmail:last', '2026-11-07', 't', 'gmail', None),
        ('gmail:empty', '', 'u', 'gmail', None),
        ('gmail:null', None, 'u', 'gmail', None)])
    db.commit()
    db.close()
    digest = hashlib.sha256(b'first').hexdigest()[:12]
    rows = [{'path': 'people/fern.md', 'text': f'# Fern\n\n## Sources\n- [1] gmail:{digest}\n- [2] gmail:empty\n'}]
    assert observed_versions(tmp_path, rows) == {'t': 'gmail:last', 'u': 'gmail:empty'}


def test_session_mentions_prefilter_preserves_unicode_case_matching():
    from connectonion.rem.sessions import mentions
    person = {'path': 'people/ipek.md', 'title': 'İpek Vale', 'text': '# İpek Vale'}
    session = {'path': 'sessions/demo.md', 'text': '# Demo\n\n## What you typed\nAsk Ipek Vale for feedback.\n'}
    assert mentions([person], [session]) == {'people/ipek.md': ['sessions/demo.md']}


def test_a_waiting_reply_is_drafted_now_and_answered_inside_its_thread():
    """Live: no "queued for tonight" beside Draft now. Static: say it waits, never with a command (D-60)."""
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['draftNote', 'draftNowButton'])
    result = _run_reader_js(functions + r'''
      const REM = {live: true, status: {worker: {enabled: true}},
        today_queue: [{key: 'avery', keys: ['avery'], reply: {state: 'queued', provider: 'outlook', thread: 'mail:outlook:pilot'}}]};
      const doneKey = () => 'avery', remCommand = args => 'co rem ' + args;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: [].concat(children), insertAdjacentHTML() {}});
      const entry = {r: {path: 'people/avery.md'}, t: {text: 'Reply to Avery.'}};
      const liveNote = draftNote(null, entry);
      REM.live = false;
      console.log(JSON.stringify({liveNote, staticNote: draftNote(null, entry)}));
    ''')
    assert result['liveNote'] is None
    assert result['staticNote']['class'] == 'quiet-line draft-reason' and 'co rem' not in json.dumps(result['staticNote'])


def test_today_card_never_answers_an_existing_thread_with_a_new_mail():
    """A mail-app compose has no In-Reply-To; only a person with no mail thread at all gets one,
    even when the thread's subject was never recorded."""
    function = re.search(r'function cardStep\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      const REM = {live: false}, threadDraft = () => null, approvalTask = () => null, looksDone = () => false;
      let reply = {state: 'queued', provider: 'outlook', thread: 'mail:outlook:pilot'}, kind = {mail: true};
      const queuedReply = () => reply, threadKind = () => kind;
      const threadContact = () => ({address: 'avery@example.com', subject: '', name: 'Avery'});
      const unrecordedSubject = cardStep({});
      reply = null; kind = null;
      console.log(JSON.stringify({unrecordedSubject, noThread: cardStep({})}));
    ''')
    assert result == {'unrecordedSubject': 'live', 'noThread': 'write'}

HAND = ['todayRow', 'obligationKey', 'rowTask', 'keepTask', 'handed', 'hostPost', 'liveHere', 'handOff',
        'handButtons', 'handState', 'followTask', 'seeResult', 'dotted', 'talkMenu', 'stripMarksDone', 'stripDone']


def _hand_js(body):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in HAND)
    return _run_reader_js('const AGENT_NAMES = { codex: "Codex", claude: "Claude" }, ACTIVE_TASK = ["queued", "starting", "running"], OPEN_TALKS = new Map();\n'
                          + functions + r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: children.filter(Boolean),
        append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; }});
      const doneKey = entry => entry.key, location = {protocol: 'http:'}, setTimeout = () => {};
      const texts = node => node.children[0].children.filter(child => child.class !== 'sep').map(child => child.text).filter(Boolean);
      const line = node => node.children[0].children.map(child => child.class === 'talk-menu' ? 'menu' : child.text).filter(Boolean);
      const row = (key, task) => ({key, keys: [key], task});
''' + body)


def test_a_handed_row_says_where_the_work_is_with_stop_take_back_and_see_result():
    result = _hand_js(r'''
      const REM = {live: true, today_queue: [row('run', {id: 'a', by: 'rem', agent: 'codex', result: 'running'}),
        row('done', {id: 'b', agent: 'claude', result: 'completed'}),
        row('fail', {id: 'c', agent: 'codex', result: 'failed', reason: 'codex CLI not found'}),
        row('open', null)]};
      const shown = Object.fromEntries(['run', 'done', 'fail', 'open'].map(key => [key, texts(handOff({key}))]));
      REM.live = false;
      shown.snapshot = texts(handOff({key: 'run'}));
      REM.live = true;
      shown.line = line(handOff({key: 'open'}));
      shown.runLine = line(handOff({key: 'run'}));
      console.log(JSON.stringify(shown));
    ''')
    assert result['run'] == ['Codex is working', 'REM started this', 'Stop', 'Take back from Codex']
    assert result['done'] == ['Claude finished', 'See result', 'Take back from Claude']
    assert result['fail'] == ['Codex stopped before finishing', 'codex CLI not found', 'See result', 'Take back from Codex']
    assert result['open'] == ['Hand to Codex', 'Hand to Claude']
    assert result['snapshot'] == ['Codex is working', 'REM started this']
    # One line, a dot between each action, the conversation behind one quiet menu.
    assert result['line'] == ['Hand to Codex', '·', 'Hand to Claude', '·', 'menu']
    assert result['runLine'] == ['Codex is working', '·', 'REM started this', '·', 'Stop', '·', 'Take back from Codex', '·', 'menu']


def test_take_back_puts_the_hand_buttons_back_on_the_row_in_place():
    result = _hand_js(r'''
      const REM = {live: true, today_queue: [row('done', {id: 'b', agent: 'codex', result: 'completed'})]};
      globalThis.fetch = async (url, options) => ({ok: true, status: 200, json: async () => ({status: 'cancelled'})});
      const node = handOff({key: 'done'});
      node.children[0].children.find(child => child.text?.startsWith('Take back from')).onclick().then(() =>
        console.log(JSON.stringify({after: texts(node), task: REM.today_queue[0].task})));
    ''')
    assert result == {'after': ['Hand to Codex', 'Hand to Claude'], 'task': None}


def test_a_queued_task_card_says_why_it_waits():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in ['taskResult', 'todayRow', 'rowTask', 'handed'])
    result = _run_reader_js(functions + r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: children.filter(Boolean),
        appendChild(child) { this.children.push(child); }, append(...items) { this.children.push(...items); }});
      const location = {protocol: 'http:'}, doneKey = entry => entry.key, copyToClipboard = () => {};
      const task = (wait, reason) => ({id: 'a', result: 'waiting', wait, reason});
      const REM = {live: true, today_queue: [
        {key: 'later', outcome: {kind: 'task', task: task('later', 'Another task is running; this one starts on a later tick tonight.')}},
        {key: 'budget', outcome: {kind: 'task', task: task('budget', '3 tasks already started tonight (limits.tasks_per_night).')}}]};
      console.log(JSON.stringify({later: taskResult({key: 'later'}), budget: taskResult({key: 'budget'})}));
    ''')
    for name, label in (('later', 'Queued: later tonight'), ('budget', 'Queued: budget used up')):
        card = result[name]
        assert card['children'][0]['text'] == label
        assert card['children'][1]['text'].startswith(('Another task', '3 tasks'))
        assert not any(child.get('class') == 'task-controls' for child in card['children'])


def test_no_task_card_says_this_version_does_not_run_it():
    # D-100: tasks run. The rc62 "held" state, its copy and its Copy-the-prompt button are gone.
    page = TEMPLATE.read_text()
    assert 'this version does not run it' not in page and '本版本暂不自动去做' not in page
    assert 'task.result === "held"' not in page


@pytest.mark.parametrize('language', ['en', 'zh'])
def test_the_empty_topic_list_says_rem_files_knowledge_on_its_night_run(language):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S)[0]
                          for name in ['topicList', 'graphT'])
    zh = re.search(r'const GRAPH_UI_ZH = \{.*?\n\};', page, re.S)[0]
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js(zh + '\n' + functions + '\nUI.zh = ' + ui + ';\nuiLanguage = ' + json.dumps(language) + ';\n' + r'''
      const el = (tag, attrs, children) => ({tag, ...attrs, children: (children || []).filter(c => c != null)});
      const topicRecords = () => [], remCommand = args => 'co rem ' + args, copyToClipboard = () => {};
      let view = null;
      const main = {set textContent(_) {}, appendChild: node => { view = node; }};
      const document = {getElementById: () => main};
      topicList();
      console.log(JSON.stringify(view));
    ''')
    text = json.dumps(result, ensure_ascii=False)
    # Owner, 2026-11-09: the category is Knowledge (知识), not a new "Topics" category.
    assert ('还没有知识条目' if language == 'zh' else 'No knowledge yet') in text
    assert ('REM 会在夜里那一轮从已有记录里整理知识。' if language == 'zh' else 'REM files knowledge from your records on its night run.') in text
    assert '主题' not in text and 'No topics' not in text and 'Topics are' not in text
    # D-60 (#2910): the night run files knowledge (daily.py backfill_topics); no command, no copy button.
    assert 'co rem' not in text and '"code"' not in text and '"复制"' not in text and '"Copy"' not in text


def test_project_lede_has_no_empty_most_often_clause_when_no_project_had_sessions():
    """'0 had sessions this quarter, most often .' is a broken sentence."""
    page = TEMPLATE.read_text()
    names = ['projectLede', 'projectActive', 'projectTierCounts']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = _run_reader_js(functions + r'''
      const pdT = (s, v = {}) => s.replace(/\{(\w+)\}/g, (_, k) => v[k]);
      const pdList = names => names.join(', '), pdIn = () => true, projectTicks = () => [], projectSessionDays = () => [];
      const projectRank = () => 0, projectTier = () => 'quiet', projectLate = () => null, projectMarks = () => [];
      const fmtTime = () => '', calendarDay = d => d, pdAt = () => 0, projectDot = () => null, projectStrip = () => null, REM = {as_of: '2026-11-09'};
      const pdWho = () => '', pdDay = d => d, el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const all = [{title: 'Harbour'}, {title: 'Lantern'}];
      let out;
      try { out = projectLede(all, {zoom: 'quarter', today: '2026-11-09'}); } catch (error) { out = String(error); }
      console.log(JSON.stringify(typeof out === 'string' ? out : JSON.stringify(out)));
    ''')
    assert 'most often .' not in result and 'most often ,' not in result
    assert 'no project had sessions this quarter' in result


def _reader_function(name):
    return re.search(r'function ' + name + r'\(.*?\n\}', TEMPLATE.read_text(), re.S)[0]


@pytest.mark.parametrize('language, expected', [('en', 'Knowledge'), ('zh', '知识')])
def test_the_knowledge_category_is_called_knowledge_not_topics(language, expected):
    """Owner, 2026-11-09: "你怎么又新增加了一个 category 呢？" The category keeps its name."""
    page = TEMPLATE.read_text()
    labels = re.search(r'const CATEGORY_LABEL = \{.*?\n\};', page, re.S)[0]
    graph = re.search(r'const GRAPH_UI_ZH = \{.*?\n\};', page, re.S)[0]
    names = re.search(r'const GRAPH_NAME = \{.*?\};', page)[0]
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    script = '\n'.join([labels, graph, names, _reader_function('label'), _reader_function('graphT'),
                        'UI.zh = ' + ui + ';', 'uiLanguage = ' + json.dumps(language) + ';',
                        "console.log(JSON.stringify({rail: label('knowledge'), legend: graphT(GRAPH_NAME.knowledge)}));"])
    assert _run_reader_js(script) == {'rail': expected, 'legend': expected}


def test_the_old_graph_address_lands_on_all_records():
    result = _run_reader_js(_reader_function('route') + '\n' + _reader_function('railActive') + r'''
      const ACTIVITY = new Set(['notes', 'logs']), location = {hash: '#view=graph&focus=knowledge%2Fheat.md'};
      const graph = railActive();
      location.hash = '#view=activity';
      console.log(JSON.stringify({graph, activity: railActive()}));
    ''')
    assert result == {'graph': 'all', 'activity': 'activity'}


WORKING_STORAGE = "{getItem: key => saved[key] ?? null, setItem: (key, value) => { saved[key] = value; }}"
BLOCKED_STORAGE = "{getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); }}"


@pytest.mark.parametrize('storage', [WORKING_STORAGE, BLOCKED_STORAGE], ids=['working', 'blocked'])
def test_all_records_remembers_graph_or_list_and_survives_blocked_storage(storage):
    result = _run_reader_js('const saved = {}; const localStorage = ' + storage + "; let allRecordsChoice = '';\n"
                            + _reader_function('allRecordsMode') + r'''
      const first = allRecordsMode();
      const chosen = allRecordsMode('list');
      const kept = allRecordsMode();
      allRecordsChoice = '';
      console.log(JSON.stringify({first, chosen, kept, again: allRecordsMode(), saved}));
    ''')
    assert result['first'] == 'graph' and result['chosen'] == 'list' and result['kept'] == 'list'
    if storage == WORKING_STORAGE:
        assert result['again'] == 'list' and list(result['saved'].values()) == ['list']
    else:  # this visit keeps the choice; nothing could be saved
        assert result['again'] == 'graph' and result['saved'] == {}


# ---------- opening is instant: the last page from disk, rebuilt behind it (owner, 2026-11-09) ----------
# Each open used to rebuild the whole notebook, and the cache key alone listed every
# file: 17 s of stat calls and 35-73 s of rendering on a 31,136-file notebook.

def _cached_reader(tmp_path, monkeypatch):
    from connectonion.rem import reader
    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path / "tmp"))
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    monkeypatch.setattr(reader, "_now", lambda: _Clock.seconds, raising=False)
    _Clock.seconds = 1_794_000_000.0
    return reader


class _Clock:
    """The render time the page shows, set by the test."""
    from datetime import datetime as real
    at = None
    seconds = 0.0     # the reader's own clock (reader._now), for its intervals

    @classmethod
    def now(cls, tz=None):
        return cls.at

    @classmethod
    def fromtimestamp(cls, *args, **kwargs):
        return cls.real.fromtimestamp(*args, **kwargs)


def test_a_second_open_of_a_large_notebook_lists_no_directory_and_is_instant(tmp_path, monkeypatch):
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    # Retained sources are most of a real notebook's files; the reader never shows them.
    for folder in range(200):
        directory = root / ".state" / "mail" / f"{folder:03}"
        directory.mkdir(parents=True)
        for item in range(100):
            (directory / f"{item}.json").write_text("{}")
    first = reader.open_snapshot(root, launch=False)

    def listed(*args, **kwargs):
        raise AssertionError("an unchanged notebook was listed again")
    for name in ("walk", "scandir", "listdir"):
        monkeypatch.setattr(os, name, listed)
    import glob  # 3.13+: pathlib's rglob bound os.scandir when it was imported; earlier ones call it
    if hasattr(glob, "_StringGlobber"):
        monkeypatch.setattr(glob._StringGlobber, "scandir", staticmethod(listed))
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: pytest.fail("rebuilt an unchanged notebook"),
                        raising=False)
    import time
    started = time.monotonic()
    second = reader.open_snapshot(root, launch=False)
    assert time.monotonic() - started < 1.0
    assert open(second["page"], encoding="utf-8").read() == open(first["page"], encoding="utf-8").read()
    assert "Alice Example" in open(second["page"], encoding="utf-8").read()


def test_a_changed_notebook_opens_the_last_page_at_once_and_rebuilds_it_behind(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    reader = _cached_reader(tmp_path, monkeypatch)
    monkeypatch.setattr(reader, "datetime", _Clock)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    _Clock.at = datetime(2026, 11, 9, 8, 15, tzinfo=timezone.utc)
    first = open(reader.open_snapshot(root, launch=False)["page"], encoding="utf-8").read()
    assert '"as_of": "2026-11-09T08:15:00+00:00"' in first

    Notebook(root).write("people/bruno.md", "# Bruno Example\n")
    spawned = []
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: spawned.append(root) or True, raising=False)
    _Clock.seconds += 60
    # An explicit open is the owner acting: a minute after the last render, it still rebuilds now.
    stale = reader.open_snapshot(root, launch=False)
    assert open(stale["page"], encoding="utf-8").read() == reader._updating(first)   # the last page, at once, marked
    assert spawned == [root]                                         # and one rebuild behind it
    assert "being built" in stale["note"]

    _Clock.at = datetime(2026, 11, 9, 9, 40, tzinfo=timezone.utc)
    reader.refresh(root)                                             # what the background process runs
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: pytest.fail("a rebuild made itself stale"))
    fresh = open(reader.open_snapshot(root, launch=False)["page"], encoding="utf-8").read()
    assert "Bruno Example" in fresh and '"as_of": "2026-11-09T09:40:00+00:00"' in fresh
    # The page names the time it was rendered: «更新于 HH:MM».
    assert 't("Updated") + " " + fmtTime(REM.as_of)' in fresh and '"Updated": "更新于"' in fresh


def test_the_saved_page_is_private_and_a_planted_link_is_refused(tmp_path, monkeypatch):
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    page = reader.open_snapshot(root, launch=False)["page"]
    assert tmp_path / "rem" not in __import__("pathlib").Path(page).parents
    if os.name == "nt":
        return
    assert os.stat(page).st_mode & 0o777 == 0o600
    folder = os.path.dirname(page)
    assert os.stat(folder).st_mode & 0o777 == 0o700
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    os.unlink(page)
    os.symlink(victim, page)
    with pytest.raises(OSError):
        reader.open_snapshot(root, launch=False)
    assert victim.read_text() == "keep"


def test_the_rebuild_behind_an_open_runs_in_a_real_detached_process(tmp_path, monkeypatch):
    """The mocks above stand in for this: python -m connectonion.rem.reader ROOT full."""
    import tempfile
    import time
    from connectonion.rem import reader
    (tmp_path / "tmp").mkdir()
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))  # the child finds the same cache
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    reader.open_snapshot(root, launch=False)
    Notebook(root).write("people/bruno.md", "# Bruno Example\n")
    stale = reader.open_snapshot(root, launch=False)       # rendered just now: the rebuild waits
    assert "Bruno Example" not in open(stale["page"], encoding="utf-8").read()
    reader.owner_changed(root)                             # unless the owner acted
    deadline = time.monotonic() + 90
    while reader.saved(root, "full").get("version") != reader.reader_version(root):
        assert time.monotonic() < deadline, open(reader._cached(root, "build.log")).read()
        time.sleep(0.2)
    assert "Bruno Example" in open(reader.page_path(root, "file.html"), encoding="utf-8").read()


def test_an_owner_action_made_while_a_rebuild_runs_is_rendered_by_that_rebuild(tmp_path, monkeypatch):
    """A request that finds a build running starts no second one, so the running one
    checks again for the owner's own action; other writes wait for the interval."""
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    reader.open_snapshot(root, launch=False)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    original, passes = reader._render, []

    def build(root, which, *args):
        passes.append(which)
        rendered = original(root, which, *args)
        if len(passes) == 1:
            Notebook(root).write("people/bruno.md", "# Bruno Example\n")  # lands mid-build
        return rendered
    monkeypatch.setattr(reader, "_render", build)
    reader.refresh(root, ["full"])
    assert passes == ["full"]                                   # a night write: next interval
    Notebook(root).write("people/carla.md", "# Carla Example\n")
    passes.clear()

    def owner_build(root, which, *args):
        passes.append(which)
        rendered = original(root, which, *args)
        if len(passes) == 1:
            Notebook(root).write("people/dara.md", "# Dara Example\n")
            reader.owner_changed(root)                          # the owner, mid-build
        return rendered
    monkeypatch.setattr(reader, "_render", owner_build)
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: None)
    reader.refresh(root, ["full"])
    assert passes == ["full", "full"]
    assert reader.saved(root, "full")["version"] == reader.reader_version(root)
    assert "Dara Example" in open(reader.page_path(root, "file.html"), encoding="utf-8").read()



def test_the_note_says_a_page_is_being_built_only_when_a_build_started(tmp_path, monkeypatch):
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    assert "being built" not in reader.open_snapshot(root, launch=False)["note"]
    Notebook(root).write("people/bruno.md", "# Bruno Example\n")
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: False)   # refused: a failing build backs off
    assert "being built" not in reader.open_snapshot(root, launch=False)["note"]


def test_a_new_install_changes_the_saved_pages_key_even_with_the_same_template(tmp_path, monkeypatch):
    """The page shows the package version, and a release can change Python without touching reader.html."""
    import connectonion
    from connectonion.rem import reader
    root = tmp_path / "rem"
    prepare(root)
    monkeypatch.setattr(connectonion, "__version__", "1.9.3")
    key = reader.reader_version(root)
    monkeypatch.setattr(connectonion, "__version__", "1.9.4")
    assert reader.reader_version(root) != key


def test_a_quiet_notebook_still_rebuilds_past_midnight_and_after_the_interval(tmp_path, monkeypatch):
    """The Today queue, dates and "Next pass" depend on the clock, not only on files."""
    from datetime import datetime, timezone
    from connectonion.rem import service
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    from datetime import timedelta
    from connectonion.rem.config import read_config
    midnight = datetime(2026, 11, 10, tzinfo=service.notebook_zone(read_config(root)))
    moment = [midnight - timedelta(minutes=2)]
    monkeypatch.setattr(service, "now", lambda: moment[0])
    reader.open_snapshot(root, launch=False)
    key = reader.reader_version(root)
    moment[0] = midnight + timedelta(minutes=1)
    assert reader.reader_version(root) != key                     # the notebook's day is in the key
    spawned = []
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: spawned.append(builds) or True)
    reader.cached_page(root, "file.html")
    assert spawned == []                                          # rendered three minutes ago: wait
    reader.refresh(root, ["full"])
    _Clock.seconds += reader.REBUILD_INTERVAL + 1                 # nothing changed, but it is old
    reader.cached_page(root, "file.html")
    assert spawned == [["full"]]


def test_details_and_page_are_published_together(tmp_path, monkeypatch):
    """A reload after an owner action must not get a new page over old details."""
    reader = _cached_reader(tmp_path, monkeypatch)
    # No detached build: one still holding the build lock made this test's refresh a
    # no-op, and the saved page stayed behind the new person (CI 3.11 and 3.12).
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: True)
    root = tmp_path / "rem"
    prepare(root)
    reader.cached_page(root, "live.html")
    reader.refresh(root)
    before = reader.saved(root, "live")
    original = reader.snapshot

    def snapshot(root, **options):
        if "today" not in options:  # the details are being built: nothing is published yet
            assert reader.saved(root, "live") == before
        return original(root, **options)
    monkeypatch.setattr(reader, "snapshot", snapshot)
    Notebook(root).write("people/fern-holt.md", "# Fern Holt\n")
    _Clock.seconds += 1
    reader.refresh(root)
    assert reader.saved(root, "live")["version"] == reader.saved(root, "full")["version"] == reader.reader_version(root)
    assert "Fern Holt" in open(reader.page_path(root, "data.json"), encoding="utf-8").read()


def test_owner_actions_after_the_last_pass_are_not_dropped_and_a_corrupt_mark_is_now(tmp_path, monkeypatch):
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    reader.open_snapshot(root, launch=False)
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: False)
    original, passes = reader.snapshot, []

    def snapshot(root, **options):
        passes.append(1)
        data = original(root, **options)
        if len(passes) <= 4:                                      # the owner, during four passes
            Notebook(root).write(f"people/action-{len(passes)}.md", f"# Action {len(passes)}\n")
            reader.owner_changed(root)
        return data
    monkeypatch.setattr(reader, "snapshot", snapshot)
    Notebook(root).write("people/start.md", "# Start\n")
    reader.refresh(root, ["full"])
    assert len(passes) == 5
    assert "Action 4" in open(reader.page_path(root, "file.html"), encoding="utf-8").read()
    passes.clear()
    monkeypatch.setattr(reader, "snapshot", lambda root, **options: passes.append(1) or original(root, **options))
    reader._cached(root, "owner").write_text("not a time")
    Notebook(root).write("people/later.md", "# Later\n")
    reader.refresh(root, ["full"])                                # no error: the mark reads as now
    assert len(passes) == 1 and float(reader._cached(root, "owner").read_text()) == _Clock.seconds


def test_a_failed_rebuild_is_recorded_shown_and_backed_off(tmp_path, monkeypatch):
    import subprocess
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    reader.open_snapshot(root, launch=False)
    reader._cached(root, "build.log").write_text("".join(f"line {n}\n" for n in range(500)))
    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: started.append(a))
    assert reader._spawn_refresh(root, ["full"]) is True
    assert len(reader._cached(root, "build.log").read_text().splitlines()) <= 200
    monkeypatch.setattr(reader, "snapshot", lambda root, **options: (_ for _ in ()).throw(RuntimeError("fictional failure")))
    Notebook(root).write("people/bruno.md", "# Bruno Example\n")
    with pytest.raises(RuntimeError):
        reader.main([str(root), "full"])                          # the detached process
    failed = reader.failure(root)
    assert failed and failed["log"] == str(reader._cached(root, "build.log"))
    assert reader._spawn_refresh(root, ["full"]) is False and len(started) == 1   # backed off
    note = reader.open_snapshot(root, launch=False)["note"]
    assert "rebuild failed" in note and str(reader._cached(root, "build.log")) in note
    _Clock.seconds += reader.REBUILD_INTERVAL + 1
    assert reader._spawn_refresh(root, ["full"]) is True and len(started) == 2


def test_a_refused_cache_folder_renders_now_and_says_why(tmp_path, monkeypatch):
    reader = _cached_reader(tmp_path, monkeypatch)
    if os.name == "nt":
        pytest.skip("POSIX ownership and modes")
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    folder = __import__("pathlib").Path(os.environ["CONNECTONION_REM_CACHE"])
    folder.mkdir(mode=0o777)
    os.chmod(folder, 0o777)                                       # as if someone else made it
    result = reader.open_snapshot(root, launch=False)
    assert "Alice Example" in open(result["page"], encoding="utf-8").read()
    assert "rendered now" in result["note"] and str(folder) in result["note"]
    text, _ = reader.cached_page(root, "live.html")
    assert "Alice Example" in text


def test_the_page_reloads_only_through_one_door_that_keeps_the_owners_place():
    """After an action or a newer render: wait for the new render, keep scroll, open
    details and the view, and never reload over a draft being written."""
    page = TEMPLATE.read_text()
    reloads = [m.start() for m in re.finditer(r"location\.reload\(\)", page)]
    door = re.search(r"function reloadOnto\(.*?\n\}", page, re.S)
    assert door and len(reloads) == 1 and door.start() < reloads[0] < door.end()
    choice = re.search(r"function reloadChoice\(.*?\n\}", page, re.S).group(0)
    result = _run_reader_js(choice + r'''
      const base = {latest: {as_of: "2026-11-09T09:40:00+00:00"}, asOf: "2026-11-09T08:15:00+00:00", typing: false, unsaved: false};
      console.log(JSON.stringify({
        newer: reloadChoice(base),
        same: reloadChoice({...base, asOf: base.latest.as_of}),
        none: reloadChoice({...base, latest: null}),
        typing: reloadChoice({...base, typing: true}),
        draft: reloadChoice({...base, unsaved: true}),
        older: reloadChoice({...base, latest: {as_of: "2026-11-09T07:00:00+00:00"}}),
      }));''')
    assert result == {"newer": "reload", "same": None, "none": None, "typing": None, "draft": "offer", "older": None}
    # Open sections are known by their id, else their summary; never by position.
    key = re.search(r"function detailsKey\(.*?\}\n", page, re.S).group(0)
    keys = _run_reader_js(key + r'''
      const summary = text => ({querySelector: () => ({textContent: text})});
      console.log(JSON.stringify([detailsKey({id: "people-columns", ...summary("Columns")}),
                                  detailsKey({id: "", ...summary("Review reply")})]));''')
    assert keys == ["#people-columns", "Review reply"]
    assert '"Newer page · Reload": "有更新 · 刷新"' in page


def test_a_quiet_visible_page_is_walked_every_interval_and_rebuilt_only_when_needed(tmp_path, monkeypatch):
    """A rebuild is ~100 s of CPU on a real notebook; the walk is ~17 s of stat calls."""
    from datetime import datetime, timedelta, timezone
    from connectonion.rem import service
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    day = [datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(service, "now", lambda: day[0])
    reader.open_snapshot(root, launch=False)
    walks, renders, original_walk, original = [], [], reader.tree_version, reader.snapshot
    monkeypatch.setattr(reader, "tree_version", lambda root: walks.append(1) or original_walk(root), raising=False)
    monkeypatch.setattr(reader, "snapshot", lambda root, **o: renders.append(1) or original(root, **o))
    # The detached build, run here: what a visible page's poll starts.
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: reader.refresh(root, builds) or True)
    start = _Clock.seconds
    at = lambda minutes: setattr(_Clock, "seconds", start + minutes * 60 + 1) or reader.cached_page(root, "file.html")
    at(10)                                       # the first walk records the tree (the first page was built without one)
    renders.clear(), walks.clear()
    start = _Clock.seconds
    for minutes in (10, 20, 50):
        at(minutes)
    assert len(walks) == 3 and renders == []     # walked, nothing differed: no rebuild
    at(60)
    assert renders == [1]                        # "Next pass" may be at most STALE_SCHEDULE_SECONDS late
    assert reader.STALE_SCHEDULE_SECONDS == 3600
    renders.clear()
    (root / "people/alice.md").write_text("# Alice Example, edited by another tool\n")
    at(65)
    assert renders == []                         # the open never walks; the interval has not passed
    at(71)
    assert renders == [1] and "edited by another tool" in open(reader.page_path(root, "file.html"), encoding="utf-8").read()
    renders.clear()
    day[0] += timedelta(days=1)
    at(82)
    assert renders == [1]                        # the notebook's day changed



def test_a_crash_at_any_write_of_a_publish_leaves_a_consistent_set(tmp_path, monkeypatch):
    """The page served, its details and /rem/version must agree, or the open page
    reloads onto itself every second until the next good build."""
    import json as _json
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: True)
    reader.cached_page(root, "live.html")
    reader.refresh(root)
    real, crash_at = reader._replace, 0
    while True:
        crash_at += 1
        _Clock.seconds += 1
        Notebook(root).write(f"people/person-{crash_at}.md", f"# Person {crash_at}\n")
        writes = []

        def failing(path, text):
            writes.append(path)
            if len(writes) == crash_at:
                raise OSError("fictional disk full")
            real(path, text)
        monkeypatch.setattr(reader, "_replace", failing)
        try:
            reader.refresh(root)
            crashed = False
        except OSError:
            crashed = True
        monkeypatch.setattr(reader, "_replace", real)
        page, _ = reader.cached_page(root, "live.html")
        details, _ = reader.cached_page(root, "data.json")
        served = re.search(r'"as_of": "([^"]+)"', page).group(1)
        assert served == reader.latest(root)["as_of"] == _json.loads(details)["as_of"], crash_at
        if not crashed:
            break
    assert crash_at > 2   # every write of a publish was tried



def test_one_refresh_gives_the_page_and_its_details_one_time(tmp_path, monkeypatch):
    """The live page and the snapshot's details are built one after the other; when
    the second build crosses a second, they disagreed and an open page reloaded
    itself every second (seen on a slow CI runner)."""
    import json as _json
    from datetime import datetime as real, timedelta, timezone
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: True)
    ticks = [real(2026, 11, 9, 8, 15, tzinfo=timezone.utc)]

    class Ticking(_Clock):
        @classmethod
        def now(cls, tz=None):  # every reading is a second later, as on a slow machine
            ticks.append(ticks[-1] + timedelta(seconds=1))
            return ticks[-1]
    monkeypatch.setattr(reader, "datetime", Ticking)
    reader.refresh(root)
    page, _ = reader.cached_page(root, "live.html")
    details, _ = reader.cached_page(root, "data.json")
    served = re.search(r'"as_of": "([^"]+)"', page).group(1)
    assert served == reader.latest(root)["as_of"] == _json.loads(details)["as_of"]


def test_an_open_tab_reaches_the_newest_render_through_the_link_it_was_given(tmp_path, monkeypatch):
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: True)
    link = reader.open_snapshot(root, launch=False)["link"]
    for n in range(1, 4):                                         # three rebuilds behind it
        Notebook(root).write(f"people/person-{n}.md", f"# Person Number {n}\n")
        _Clock.seconds += 1
        reader.refresh(root, ["full"])
    page = __import__("urllib.parse").parse.unquote(link.removeprefix("file://"))
    assert "Person Number 3" in open(page, encoding="utf-8").read()   # reload: the newest, never a missing file
    assert reader.open_snapshot(root, launch=False)["link"] == link



def test_a_build_rendered_after_its_partner_still_names_the_same_time(tmp_path, monkeypatch):
    """The live page is built on the first request; its details later, in the
    background. Rendered apart they named different seconds, and the page's
    details disagreed with /rem/version. Every saved build is rendered together."""
    import json as _json
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: True)
    monkeypatch.setattr(reader, "datetime", _Ticking)
    reader.cached_page(root, "live.html")                         # the first request: the page alone
    reader.refresh(root)                                          # then its details, behind it
    page, _ = reader.cached_page(root, "live.html")
    details, _ = reader.cached_page(root, "data.json")
    offline = open(reader.page_path(root, "file.html"), encoding="utf-8").read()
    served = re.search(r'"as_of": "([^"]+)"', page).group(1)
    assert served == reader.latest(root)["as_of"] == _json.loads(details)["as_of"]
    assert served == re.search(r'"as_of": "([^"]+)"', offline).group(1)


def test_a_stop_between_the_manifest_and_the_stable_link_is_repaired_on_read(tmp_path, monkeypatch):
    import json as _json
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: True)
    monkeypatch.setattr(reader, "datetime", _Ticking)
    reader.cached_page(root, "live.html")
    reader.refresh(root)
    link = reader.page_path(root, "file.html")
    real = reader._replace

    def stops_at_the_link(path, text):
        if path == link:
            raise OSError("fictional stop")
        real(path, text)
    monkeypatch.setattr(reader, "_replace", stops_at_the_link)
    Notebook(root).write("people/bruno.md", "# Bruno Example\n")
    _Clock.seconds += 1
    with pytest.raises(OSError):
        reader.refresh(root)
    monkeypatch.setattr(reader, "_replace", real)
    details, _ = reader.cached_page(root, "data.json")
    offline = open(reader.page_path(root, "file.html"), encoding="utf-8").read()
    assert reader.page_path(root, "file.html") == link
    assert re.search(r'"as_of": "([^"]+)"', offline).group(1) == _json.loads(details)["as_of"]
    assert "Bruno Example" in offline


class _Ticking:
    """A wall clock that moves a second each time it is read: a loaded CI runner."""
    from datetime import datetime as real, timezone
    at = real(2026, 11, 9, 8, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        from datetime import timedelta
        cls.at += timedelta(seconds=1)
        return cls.at

    @classmethod
    def fromtimestamp(cls, *args, **kwargs):
        return cls.real.fromtimestamp(*args, **kwargs)



def test_a_planted_link_at_the_stable_page_is_neither_followed_nor_returned(tmp_path, monkeypatch):
    reader = _cached_reader(tmp_path, monkeypatch)
    if os.name == "nt":
        pytest.skip("symlinks need privileges on Windows")
    root = tmp_path / "rem"
    prepare(root)
    reader.open_snapshot(root, launch=False)
    link = reader._cached(root, "file.html")
    victim = tmp_path / "victim.html"
    victim.write_text("planted")
    os.utime(victim, ns=(4_000_000_000 * 10**9, 4_000_000_000 * 10**9))   # newer than any build
    link.unlink()
    os.symlink(victim, link)
    with pytest.raises(OSError):
        reader.page_path(root, "file.html")
    assert victim.read_text() == "planted"


def test_co_rem_open_runs_where_there_is_no_fcntl(tmp_path):
    """Windows has no fcntl. The snapshot reads each row's task receipt through
    rem.tasks, whose top-level `import fcntl` made `co rem open` exit 1 there
    (windows-e2e, release/1.9.3). The cached open runs here with fcntl unimportable;
    REM's own lock is stood in for, as on Windows it takes msvcrt instead."""
    import sys
    script = ("import sys; sys.modules['fcntl'] = None\n"
              "from pathlib import Path\n"
              "from connectonion.rem import files, reader, tasks\n"
              "files._try_lock = lambda fd: None\n"
              "root = Path(sys.argv[1])\n"
              "assert tasks.receipt_for(root, 'people/mara.md\\nSend the notes') is None\n"
              "print(reader.open_snapshot(root, launch=False)['page'])\n")
    root = tmp_path / "unstarted notebook"
    result = subprocess.run([sys.executable, "-c", script, str(root)], capture_output=True,
                            text=True, cwd=os.getcwd(), timeout=50)
    assert result.returncode == 0, result.stderr[-2000:]
    assert "Not started" in open(result.stdout.strip(), encoding="utf-8").read()


# ---------- an open never waits on a build (1.9.4 hotfix) ----------
# The first co rem open after upgrading to 1.9.3 took 1025 s and printed one line.
# 1.9.3rc64 kept the file page out of the saved set's manifest, so 1.9.3 found "no
# page", took the build lock (waiting out the rebuild the upgrade had started) and
# rendered the whole notebook again in the foreground. A small notebook took the
# same road through "the last render took under 2 s".

def _saved_under_an_older_release(tmp_path, monkeypatch, shape):
    import connectonion
    reader = _cached_reader(tmp_path, monkeypatch)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    monkeypatch.setattr(connectonion, "__version__", "1.9.3")
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: True)
    reader.cached_page(root, "live.html")
    reader.refresh(root)
    if shape == "rc64-manifest":   # its _publish wrote the file page beside the set, never into it
        manifest = json.loads(reader._cached(root, "current.json").read_text())
        (reader._cache_dir() / manifest["files"].pop("file.html")).unlink()
        reader._cached(root, "current.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(connectonion, "__version__", "1.9.4")                # the upgrade
    return reader, root


@pytest.mark.parametrize("shape", ["upgrade", "rc64-manifest", "build-running"])
def test_after_an_upgrade_open_shows_the_saved_page_at_once_while_a_slow_build_runs(tmp_path, monkeypatch, shape):
    import threading
    import time
    from connectonion.rem import files
    reader, root = _saved_under_an_older_release(tmp_path, monkeypatch, shape)
    release, original = threading.Event(), reader._render
    monkeypatch.setattr(reader, "_render", lambda *args: (release.wait(30), original(*args))[1])
    lock = None
    if shape == "build-running":   # the rebuild the upgrade started holds the build lock
        lock = os.open(reader._cached(root, "build.lock"), os.O_CREAT | os.O_RDWR, 0o600)
        files._try_lock(lock)
    result = {}
    opener = threading.Thread(target=lambda: result.update(reader.open_snapshot(root, launch=False)), daemon=True)
    began = time.monotonic()
    opener.start()
    opener.join(2.0)
    took = time.monotonic() - began
    release.set()
    if lock is not None:
        os.close(lock)
    opener.join(60)
    assert took < 2.0, f"co rem open waited {took:.1f} s on a build"
    page = open(result["page"], encoding="utf-8").read()
    assert "Alice Example" in page and 'id="rem-updating"' in page
    assert "being built" in result["note"]


def test_a_stale_page_says_updating_in_the_readers_language_and_a_current_one_does_not(tmp_path, monkeypatch):
    reader, root = _saved_under_an_older_release(tmp_path, monkeypatch, "upgrade")
    served, building = reader.cached_page(root, "live.html")      # what GET /rem answers
    assert building and 'id="rem-updating"' in served
    mark = re.search(r'<script>(\(\(\) => \{[^<]*?rem-updating.*?)</script>', served, re.S).group(1)
    shown = {}
    for languages, browser in ((["zh", "en"], "en-AU"), (["en"], "zh-CN"), (["en"], "en-AU")):
        shown[f"{languages[0]}/{browser}"] = _run_reader_js(
            "const node = {}; const document = {getElementById: () => node};"
            f"const window = {{REM: {{your_languages: {json.dumps(languages)}}}}};"
            f"const navigator = {{language: {json.dumps(browser)}}};" + mark
            + "\nconsole.log(JSON.stringify(node.textContent));")
    assert shown == {"zh/en-AU": "正在更新…", "en/zh-CN": "正在更新…", "en/en-AU": "Updating…"}
    reader.refresh(root)                                           # the rebuild lands
    fresh, building = reader.cached_page(root, "live.html")
    assert not building and "rem-updating" not in fresh
    opened = reader.open_snapshot(root, launch=False)
    assert "rem-updating" not in open(opened["page"], encoding="utf-8").read()


def test_with_no_saved_page_at_all_open_renders_once_and_says_so_every_few_seconds(tmp_path, monkeypatch):
    import time
    reader = _cached_reader(tmp_path, monkeypatch)
    monkeypatch.setattr(reader, "PROGRESS_SECONDS", 0.05)
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: True)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice Example\n")
    original = reader._render
    monkeypatch.setattr(reader, "_render", lambda *args: (time.sleep(0.5), original(*args))[1])
    lines = []
    result = reader.open_snapshot(root, launch=False, say=lines.append)
    assert "Alice Example" in open(result["page"], encoding="utf-8").read()
    assert len(lines) >= 4 and "first" in lines[0], lines        # a line at once, then one per tick


def test_no_view_offers_a_command_to_copy():
    """D-60 (#2910): the reader never hands the owner a command; REM or the live reader does the work."""
    page = TEMPLATE.read_text()
    assert 'function commandChip' not in page and 'remCommand(' not in page and 'initCommand(' not in page
    assert not re.search(r'class: "cmd"|\.cmd\b', page)
    assert not re.search(r'run `?co rem |paste (?:it )?in a terminal', page, re.I)
    assert not re.search(r'"Copy (?:the )?(?:\w+ )?(?:command|preview)"', page)


@pytest.mark.parametrize('link', ['http://127.0.0.1:8000/rem?token=fictional', ''])
def test_the_review_snapshot_says_one_sentence_and_links_the_live_reader(link):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S)[0] for name in ['reviewPage', 'liveReaderLine'])
    result = _run_reader_js(functions + r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: children.filter(c => c != null),
        appendChild(child) { this.children.push(child); }});
      const nodes = [], main = {set textContent(_) {}, appendChild: node => nodes.push(node)};
      const document = {getElementById: () => main}, byPath = () => null, emptyState = text => ({text});
      const REM = {live: false, live_link: ''' + json.dumps(link) + r''', reviews: [{id: 'a', status: 'pending', kind: 'link',
        question: 'Is Fern Vale at Harbour Studio?', basis: 'two mails', subjects: []}]};
      reviewPage();
      console.log(JSON.stringify(nodes));
    ''')
    text = json.dumps(result)
    line = next(node for node in result if node.get('class') == 'snapshot-line')
    links = [child for child in line['children'] if isinstance(child, dict) and child.get('tag') == 'a']
    assert [a['href'] for a in links] == ([link] if link else [])
    assert 'review-acts' not in text and 'co rem' not in text


INVESTIGATE = HAND + ['investigateRequest', 'liveReaderLine']


def test_ask_codex_to_look_requests_a_private_project_investigation_in_place():
    """#2909: the private project's own page is the key; the same /rem/task run as 交给 Codex, followed in place."""
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in INVESTIGATE)
    result = _run_reader_js('const AGENT_NAMES = { codex: "Codex", claude: "Claude" }, ACTIVE_TASK = ["queued", "starting", "running"], OPEN_TALKS = new Map();\n'
                            + functions + r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: children.filter(Boolean),
        append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; }});
      const doneKey = entry => entry.key, location = {protocol: 'http:'}, setTimeout = () => {}, requests = [];
      const words = node => node.children[0].children.map(child => child.text).filter(text => text && text !== '·');
      const REM = {live: true, today_queue: []};
      globalThis.fetch = async (url, options) => { requests.push({url, body: JSON.parse(options.body)});
        return {ok: true, status: 200, json: async () => ({id: 'f'.repeat(32), result: 'starting', agent: 'codex'})}; };
      const r = {path: 'projects/private-notes-ab12.md', private_project: true};
      const node = investigateRequest(r), before = words(node);
      node.children[0].children.find(child => child['data-agent'] === 'codex').onclick().then(() => {
        const after = words(node);
        REM.live = false;
        const snapshot = investigateRequest({path: 'projects/private-notes-ab12.md', private_project: true});
        REM.live = true;
        const reopened = words(investigateRequest({path: 'projects/private-notes-ab12.md', private_project: true,
          task: {id: 'f'.repeat(32), agent: 'codex', result: 'completed'}}));
        console.log(JSON.stringify({before, after, requests, snapshot, reopened, kept: r.investigation.task.result}));
      });
    ''')
    assert result['before'] == ['Ask Codex to look', 'Ask Claude to look']
    assert result['requests'] == [{'url': '/rem/task', 'body': {'action': 'run', 'key': 'projects/private-notes-ab12.md', 'agent': 'codex'}}]
    assert result['after'] == ['Codex is working', 'Stop', 'Take back from Codex'] and result['kept'] == 'starting'
    assert result['reopened'] == ['Codex finished', 'See result', 'Take back from Codex']
    # A snapshot cannot start it: one sentence, never a command.
    assert result['snapshot']['class'] == 'snapshot-line' and 'co rem' not in json.dumps(result['snapshot'])


def test_ask_codex_to_look_reads_in_chinese():
    page = TEMPLATE.read_text()
    assert '"Ask {agent} to look": "让 {agent} 查"' in page
    assert '"This is a snapshot: ask Codex to look from the live reader.": ' in page


STALE = ['redraw', 'drawKeepingView', 'markUpdatesWaiting', 'settleRedraw']


def test_a_skipped_redraw_says_updates_are_waiting_and_draws_them_when_the_draft_is_done():
    """A draft holds Today still; a quiet 有更新 says it is behind, and leaving the field or clicking draws it."""
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in STALE)
    result = _run_reader_js('let redrawSkipped = false;\n' + functions + r'''
      let typing = true, unsaved = false, renders = 0, restored = [];
      const typingIn = () => typing, unsavedDraft = () => unsaved, unkeptWords = () => false, render = () => { renders++; };
      const viewState = () => ({open: ['#processing']}), restoreView = state => restored.push(state);
      const setTimeout = fn => fn(), shown = {};
      const body = {children: [], appendChild(node) { node.remove = () => { this.children = this.children.filter(n => n !== node); }; this.children.push(node); }};
      const document = {activeElement: {}, body, getElementById: id => body.children.find(n => n.id === id) || null};
      const el = (tag, attrs = {}) => ({tag, ...attrs});
      redraw(); redraw();
      shown.typing = {renders, marks: body.children.map(n => n.text)};
      typing = false; settleRedraw();
      shown.left = {renders, marks: body.children.length, restored: [...restored]};
      unsaved = true; redraw(); settleRedraw();
      shown.draft = {renders, marks: body.children.length};
      body.children[0].onclick();
      shown.clicked = {renders, marks: body.children.length, restored: restored.length};
      unsaved = false; settleRedraw();
      shown.quiet = renders;
      console.log(JSON.stringify(shown));
    ''')
    assert result['typing'] == {'renders': 0, 'marks': ['Updates waiting']}
    assert result['left'] == {'renders': 1, 'marks': 0, 'restored': [{'open': ['#processing']}]}
    assert result['draft'] == {'renders': 1, 'marks': 1}
    assert result['clicked'] == {'renders': 2, 'marks': 0, 'restored': 2}
    assert result['quiet'] == 2           # nothing was skipped since: no extra draw


def test_updates_waiting_reads_in_chinese_and_is_painted_from_the_sheet():
    page = TEMPLATE.read_text()
    assert '"Updates waiting": "有更新"' in page
    assert re.search(r'\.updates-waiting \{[^}]*var\(--grey\)', page)


def test_a_redraw_carries_typed_words_caret_and_focus_by_stable_key_and_waits_for_a_field_without_one():
    """Clicking 有更新 never loses words: keyed fields come back with caret and focus; an unkeyed one holds the mark."""
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['keptFields', 'restoreFields', 'unkeptWords', 'markUpdatesWaiting', 'drawKeepingView'])
    result = _run_reader_js('let redrawSkipped = true; const editedFields = new Set(), EDITABLE = "textarea";\n' + functions + r"""
      const field = (keep, value) => ({dataset: keep ? {keep} : {}, value, selectionStart: 2, selectionEnd: 4,
        focus() { document.activeElement = this; }, setSelectionRange(a, b) { this.caret = [a, b]; },
        dispatchEvent(event) { this.fired = event.type; }});
      let nodes = [field('slot:d1:1', 'Friday'), field('talk:codex:people/fern.md\nReply', 'Draft it short')];
      nodes.forEach(node => editedFields.add(node));
      const main = {contains: () => true}, body = {children: [], appendChild(node) { node.remove = () => { this.children = []; }; this.children.push(node); }};
      const document = {activeElement: nodes[1], body, querySelectorAll: () => nodes,
        getElementById: id => id === 'main' ? main : body.children.find(n => n.id === id) || null};
      globalThis.Event = class { constructor(type) { this.type = type; } };
      const el = (tag, attrs = {}) => ({tag, ...attrs});
      let renders = 0;
      const viewState = () => ({fields: keptFields()}), restoreView = state => restoreFields(state.fields);
      const render = () => { renders++; nodes = [field('slot:d1:1', ''), field('talk:codex:people/fern.md\nReply', '')]; };
      markUpdatesWaiting();
      body.children[0].onclick();
      const after = nodes.map(node => ({value: node.value, fired: node.fired || null, caret: node.caret || null, kept: editedFields.has(node)}));
      const focused = document.activeElement === nodes[1];
      const loose = field(null, 'Words with no home');
      nodes.push(loose); editedFields.add(loose);
      markUpdatesWaiting();
      body.children[0].onclick();
      console.log(JSON.stringify({after, focused, renders, marks: body.children.length}));
    """)
    assert result['after'] == [{'value': 'Friday', 'fired': 'input', 'caret': None, 'kept': True},
                               {'value': 'Draft it short', 'fired': 'input', 'caret': [2, 4], 'kept': True}]
    # A field with no stable key: the mark stays and nothing more is drawn.
    assert result['focused'] and result['renders'] == 1 and result['marks'] == 1


def _lang_toggle_js(body):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['setInterfaceLanguage', 'renderLangToggle', 'drawKeepingView'])
    return _run_reader_js('let redrawSkipped = false;\n' + functions + r'''
      const stored = [], posted = [], order = [], marks = [], restored = [];
      const REM = {live: true, records: [{readLanguage: 'en'}]}, location = {protocol: 'http:', hash: '#today'};
      globalThis.fetch = (url, options) => { posted.push([url, JSON.parse(options.body)]); };
      const readerStorage = (key, value) => stored.push([key, value]), closeEvidence = () => {};
      const button = {setAttribute(name, value) { this[name] = value; }, getAttribute(name) { return this[name]; }};
      const named = () => [button.textContent, button.lang, button['aria-label'], button.title];
      let sections = [{open: true}, {open: false}, {open: true}], unkept = false, redrawn = 3;
      const document = {getElementById: id => id === 'lang-toggle' ? button : null,
        querySelectorAll: selector => selector === '#main details' ? sections : []};
      const unkeptWords = () => unkept, markUpdatesWaiting = () => marks.push('updates-waiting');
      // What the page held before the click: where it was, the sections open by id, the words in keyed fields.
      const state = {hash: '#today', y: 640, open: ['#processing'], fields: [{key: 'talk:codex:fern', value: 'Draft it short', focused: true, start: 2, end: 4}]};
      const viewState = () => state;
      const render = () => { order.push('render:' + uiLanguage); sections = Array.from({length: redrawn}, () => ({open: false})); };
      const restoreView = given => restored.push({unchanged: given === state, open: given.open, fields: given.fields.length, y: given.y,
        reopened: sections.map(node => node.open), language: uiLanguage});
''' + body)


def test_the_language_button_names_its_target_saves_the_choice_and_redraws_keeping_the_view():
    """One click: the choice is stored and sent like the Settings switch, the button now names the other language,
    and the page is drawn the way a click on 有更新 draws it: sections reopened by position (their summaries change
    language), then restoreView with the state untouched, so id-keyed sections, keyed words and scroll come back."""
    result = _lang_toggle_js(r'''
      renderLangToggle();
      const before = named();
      let prevented = false;
      button.onmousedown({preventDefault() { prevented = true; }});
      button.onclick();
      const after = named(), first = restored.splice(0);
      redrawn = 2;                       // the other language draws a different number of sections
      button.onclick();
      console.log(JSON.stringify({before, after, prevented, uiLanguage, stored, posted, order, first, second: restored,
        readLanguage: REM.records[0].readLanguage ?? null, redrawSkipped, marks}));
    ''')
    assert result['before'] == ['中', 'zh', '切换到中文', '切换到中文']
    assert result['after'] == ['EN', 'en', 'Switch to English', 'Switch to English']
    assert result['prevented'] is True                     # the caret stays in the field being typed in
    assert result['stored'] == [['co-rem-ui-language', 'zh'], ['co-rem-ui-language', 'en']]
    assert result['posted'] == [['/rem/language', {'language': 'zh'}], ['/rem/language', {'language': 'en'}]]
    assert result['order'] == ['render:zh', 'render:en'] and result['uiLanguage'] == 'en'
    assert result['readLanguage'] is None
    assert result['first'] == [{'unchanged': True, 'open': ['#processing'], 'fields': 1, 'y': 640,
                                'reopened': [True, False, True], 'language': 'zh'}]
    # A different count: nothing is reopened by position, and the sections known by id still come back.
    assert result['second'] == [{'unchanged': True, 'open': ['#processing'], 'fields': 1, 'y': 640,
                                 'reopened': [False, False], 'language': 'en'}]
    assert result['redrawSkipped'] is False and result['marks'] == []


def test_the_language_button_never_wipes_words_a_redraw_cannot_put_back():
    """Words in a field with no stable key: the click still saves the choice and the button flips, so it is seen
    to have worked; the page is not drawn, 有更新 shows, and the waiting redraw brings the language."""
    result = _lang_toggle_js(r'''
      renderLangToggle();
      unkept = true;
      button.onclick();
      console.log(JSON.stringify({label: named()[0], uiLanguage, stored, order, restored, redrawSkipped, marks}));
    ''')
    assert result == {'label': 'EN', 'uiLanguage': 'zh', 'stored': [['co-rem-ui-language', 'zh']], 'order': [], 'restored': [],
                      'redrawSkipped': True, 'marks': ['updates-waiting']}


def test_the_language_button_is_named_before_the_first_render():
    """The first render waits for the saved choices; the button in the header is never an empty, unnamed control."""
    page = TEMPLATE.read_text()
    first_render = page.index('Promise.all([readerStorage("co-rem-ui-language")')
    assert re.search(r'^renderLangToggle\(\);$', page[:first_render], re.M)
    assert page.index('id="lang-toggle"') < page.index('function renderLangToggle()')


def test_committed_rem_text_says_owner_and_never_a_real_name():
    """The reader, its tests and its guide are public: the person it was built for is "the owner" there."""
    name = 'Aa' + 'ron'
    root = TEMPLATE.parents[2]
    files = [TEMPLATE, root / 'docs' / 'cli' / 'rem.md', *sorted((root / 'tests' / 'unit').glob('test_rem_*.py')),
             *sorted((root / 'tests' / 'e2e' / 'cli').glob('test_rem_*.py'))]
    hits = [f'{path.relative_to(root)}:{number}' for path in files
            for number, line in enumerate(path.read_text().splitlines(), 1) if name in line]
    assert hits == []


def _youify(lines):
    """The reader's own youify over `lines`, as the owner reads them."""
    source = TEMPLATE.read_text()
    parts = [re.search(r"^const " + name + r" = .*?;$", source, re.M).group(0)
             for name in ["YOU_VERBS", "NOT_VERBS", "CLAUSE_START", "ALSO_VERBS"]]
    parts += [re.search(r"function " + name + r"\(.*?\n\}", source, re.S).group(0) for name in ["plural", "youify"]]
    return _run_reader_js("\n".join(parts) + f"\nconsole.log(JSON.stringify({json.dumps(lines)}.map(youify)));")


def test_a_question_to_the_owner_agrees_when_the_verb_comes_first():
    # #2908: "Has the user collected …?" on the page read "Has you collected …?".
    cases = {
        "Has the user collected the replacement card since 2026-10-01? [3]": "Have you collected the replacement card since 2026-10-01? [3]",
        "Does the user have the signed copy?": "Do you have the signed copy?",
        "Is the user still waiting on the quote?": "Are you still waiting on the quote?",
        "Was the user told about the move?": "Were you told about the move?",
        "Hasn't the user replied?": "Haven't you replied?",
        "When does the user expect the deposit?": "When do you expect the deposit?",
        "Did Mara accept, and has the user replied?": "Did Mara accept, and have you replied?",
    }
    assert _youify(list(cases)) == list(cases.values())


def test_a_verb_before_the_user_as_object_or_possessive_is_left_alone():
    cases = {
        "The signer is the user.": "The signer is you.",
        "Mara has the user's deck.": "Mara has your deck.",
        "Did the user send it?": "Did you send it?",
        "Has Mara replied to the user?": "Has Mara replied to you?",
    }
    assert _youify(list(cases)) == list(cases.values())


def test_the_night_chart_window_never_ends_before_it_starts():
    """Review of #2929: run times later than the snapshot's as_of (a clock ahead of it) made start > end, so every
    x position divided by a negative span. The window keeps at least an hour, and a phone keeps thirty hours."""
    page = TEMPLATE.read_text()
    function = re.search(r'function nightWindow\(.*?\n\}', page, re.S).group(0)
    result = _run_reader_js(function + r'''
      const DAY_MS = 86400000, REM = {as_of: '2026-11-10T12:00:00Z'}, end = Date.parse(REM.as_of);
      const ahead = nightWindow([end + 2 * 3600000, end + 5 * 3600000], false);
      const phone = nightWindow([end - 4 * DAY_MS], true), desk = nightWindow([end - 4 * DAY_MS], false);
      console.log(JSON.stringify({ahead: [ahead.end - ahead.start], phone: (phone.end - phone.start) / 3600000, desk: (desk.end - desk.start) / DAY_MS}));
    ''')
    assert result['ahead'][0] >= 3600000
    assert result['phone'] == 30 and result['desk'] == 3
