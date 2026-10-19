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
        'for (const [i, line] of ["Now: waiting on review", "**Now:** waiting on review"].entries()) {',
        'r = {path: `projects/pilot-${i}.md`, title: "Pilot", category: "projects",',
        'text: "# Pilot\\n\\n## Insight\\n- " + line};',
        week, '}', 'console.log(JSON.stringify(rows));',
    ])
    rows = _run_reader_js(script)
    for week_list in rows[1::2]:
        summary = week_list["children"][0]["children"][2]["children"][2]["text"]
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


def test_interface_language_uses_owner_order_and_leaves_record_prose_alone(tmp_path, monkeypatch):
    import sys
    from datetime import datetime, timezone
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build

    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    monkeypatch.setattr('connectonion.rem.languages.owner_languages', lambda root: {'languages': ['zh', 'en']})
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
        't("{n} runs", {n: 10}), t("{n} written of {m}", {n: 3, m: 6})];',
        'const en = labels(); uiLanguage = "zh"; const zh = labels();',
        'console.log(JSON.stringify({en, zh})); })();',
    ]))
    assert result['en'] == ['10 days', '1 day', 'today', 'source 99', 'overdue · 19 Oct', 'due 21 Oct',
                            'Read 240 items', 'Rewrote 7 pages', '10 runs', '3 written of 6']
    assert result['zh'] == ['10 天', '1 天', '今天', '来源 99', '已逾期 · 10月19日', '到期 10月21日',
                            '阅读了 240 项', '改写了 7 页', '10 次运行', '6 人中已撰写 3 人']


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
