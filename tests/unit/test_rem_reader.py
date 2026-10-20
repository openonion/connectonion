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
    script = privacy + "\n" + script
    # stdin, not -e: Linux caps one argument at 128 KB and the template is larger.
    script = "const UI = {en: {}}; let uiLanguage = 'en';\n" + re.search(r"function t\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + re.search(r"function uiLocale\(.*?\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + script
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_this_week_project_rows_strip_the_now_label():
    page = TEMPLATE.read_text(encoding="utf-8")
    parsing = page[page.index("const UNKNOWN_LINE ="):page.index("function mappedContact(")]
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["splitTrailers", "plainLine"])
    week = page[page.index("  // This week: what"):page.index('  const processing = el("details"')]
    script = "\n".join([
        parsing, functions,
        'const youify = text => text;',
        'const el = (tag, attrs, children = []) => ({tag, ...attrs, children});',
        'const shortDate = day => day, moon = () => null, href = r => r.path;',
        'const singular = () => "project", sectionHead = text => ({text});',
        'let r; const weekChanges = () => [{r, day: "2026-10-16"}];',
        'const rows = [], main = {appendChild: node => rows.push(node)};',
        'const updatedMarker = () => null;',
        'for (const [i, line] of ["Now: waiting on review", "**Now:** waiting on review"].entries()) {',
        'r = {path: `projects/pilot-${i}.md`, title: "Pilot", category: "projects",',
        'text: "# Pilot\\n\\n## Insight\\n- " + line};',
        week, '}', 'console.log(JSON.stringify(rows));',
    ])
    rows = _run_reader_js(script)
    for week_list in rows[1::2]:
        summary = next(child["text"] for child in week_list["children"][0]["children"][2]["children"]
                       if child and child.get("class") == "s")
        assert summary == "waiting on review"


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
        "orgs/resdemou-com-1.md": "# resdemou.com\n\nResdemou's legal identity is recorded.\n",
        "orgs/connectonion-com-2.md": "# connectonion.com\n\nAn agent framework.\n",
        "orgs/morganpost-net-3.md": "# morganpost.net\n\nNo name stated.\n\n## Sources\n- MorganPost archived mail\n",
        "orgs/blackdiamondz-com-au-4.md": "# blackdiamondz.com.au\n\nBlack Diamondz manages properties.\n",
        "orgs/named.md": "# An existing title\n\nConnectOnion operates here.\n",
        "projects/domain.md": "# resdemou.com\n\nResdemou operates here.\n",
        "people/alice.md": "# Alice\n\n## Facts\n- Company: [ConnectOnion](../orgs/connectonion-com-2.md) [3]\n",
        "people/bob.md": "# Bob\n\n- Company: [An older name](../orgs/resdemou-com-1.md) [1]\n",
    }
    for path, text in pages.items():
        notebook.write(path, text)
    before = {p.relative_to(tmp_path).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in tmp_path.rglob("*") if p.is_file()}

    records = {r["path"]: r for r in snapshot(tmp_path)["records"]}
    for path, name, domain in [("orgs/resdemou-com-1.md", "Resdemou", "resdemou.com"),
                               ("orgs/connectonion-com-2.md", "ConnectOnion", "connectonion.com"),
                               ("orgs/blackdiamondz-com-au-4.md", "Black Diamondz", "blackdiamondz.com.au")]:
        assert records[path]["title"] == name
        assert records[path]["domain"] == domain
        assert records[path]["text"] == pages[path]
    assert records["orgs/morganpost-net-3.md"]["title"] == "morganpost.net"
    assert "domain" not in records["orgs/morganpost-net-3.md"]
    assert records["orgs/named.md"]["title"] == "An existing title"
    assert "domain" not in records["orgs/named.md"]
    assert records["projects/domain.md"]["title"] == "resdemou.com"
    assert "domain" not in records["projects/domain.md"]
    assert before == {p.relative_to(tmp_path).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("domain, text, expected", [
    ("blackdiamondz.com.au", "Black Diamondz manages properties.", "Black Diamondz"),
    ("connectonion.com", "Connectonion began. ConnectOnion grew. ConnectOnion ships.", "ConnectOnion"),
    ("resdemou.com", "Resdemou’s legal identity.", "Resdemou"),
    ("onetwothreefourfive.com", "One Two Three Four Five operates here.", ""),
    ("blackdiamondz.com.au", "Black and Diamondz are separate words.", ""),
    ("resdemou.com", "resdemou is lowercase.", ""),
    ("resdemou.com", "No name.\n\n## Sources\nResdemou is only a source.\n\n## History\nNothing new.", ""),
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
def test_copy_path_and_reopen_command_keep_the_notebook_root(tmp_path, protocol):
    root = tmp_path / "owner's notebook"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice\n")
    page = render(root)
    data = json.loads(re.search(r"const REM = (.*);", page).group(1))
    record = next(r for r in data["records"] if r["path"] == "people/alice.md")
    # Execute the generated handlers with only the clipboard and footer DOM stubbed.
    command = re.search(r"function remCommand\(args\).*", page).group(0)
    copy = re.search(r"pathBtn.onclick = .*", page).group(0)
    footer = next(line for line in page.splitlines() if "settings.appendChild" in line and "re-renders" in line)
    script = "\n".join([
        "const REM = " + json.dumps(data) + "; const r = " + json.dumps(record) + ";",
        "const location = {protocol: " + json.dumps(protocol) + "};",
        "const result = {}, pathBtn = {};",
        "const copyToClipboard = path => result.path = path;",
        "const el = (tag, attrs) => attrs.text;",
        "const settings = {appendChild: text => result.footer = text};",
        command, copy, footer, "pathBtn.onclick(); console.log(JSON.stringify(result));",
    ])
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed; it runs the reader's JavaScript")
    privacy = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0)
                        for name in ["privatePassages", "unlabelled", "hasPrivacy"])
    script = privacy + "\n" + script
    # stdin, not -e: Linux caps one argument at 128 KB and the template is larger.
    script = "const UI = {en: {}}; let uiLanguage = 'en';\n" + re.search(r"function t\(.*?\n\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + re.search(r"function uiLocale\(.*?\}", TEMPLATE.read_text(), re.S).group(0) + "\n" + script
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    quoted_root = "'" + str(root).replace("'", "'\\''") + "'"
    assert json.loads(result.stdout) == {
        "path": str(root / record["path"]),
        "footer": "Reload for latest" if protocol == "about:" else f"co rem --root {quoted_root} open re-renders",
    }


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


def test_empty_between_you_has_no_section_but_real_threads_remain():
    page = TEMPLATE.read_text(encoding="utf-8")
    function = re.search(r"function betweenYou\(.*?\n\}", page, re.S).group(0)
    result = _run_reader_js("\n".join([
        function, 'const threads = r => r;',
        'const el = (tag, attrs, children) => ({tag, ...attrs, children});',
        'const ledgerColumn = (r, items, dir) => ({dir, count: items.length});',
        'console.log(JSON.stringify([betweenYou({items: [], calm: "Nothing open as of 2026-10-20"}),',
        'betweenYou({items: [{dir: "mine"}], calm: ""})]));',
    ]))
    assert result[0] is None
    assert result[1]["children"][1]["children"] == [{"dir": "mine", "count": 1}, {"dir": "theirs", "count": 0}]


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
                          for name in ["blockerTag", "threadAge", "dueLabel", "threadDate", "age", "daysSince"])
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
    assert [row["age"] for row in result] == ["3 days"] * 5 + ["due 23 Oct", "overdue · 10 Sep"]
    assert [bool(row["tag"]) for row in result] == [False, True, True, True, True, False, False]


@pytest.mark.parametrize('languages', [['zh', 'en'], ['en', 'zh']])
def test_interface_language_prefers_supported_non_english_and_leaves_record_prose_alone(tmp_path, monkeypatch, languages):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build

    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    monkeypatch.setattr('connectonion.rem.languages.owner_languages', lambda root: {'languages': languages})
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


def test_display_commands_use_short_form_only_for_the_default_notebook(tmp_path, monkeypatch):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    from connectonion.rem.reader import snapshot
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build

    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    root = build(tmp_path / '.co' / 'rem', datetime(2026, 10, 1, tzinfo=timezone.utc))
    data = snapshot(root)
    assert data['default_root'] is True
    function = re.search(r'function remCommand\(args\).*', TEMPLATE.read_text()).group(0)
    result = _run_reader_js('\n'.join([
        'const REM = ' + json.dumps(data) + ';', function,
        'const commands = [remCommand("sources"), remCommand("import sessions")];',
        'REM.default_root = false; REM.root = "/tmp/avery\'s notebook";',
        'commands.push(remCommand("import sessions")); console.log(JSON.stringify(commands));',
    ]))
    assert result[:2] == ['co rem sources', 'co rem import sessions']
    assert result[2] == "co rem --root '/tmp/avery'\\''s notebook' import sessions"


def test_dynamic_reader_chrome_translates_without_changing_english():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['age', 'dueLabel', 'threadDate', 'citationDate', 'chipLabel'])
    result = _run_reader_js('\n'.join([
        '(() => { let uiLanguage = "en";', interface, functions,
        'const REM = {as_of: "2026-10-20"}, calendarDay = day => day;',
        'const daysSince = day => Number(day), citationSource = () => "", sourceId = () => "";',
        'const sourceChannel = () => "";',
        'const labels = () => [age("10"), age("1"), age("0"), citationDate({}, "99"),',
        'dueLabel({due: "2026-10-19"}), dueLabel({due: "2026-10-21"}),',
        't("Read {n} items", {n: 240}), t("Rewrote {n} pages", {n: 7}),',
        't("{n} runs", {n: 10}), t("{n} written of {m}", {n: 3, m: 6, unit: " 人"})];',
        'const en = labels(); uiLanguage = "zh"; const zh = labels();',
        'console.log(JSON.stringify({en, zh})); })();',
    ]))
    assert result['en'] == ['10 days', '1 day', 'today', 'source 99', 'overdue · 19 Oct', 'due 21 Oct',
                            'Read 240 items', 'Rewrote 7 pages', '10 runs', '3 written of 6']
    assert result['zh'] == ['10 天', '1 天', '今天', '来源 99', '已逾期 · 10月19日', '到期 10月21日',
                            '阅读了 240 项', '改写了 7 页', '10 次运行', '已撰写 3 / 6 人']


@pytest.mark.parametrize('source', ['unbroken' * 80 + ':fixture', 'gmail:fixture', ''],
                         ids=['long-source', 'undated-mail', 'missing'])
def test_undated_quiet_citation_uses_number_instead_of_source_label(source):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['citationDay', 'citationDate'])
    result = _run_reader_js('\n'.join([
        functions, 'const REM = {source_context: {}};',
        'const citationSource = () => ' + json.dumps(source) + ', sourceId = text => text;',
        'const chipLabel = () => ' + json.dumps(source) + ';',
        'const labels = [citationDate({}, "99")];',
        'REM.source_context[' + json.dumps(source) + '] = {time: "2026-10-20"};',
        'labels.push(citationDate({}, "99")); console.log(JSON.stringify(labels));',
    ]))
    assert result == ['source 99', '20 Oct']


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
                          for name in ['changedValue', 'plainLine'])
    script = '\n'.join([
        '(() => {', functions, 'const youify = value => value;',
        'const r = {path: "people/avery-lin.md"};',
        'let items; const parseFacts = () => new Map([["First contact", items]]);',
        'let memoryPass = {claims: [{record: r.path, field: "first contact",',
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
                          for name in ['lastPass', 'runTime', 'sameClaim', 'updatedMarker'])
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
    assert result['zh'] == ['最近动态', '文件更新于', '最近映射的会话', '最近名称匹配',
                            '条存档消息', '昨夜', '昨夜整理时更新']


def test_audited_chrome_uses_category_nouns_and_keeps_english_labels():
    page = TEMPLATE.read_text()
    interface = page[page.index('const UI ='):page.index('function setInterfaceLanguage(')]
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['categoryCount', 'usageCaption', 'refusalReason', 'sourceLabel', 'threadDate'])
    result = _run_reader_js('\n'.join([
        '(() => { let uiLanguage = "zh";', interface, functions,
        'const REM = {source_context: {"claude-code:12345678-1234-1234-1234-123456789abc:1": {time: "2026-09-03T12:00:00Z"}}};',
        'const fmtDate = () => "10月10日";',
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
    assert result['zh'] == [f'已撰写 3 / 6 {unit}' for unit in units]
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
    ('codex:12345678-1234-1234-1234-123456789abc:2', True, 'Codex session · 3 Sep'),
    ('claude-code:12345678-1234-1234-1234-123456789abc:2', True, 'Claude Code session · 3 Sep'),
    ('codex:12345678-1234-1234-1234-123456789abc:2', False, 'codex:12345678…:2'),
    ('file:' + 'b' * 32, True, 'file:bbbbbbbb…'),
    ('gmail:' + 'c' * 31, False, 'gmail:' + 'c' * 31),
])
def test_source_labels_only_shorten_opaque_segments(source, dated, expected):
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['sourceLabel', 'threadDate'])
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
    assert result == {'grouped': [['people/mara.md', 'people/tomas.md', 'people/ines.md']],
                      'bridge': [2, 1], 'sharedThread': True,
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



def test_reader_history_accepts_chinese_colon_and_preserves_citations():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['listItems', 'historyItems'])
    result = _run_reader_js(functions + r'''
      console.log(JSON.stringify(historyItems('- 2026-10-15：Arthur Chen 发来合同 [3].\n- 2026-10-14: 已确认 [2].')));
    ''')
    assert result == [{'day': '2026-10-15', 'end': '', 'text': 'Arthur Chen 发来合同 [3].'},
                      {'day': '2026-10-14', 'end': '', 'text': '已确认 [2].'}]


def test_reader_merged_threads_exclude_empty_prose_and_the_rows_own_person():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['threadEntries', 'threadGroups', 'obligationEvidence', 'obligationWords',
                                       'sameObligation', 'plainLine', 'threadWords', 'rawSection'])
    result = _run_reader_js(functions + r'''
      const REM = {owner: 'people/aaron.md'}, COMMENT = /<!--[\s\S]*?-->/g, DAY_MS = 86400000;
      const youify = text => text;
      const records = [
        {path: REM.owner, title: 'Aaron Xie', category: 'people'},
        {path: 'people/ody.md', title: 'Ody Zhou', category: 'people'},
        {path: 'people/ody-alias.md', title: 'Ody Zhou', category: 'people'},
        {path: 'people/jerryl.md', title: 'Jerryl Seow', category: 'people'}
      ];
      const inCategory = () => records, listedRecords = () => records;
      const threads = r => ({items: r.items});
      for (const r of records) {
        r.text = '# ' + r.title + '\n\n## Sources\n- [1] gmail:shared';
        r.items = [{text: 'You owe Ody Zhou a signed agreement [1].', dir: 'mine', since: '2026-10-15'}];
      }
      records[0].items = [{text: ' ', originalText: 'You owe Ody Zhou a signed agreement [1].', dir: 'mine', since: '2026-10-16'},
        {text: 'You owe Jerryl Seow [1]', dir: 'mine', since: '2026-10-15'},
        {text: '[1].', dir: 'mine', since: '2026-10-16'}];
      records[1].items.push({...records[1].items[0]});
      const merged = threadEntries();
      console.log(JSON.stringify(merged.map(({r, t, also}) => ({person: r.title, text: t.text,
        also: also.map(person => person.title)}))));
    ''')
    assert result == [{'person': 'Ody Zhou', 'text': 'You owe Ody Zhou a signed agreement [1].',
                       'also': ['Jerryl Seow']}]


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


@pytest.mark.parametrize('text,expected', [
    ('Mara gives examples, e.g.support letters. Send the draft: include details, please. Third sentence.',
     'Mara gives examples, e.g.support letters. Send the draft: include details, please. Third sentence.'),
    ('Version 3.5 uses example.test. Next sentence. Third sentence.',
     'Version 3.5 uses example.test. Next sentence. Third sentence.'),
    ('前文。需要草稿：保留说明，及细节！第三句。', '前文。 需要草稿：保留说明，及细节！'),
    ('公开介绍。秘密信息[personal]。公开结尾。', '公开介绍。 秘密信息[personal]。公开结尾。'),
])
def test_reader_person_lead_keeps_english_punctuation_and_private_passages(text, expected):
    function = re.search(r'function personLead\(.*?\n\}', TEMPLATE.read_text(), re.S).group(0)
    result = _run_reader_js(function + r'''
      const section = () => null, listItems = () => [], known = () => ({intro: ''' + json.dumps(text) + r'''});
      const el = (tag, attrs) => attrs.html, privateFallback = node => node, inline = text => text;
      console.log(JSON.stringify(personLead({path: 'people/mara.md'})));
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
                          for name in ['sessionText', 'sessionExcerpt'])
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
