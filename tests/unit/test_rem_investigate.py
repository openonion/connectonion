"""Both runners are co ai; the runner setting only picks which harness answers."""

import json
import types
from pathlib import Path

import pytest

from connectonion.rem import investigate as inv
from connectonion.rem.config import prepare, read_config, set_config


class Quiet:
    """One mail from Vern: an investigation with nothing about its subject stops before the model (#1974)."""
    def my_addresses(self): return {"me@x.y"}
    def list_between(self, s, e, n):
        return [{"id": "q1", "from": "vern.chan@unsw.edu.au", "to": ["me@x.y"], "subject": "Hello", "date": s}]
    def get_email_body(self, i): return "Hi, Vern here."


@pytest.fixture(autouse=True)
def skill_found(monkeypatch):
    """The real check spawns the interpreter; its own tests are in test_rem_runner."""
    monkeypatch.setattr("connectonion.rem.runner.check_skill", lambda root, stage: None)


def test_transient_connection_error_retries_body_fetch(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda seconds: None)
    attempts = []

    def fetch():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError('temporary outage')
        return 'body'

    assert inv._patient(fetch) == 'body'
    assert len(attempts) == 3


def test_gather_fetches_mail_bodies_concurrently_and_keeps_source_order():
    import threading
    from datetime import datetime, timedelta, timezone

    together = threading.Barrier(4, timeout=5)

    class Mail:
        def my_addresses(self): return {"me@example.org"}
        def list_with(self, address, start, finish):
            return [{"id": str(n), "date": (datetime.now(timezone.utc) - timedelta(days=5 - n)).isoformat(),
                     "from": "friend@example.org", "to": ["me@example.org"], "subject": "Hi"}
                    for n in range(1, 5)]
        def get_email_body(self, message_id):
            together.wait()
            return f"Body {message_id}"

    items, coverage = inv.gather("Friend", ["friend@example.org"], days=30,
                                 clients={"gmail": Mail()}, subscriptions={})
    assert [item["text"] for item in items if item["source"].startswith("gmail:")] == [
        "Body 1", "Body 2", "Body 3", "Body 4"]
    assert any("4 bodies read" in line for line in coverage)


def test_quick_evidence_keeps_complete_gathered_sources():
    items = [{'source': 'gmail:old', 'timestamp': '2026-09-20', 'text': 'a' * 9000},
             *[{'source': f'codex:{i}', 'timestamp': f'2026-09-{21 + i:02d}',
                'text': 'b' * 9000} for i in range(4)],
             {'source': 'outlook:new', 'timestamp': '2026-09-26', 'text': 'c' * 9000}]
    selected = inv.quick_evidence(items)
    assert len(selected) == len(items)
    assert {item['source'].split(':')[0] for item in selected} == {'gmail', 'codex', 'outlook'}
    assert selected == items and all(len(item['text']) == 9000 for item in selected)


def test_owner_work_packet_exposes_dated_decision_sources_without_claiming_completion():
    items = [
        {'source': 'codex:old', 'role': 'user', 'project': '/work/rem', 'timestamp': '2026-09-28',
         'text': 'Use a static owner page for this first pass.'},
        {'source': 'codex:choice', 'role': 'user', 'project': '/work/rem', 'timestamp': '2026-10-01',
         'text': 'Instead, switch to a cited model investigation after the quick pass.'},
        {'source': 'codex:new', 'role': 'user', 'project': '/work/rem', 'timestamp': '2026-10-02',
         'text': 'Check the owner page with real source material before releasing.'},
        {'source': 'outlook:invite', 'role': 'user', 'project': '', 'timestamp': '2026-10-02',
         'text': 'Maybe attend a talk in November.'},
    ]
    packet = inv.owner_work_evidence(items)
    assert packet.index('codex:old') < packet.index('codex:choice') < packet.index('codex:new')
    assert 'outlook:invite' not in packet
    assert 'not a digest or evidence of completion' in packet


def test_owner_work_packet_follows_a_repeated_topic_inside_a_mixed_workspace():
    items = [
        {'source': 'codex:unrelated', 'role': 'user', 'project': '/work', 'timestamp': '2026-09-27',
         'text': 'Choose the event venue and send the invitation.'},
        {'source': 'codex:old', 'role': 'user', 'project': '/work', 'timestamp': '2026-09-28',
         'text': 'REM先不要让模型写首次页面，保留静态模板。'},
        {'source': 'codex:new', 'role': 'user', 'project': '/work', 'timestamp': '2026-10-01',
         'text': '现在REM应该用模型写有来源的首次页面。'},
        {'source': 'codex:latest', 'role': 'user', 'project': '/work', 'timestamp': '2026-10-02',
         'text': 'Check the REM init page against the real notebook.'},
    ]
    packet = inv.owner_work_evidence(items)
    assert 'topic REM' in packet
    assert all(source in packet for source in ('codex:old', 'codex:new', 'codex:latest'))
    assert 'codex:unrelated' not in packet


def test_owner_work_packet_follows_init_across_a_renamed_memory_product():
    items = [
        {'source': 'claude-code:old', 'role': 'user', 'project': '/work/connectonion',
         'timestamp': '2026-09-27', 'text': 'Maybe co wiki init should start from a static page.'},
        {'source': 'codex:reversal', 'role': 'user', 'project': '/work',
         'timestamp': '2026-10-01', 'text': '不对，init 不启动模型是错的，应该在 init 用模型调查。'},
        {'source': 'codex:latest', 'role': 'user', 'project': '/work',
         'timestamp': '2026-10-02', 'text': 'Check the REM init page against real data.'},
        {'source': 'claude-code:unrelated', 'role': 'user', 'project': '/work/connectonion',
         'timestamp': '2026-10-01', 'text': 'Choose a venue for the student event.'},
    ]
    packet = inv.owner_work_evidence(items)
    assert 'topic init' in packet
    assert all(source in packet for source in ('claude-code:old', 'codex:reversal', 'codex:latest'))
    assert 'claude-code:unrelated' not in packet


def test_full_owner_pass_compares_sources_already_cited_by_the_quick_page(tmp_path, monkeypatch):
    from datetime import date

    root = _notebook(tmp_path, 'codex')
    book = inv.Notebook(root)
    page = book.read('people/vern.md').replace('· not investigated yet',
                                               f'· investigated {date.today().isoformat()} (codex)')
    page = page.replace('## Sources\n- (none yet)', '## Sources\n- [1] codex:old')
    book.write('people/vern.md', page)
    messages = [
        {'source': 'codex:old', 'role': 'user', 'project': '/work', 'timestamp': '2026-09-29',
         'text': 'Maybe init should keep the static page for now.'},
        {'source': 'codex:new', 'role': 'user', 'project': '/work', 'timestamp': '2026-10-02',
         'text': 'No, init should investigate with a model before the first page.'},
    ]
    monkeypatch.setattr(inv, 'gather', lambda *args, **kwargs: (messages, ['codex: 2 messages']))
    seen = []
    inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], days=5,
                    clients={}, subscriptions={}, sent_only=True,
                    runner=lambda notebook, items, config, stage: seen.extend(items) or {'changed': []})
    assert not any(item.get('source') == 'codex:old' for item in seen)
    packet = next(item for item in seen if item['role'] == 'owner-work-evidence')
    assert packet['sources'] == ['codex:old', 'codex:new']
    assert 'Maybe init' in packet['text'] and 'No, init' in packet['text']


def test_quick_owner_run_uses_one_turn_and_reports_partial_coverage(tmp_path, monkeypatch):
    root = _notebook(tmp_path, 'codex')
    rows = [{'source': f'gmail:{i}', 'timestamp': f'2026-09-{(i % 25) + 1:02d}',
             'text': 'A' * 9000} for i in range(30)]
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: (rows, ['gmail: 30 messages found']))
    received = []

    def runner(notebook, items, config, stage):
        received.extend(items)
        return {'changed': [], 'usage': None}

    result = inv.investigate(root, 'people/vern.md', 'Vern', ['vern'], days=5,
                             clients={}, subscriptions={}, runner=runner, quick=True,
                             extractor=lambda *a: pytest.fail('quick pass must fit one model turn'))
    assert result['quick'] is True and result['items_available'] == 30
    assert result['items'] == 1  # all 30 originals are in the evidence index
    assert any('Quick first pass' in text for text in result['coverage'])
    assert len(received) == 4  # page, coverage, quick-scope marker, evidence index
    assert received[2]['role'] == 'quick-first-pass'
    assert len(received[3]['sources']) == 30


def test_quick_owner_fetches_all_matching_mail_bodies():
    class Mailbox:
        def __init__(self):
            self.fetched = []

        def my_addresses(self):
            return ['me@example.org']

        def list_between(self, start, end, limit):
            return [{'id': str(i), 'from': 'me@example.org', 'to': 'other@example.org',
                     'date': f'2026-09-25T{i:02d}:00:00Z', 'subject': 'Subject'}
                    for i in range(20)]

        def get_email_body(self, email_id):
            self.fetched.append(email_id)
            return 'Body'

    box = Mailbox()
    items, coverage = inv.gather('Me', ['me@example.org'], days=5,
                                 clients={'outlook': box}, subscriptions={},
                                 sent_only=True, quick=True)
    assert len(items) == 20 and box.fetched == [str(i) for i in range(20)]
    assert any('20 matched, 20 bodies read' in line for line in coverage)


@pytest.fixture
def co_ai(monkeypatch):
    """A `co` that answers at once and remembers how it was called."""
    calls = []

    def fake_run(argv, cwd, capture_output, text, timeout, env=None):
        calls.append(argv)
        import re
        from pathlib import Path
        path = Path(re.search(r'NEW file (.+?candidate.md)', argv[-1])[1])
        page = next(Path(cwd).glob('investigate-*/notebook/people/vern.md')).read_text()
        # The least a finished page is (#2008): one cited fact, every other section a bare Unknown.
        path.write_text(page.replace("## Who they are\n- Unknown — not investigated yet",
                                     "## Who they are\n- Vern works at UNSW. [W1]", 1)
                        .replace("## Sources\n- (none yet)",
                                 "## Sources\n- [W1] https://www.unsw.edu.au/staff/vern-chan, observed 2026-09-23.", 1)
                        .replace("- Unknown — not investigated yet", "- Unknown"))
        return types.SimpleNamespace(stdout=json.dumps({"outcome": "natural", "result": "ok", "usage": None}),
                                     stderr="", returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("connectonion.rem.runner.co_command", lambda: ["/usr/local/bin/co"])
    return calls


def _notebook(tmp_path, runner):
    root = tmp_path / "rem"
    prepare(root)
    set_config(root, ["runner", runner])
    inv.Notebook(root).stub_person("people/vern.md", "Vern Chan", ["vern"], email="vern.chan@unsw.edu.au")
    return root


def test_runner_codex_is_co_ai_delegating_with_investigation_tools(tmp_path, co_ai):
    root = _notebook(tmp_path, "codex")
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    argv = co_ai[0]
    assert argv[1:3] == ["ai", "--json"]
    assert argv[3:9] == ["--harness", "codex", "--sandbox", "danger-full-access",
                         "--model", read_config(root)["model"]]
    # The Skill is told the page's real path, extension included: an earlier
    # version cut the record at its first "." and pointed it at people/vern.
    assert argv[-1].startswith("/rem-investigate ") and "/notebook/people/vern.md" in argv[-1]


def test_investigation_reports_privacy_safe_stages(tmp_path):
    root = _notebook(tmp_path, "codex")
    stages = []

    def fake_runner(notebook, items, config, stage):
        assert stage == "investigate"
        return {"changed": [], "usage": None}

    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=5,
                    clients={"outlook": Quiet()}, subscriptions={}, runner=fake_runner,
                    stage_progress=lambda stage, *counts: stages.append((stage, counts)))
    assert [stage for stage, _ in stages] == [
        "gathering sources", "gathering outlook mail", "preparing evidence", "writing investigation",
        "recording result"]


def test_project_inventory_is_bounded_and_excludes_hidden_or_sensitive_files(tmp_path):
    project = tmp_path / 'project'
    (project / 'docs').mkdir(parents=True)
    (project / '.git').mkdir()
    for name in ('README.md', 'password.txt', '.env', 'a.py'):
        (project / name).write_text('fixture')
    (project / 'docs' / 'rem-guide.md').write_text('fixture')
    (project / '.git' / 'config').write_text('fixture')
    page = f'# Project\n## Paths\n- {project}\n- Sessions: 1\n## Sources\n'
    leads = inv.project_file_inventory(page, max_files=2)
    assert len(leads) == 2
    assert leads[0].endswith('/README.md')
    assert any(path.endswith('/rem-guide.md') for path in leads)
    assert not any('password' in path or '/.git/' in path or '/.env' in path for path in leads)
    cited = page.replace(f'- {project}\n', f'- {project} [1][2]\n')
    assert inv.project_paths(cited) == [str(project)]
    assert inv.project_file_inventory(cited, max_files=2) == leads


# The whole command line before the prompt, pinned per executor for both
# attended and scheduled investigation runs.
PINNED = {
    "codex": ["ai", "--json", "--harness", "codex", "--sandbox", "danger-full-access",
              "--model", "gpt-5.6-luna", "--timeout", "1200"],
    "claude-code": ["ai", "--json", "--harness", "claude-code", "--permission-mode", "bypassPermissions",
                    "--model", "sonnet", "--timeout", "1200"],
}


def _pinned_notebook(tmp_path, runner):
    root = _notebook(tmp_path, runner)
    set_config(root, ["model", "gpt-5.6-luna" if runner == "codex" else "sonnet"])
    set_config(root, ["limits.timeout_seconds", "1200"])
    return root


@pytest.mark.parametrize("runner", sorted(PINNED))
def test_an_investigation_the_user_starts_has_tools_authorized(tmp_path, co_ai, runner):
    root = _pinned_notebook(tmp_path, runner)
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    assert co_ai[0][1:-1] == PINNED[runner]


@pytest.mark.parametrize("runner", sorted(PINNED))
def test_the_scheduled_daily_investigation_has_tools_authorized(tmp_path, co_ai, monkeypatch, runner):
    from connectonion.rem.daily import run_daily
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: kind == "outlook")
    monkeypatch.setattr("connectonion.rem.daily.mail_client", lambda kind, **kw: Quiet())
    root = _pinned_notebook(tmp_path, runner)
    result = run_daily(root, scheduled=True,
                       maintain=lambda root, scheduled: {"outcome": "no_change"})
    assert result["run"]["outcome"] == "completed", result
    assert [argv[1:-1] for argv in co_ai] == [PINNED[runner]]


def test_a_daily_run_says_each_step_as_it_starts(tmp_path, co_ai, monkeypatch):
    """#2033: off a terminal, a sync printed nothing for 25 minutes, then everything."""
    from connectonion.rem.daily import run_daily
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: kind == "outlook")
    monkeypatch.setattr("connectonion.rem.daily.mail_client", lambda kind, **kw: Quiet())
    root = _pinned_notebook(tmp_path, "codex")
    said = []
    run_daily(root, scheduled=True, say=said.append,
              maintain=lambda root, scheduled: {"outcome": "no_change", "items": 0, "changed": []})
    assert said[0] == "Reading new material…"
    assert said[1].startswith("New material: 0 items, 0 pages changed")
    assert any(line.startswith("Investigating people/") for line in said), said


def test_runner_coai_is_co_ai_on_our_own_loop_and_its_own_default_model(tmp_path, co_ai):
    root = _notebook(tmp_path, "coai")
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    argv = co_ai[0]
    assert argv[1:3] == ["ai", "--json"] and argv[-1].startswith("/rem-investigate ")
    assert argv[3:5] == ["--harness", "ours"]
    assert not {"--sandbox", "--model"} & set(argv)


def test_the_status_line_names_the_sources_searched_and_does_not_claim_the_web(tmp_path, co_ai):
    """Whether the web was reached is the Skill's to report on the page: a real
    run had `co browser` fail inside the thread while the line still said web."""
    from connectonion.rem.files import Notebook
    for runner in ("codex", "coai"):
        root = _notebook(tmp_path / runner, runner)
        inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                        clients={"outlook": Quiet()}, subscriptions={})
        status = next(line for line in Notebook(root).read("people/vern.md").splitlines()
                      if line.startswith("Investigation:"))
        assert "outlook" in status and "web" not in status, (runner, status)


def test_investigation_status_excludes_sources_not_searched(tmp_path, monkeypatch):
    root = _notebook(tmp_path, "codex")
    monkeypatch.setattr(inv, "gather", lambda *args, **kwargs: ([
        {"source": "codex:s:1", "role": "user", "timestamp": "2026-09-01", "text": "Vern's project"}], [
        "outlook: project mail not requested; not searched",
        "gmail: project mail not requested; not searched",
        "codex: 10 messages in window, 0 related to subject, 0 read",
        "claude-code: 3 messages in window, 0 related to subject, 0 read",
    ]))
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=5,
                    clients={}, subscriptions={}, runner=lambda *args, **kwargs: {"changed": []})
    from connectonion.rem.files import Notebook
    status = next(line for line in Notebook(root).read("people/vern.md").splitlines()
                  if line.startswith("Investigation:"))
    assert "codex, claude-code" in status
    assert "outlook" not in status and "gmail" not in status
    assert "Requested investigation window" not in status


def test_oversized_attachment_is_split_without_losing_text_or_sources():
    config = {"limits": {"extract_items_per_batch": 40, "extract_chars_per_batch": 500}}
    items = [{"text": '合同条款\\\"\n' * 600, "source": "gmail:contract.pdf",
              "timestamp": "2026-09-01T00:00:00Z", "role": "attachment"},
             {"text": "Latest signed terms", "source": "outlook:signed",
              "timestamp": "2026-09-02T00:00:00Z", "role": "other"}]
    seen = []

    def extract(chunk, config, kind):
        assert len(json.dumps(chunk, ensure_ascii=False)) <= 500
        seen.extend(chunk)
        return {"notes": "A sourced digest", "usage": {"input_tokens": 10}}

    digests, usage = inv.digest_in_chunks(items, config, extract)
    for original in items:
        assert "".join(i["text"] for i in seen if i["source"] == original["source"]) == original["text"]
    assert seen[-1]["source"] == "outlook:signed"
    assert usage["input_tokens"] == len(digests) * 10


def test_chunk_limit_counts_the_text_the_model_is_given():
    from connectonion.rem.runner import readable_material
    item = {"text": "x", "source": "gmail:1", "timestamp": "2026-09-01T00:00:00Z"}
    limit = len(readable_material([item, item]).encode("utf-8")) - 1
    config = {"limits": {"extract_items_per_batch": 40, "extract_chars_per_batch": limit}}
    batches = []
    stages = []

    def extract(chunk, config, kind):
        batches.append(chunk)
        return {"notes": "Notes"}

    inv.digest_in_chunks([item, item], config, extract,
                         progress=lambda stage, current, total, usage: stages.append((stage, current, total, usage)))
    assert len(batches) == 2
    assert stages == [("extracting long evidence", 1, 2, {}),
                      ("extracting long evidence", 2, 2, {})]
    assert all(len(readable_material(c).encode("utf-8")) <= limit for c in batches)


def test_completed_extraction_chunks_are_reused_after_interruption(tmp_path):
    root = _notebook(tmp_path, "codex")
    item = {"source": "gmail:one", "timestamp": "2026-09-20", "text": "A" * 60}
    config = {"runner": "codex", "model": "gpt-6-luna", "limits": {
        "extract_items_per_batch": 1, "extract_chars_per_batch": 300}}
    calls = []

    def extract(chunk, settings, kind):
        calls.append(chunk)
        return {"notes": "Supported note", "usage": {"input_tokens": 20}}

    first, usage = inv.digest_in_chunks([item], config, extract, root=root)
    second, reused_usage = inv.digest_in_chunks([item], config, extract, root=root)
    assert first == second and len(calls) == 1
    assert usage == {"input_tokens": 20} and reused_usage == {}
    assert (root / '.state/extracts/investigate').is_dir()


def test_over_input_limit_the_writer_searches_evidence_files_instead_of_digests(tmp_path, monkeypatch):
    """#1850: summarising everything first cost the owner's page 39 digest calls
    and 75 minutes. Over the limit, the material becomes files the one turn
    searches; no digest call is made."""
    root = _notebook(tmp_path, "codex")
    config = read_config(root)
    original = inv.Notebook(root).read("people/vern.md")
    items = [{"text": f"message {i}: " + "x" * 30_000, "source": f"outlook:{i}", "role": "other",
              "speaker": "vern@x.y", "subject": f"Contract {i}",
              "timestamp": f"2026-09-{i + 1:02d}T00:00:00Z"} for i in range(12)]
    items[7]["text"] += " The capstone runs 3 March to 30 May."
    assert len(json.dumps(items)) > config["limits"]["input_chars_per_batch"]
    monkeypatch.setattr(inv, "gather", lambda *a, **kw: (items, ["outlook: 12 matched"]))
    seen = {}

    def write(notebook, material, config, **kw):
        evidence = next(i for i in material if i["role"] == "evidence-index")
        index = Path(evidence["file"])
        folder = index.parent
        seen.update(folder=folder, sources=evidence["sources"])
        assert original in material[0]["text"]
        assert len(json.dumps(material)) < config["limits"]["input_chars_per_batch"]
        assert "has NOT been summarised" in evidence["text"] and str(folder) in evidence["text"]
        # Every item is on disk under its citable id, and a search finds the needle.
        text = "\n".join(p.read_text() for p in folder.rglob("*.md") if p.name != "index.md")
        assert all(f"### {i['source']} ·" in text for i in items)
        hit = [p for p in folder.rglob("*.md") if "capstone runs 3 March" in p.read_text()]
        assert len(hit) == 1 and "### outlook:7 ·" in hit[0].read_text()
        assert hit[0].relative_to(folder).as_posix() in index.read_text()
        page = notebook.path("people/vern.md")
        page.write_text(original.replace("- Role: Unknown", "- Role: Account owner [1]"))
        return {"changed": ["people/vern.md"], "usage": {"input_tokens": 5}}

    out = inv.investigate(root, "people/vern.md", "Vern", ["me@x.y"], days=7, clients={}, subscriptions={},
                          extractor=lambda *a: pytest.fail("no digest pass"), runner=write)

    assert out["changed"] == ["people/vern.md"] and out["usage"] == {"input_tokens": 5}
    assert sorted(seen["sources"]) == sorted(i["source"] for i in items)
    assert any(line.startswith("evidence: ") and "searched, not summarised" in line for line in out["coverage"])
    assert not seen["folder"].exists(), "private mail copies are removed after the run"
    assert "investigated" in inv.Notebook(root).read("people/vern.md")


def test_over_input_limit_a_summary_tier_model_is_handed_digests_not_files(tmp_path, monkeypatch):
    """#1847: a model that can only reply cannot search evidence files, so over
    the limit it gets the material digested in order, inline in its one turn."""
    from connectonion.rem.files import state_path, write_json
    root = _notebook(tmp_path, "codex")
    config = read_config(root)
    write_json(state_path(root, "tier.json"), {"tier": "summary", "runner": config["runner"],
                                               "model": config["model"]})
    items = [{"text": f"message {i}: " + "x" * 30_000, "source": f"outlook:{i}", "role": "other",
              "speaker": "vern@x.y", "subject": f"Contract {i}",
              "timestamp": f"2026-09-{i + 1:02d}T00:00:00Z"} for i in range(12)]
    monkeypatch.setattr(inv, "gather", lambda *a, **kw: (items, ["outlook: 12 matched"]))
    digested = []

    def extract(chunk, settings, kind):
        digested.append(len(chunk))
        return {"notes": f"- Vern signed contract [{chunk[0]['source']}]", "usage": {"input_tokens": 1}}

    def write(notebook, material, config, **kw):
        assert not any(i["role"] == "evidence-index" for i in material)
        assert any("Vern signed contract" in i.get("text", "") for i in material)
        return {"changed": [], "usage": {"input_tokens": 5}}

    out = inv.investigate(root, "people/vern.md", "Vern", ["me@x.y"], days=7, clients={}, subscriptions={},
                          extractor=extract, runner=write)

    assert digested and sum(digested) >= len(items)
    assert any(line.startswith("digest: ") and "summary-tier" in line for line in out["coverage"])


def test_a_page_citing_an_evidence_file_entry_passes_the_source_check(tmp_path):
    from connectonion.rem.page_review import validate

    root = _notebook(tmp_path, "codex")
    original = inv.Notebook(root).read("people/vern.md")
    items = [{"role": "evidence-index", "source": "investigation:evidence", "sources": ["outlook:7"],
              "text": "index"}]

    def cited(source):
        head, _, tail = original.partition("\n## Sources\n")
        body = head.replace("- Role: Unknown", "- Role: Capstone supervisor [1]")
        return body + "\n## Sources\n- [1] " + source + "\n" + tail.split("\n", 1)[-1]

    errors = [e for e in validate("people/vern.md", cited("outlook:7"), original, items) if "source" in e]
    invented = [e for e in validate("people/vern.md", cited("outlook:99"), original, items) if "source" in e]

    assert errors == [] and invented == ["Citation has no identifiable source: 1"]


def test_impossible_chunk_limit_fails_before_spending_tokens():
    config = {"limits": {"extract_items_per_batch": 40, "extract_chars_per_batch": 5}}
    items = [{"text": "x", "source": "outlook:1", "timestamp": "2026-09-01T00:00:00Z"}]
    with pytest.raises(inv.RemError, match="increase limits.extract_chars_per_batch"):
        inv.digest_in_chunks(items, config, lambda *a: pytest.fail("must validate before calling the model"))


def test_coding_search_continues_past_first_batch_and_matches_aliases(tmp_path, monkeypatch):
    from connectonion.rem.source import Batch
    seen = []
    def collect(sub, cursor, *limits):
        seen.append(cursor)
        if not cursor:
            return Batch([{"text": "unrelated", "timestamp": "2026-09-01", "source": "codex:1"}], {"offset": 40})
        if cursor == {"offset": 40}:
            return Batch([{"text": "odi accepted the terms", "timestamp": "2026-09-02",
                           "source": "codex:2"}], {"offset": 80})
        return Batch([], cursor)
    monkeypatch.setattr(inv, "collect", collect)
    items, coverage = inv.gather("Ody Zhou", ["ody@example.org", "odi"], days=30, clients={},
                                subscriptions={"codex": {"kind": "codex", "root": str(tmp_path)}})
    assert [i["source"] for i in items] == ["codex:2"]
    assert seen == [{}, {"offset": 40}, {"offset": 80}]
    assert "2 messages" in next(line for line in coverage if line.startswith("codex"))


@pytest.mark.parametrize("stdout,returncode", [
    ("", 1), ("not JSON", 0), ("{}", 0),
    (json.dumps({"outcome": "natural", "result": "ok"}), 1),
    (json.dumps({"outcome": "error", "error": "model unavailable"}), 0),
])
def test_failed_command_never_marks_owner_investigated(tmp_path, monkeypatch, co_ai, stdout, returncode):
    root = _notebook(tmp_path, "codex")
    before = inv.Notebook(root).read("people/vern.md")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: types.SimpleNamespace(
        stdout=stdout, stderr="command failed", returncode=returncode))
    with pytest.raises(inv.RemError, match="co ai"):
        inv.investigate(root, "people/vern.md", "Vern", ["vern"], days=7,
                        clients={"outlook": Quiet()}, subscriptions={})
    assert inv.Notebook(root).read("people/vern.md") == before


def test_timeout_preserves_unfinished_page(tmp_path, monkeypatch, co_ai):
    import subprocess
    root = _notebook(tmp_path, "codex")
    before = inv.Notebook(root).read("people/vern.md")

    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired("co ai", 900)

    monkeypatch.setattr("subprocess.run", timeout)
    with pytest.raises(inv.RemError, match="timed out"):
        inv.investigate(root, "people/vern.md", "Vern", ["vern"], days=7,
                        clients={"outlook": Quiet()}, subscriptions={})
    assert inv.Notebook(root).read("people/vern.md") == before


def test_a_person_s_mail_is_asked_of_the_server_not_found_by_listing_everything():
    """Listing the whole window took minutes per person and a busy week past the
    listing cap lost mail silently. With the person's addresses in hand, the
    mailbox is asked for exactly their mail, every address once."""
    class Searchable(Quiet):
        asked = []
        def list_between(self, s, e, n): raise AssertionError("listed the whole mailbox")
        def list_with(self, address, start, end):
            self.asked.append(address)
            return [{"id": f"{address}-1", "from": f"Vern <{address}>", "to": ["me@x.y"],
                     "subject": "Practice of Work", "date": "2026-07-21T00:00:00Z"}]
        def get_email_body(self, i): return "--- Email Body ---\nOne team of 4-6 works."

    box = Searchable()
    items, coverage = inv.gather("Vern Chan", ["vern.chan@unsw.edu.au", "vern@founders.unsw.edu.au", "Vern Chan"],
                                 days=90, clients={"outlook": box}, subscriptions={})
    assert box.asked == ["vern.chan@unsw.edu.au", "vern@founders.unsw.edu.au"]
    assert [i["text"].split("\n")[-1] for i in items] == ["One team of 4-6 works."] * 2
    assert "searched on the server" in coverage[0] and "2 matched" in coverage[0]


def test_an_org_s_mail_is_asked_of_the_server_by_domain_not_found_by_listing_everything():
    """UNSW spent ten of 18.5 minutes listing 2,269 Outlook and 1,557 Gmail headers
    week by week to find one domain (#1963). The mailbox can answer "mail from or
    to this domain" itself; what it answers loosely is still checked here."""
    box = LikeGraph()
    items, coverage = inv.gather("UNSW", ["@unsw.edu.au", "unsw.edu.au", "UNSW"], days=90,
                                 clients={"outlook": box}, subscriptions={}, record="orgs/unsw.md")
    assert box.asked == ["unsw"]            # #1981: Graph answers 500 for participants:<bare domain>
    assert [i["text"].split("\n")[-1] for i in items] == ["body 1"]
    assert "searched on the server for unsw" in coverage[0] and "1 matched" in coverage[0]


class LikeGraph(Quiet):
    """What Graph did on the owner's mailbox (2026-09-30): `participants:unsw.edu.au`
    and `participants:@unsw.edu.au` → HTTP 500; `participants:unsw` → rows."""
    def __init__(self): self.asked = []
    def list_between(self, s, e, n): raise AssertionError("listed the whole mailbox")
    def list_with(self, address, start, end, **kw):
        from connectonion.provider_credentials import ProviderCredentialError
        self.asked.append(address)
        if "." in address and "@" not in address.lstrip("@") or address.startswith("@"):
            raise ProviderCredentialError("provider_unavailable", "Microsoft Graph API error (HTTP 500).",
                                          "co outlook inbox", status=500)
        return [{"id": "1", "from": "Ada <ada@unsw.edu.au>", "to": ["me@x.y"],
                 "subject": "Pilot", "date": "2026-07-21T00:00:00Z"},
                {"id": "2", "from": "Bo <bo@elsewhere.org>", "to": ["me@x.y"],
                 "subject": "Unrelated", "date": "2026-07-22T00:00:00Z"}]
    def get_email_body(self, i): return f"--- Email Body ---\nbody {i}"


def test_a_mailbox_that_fails_is_a_gap_in_coverage_and_the_other_mailbox_is_still_read():
    """#1981: one Graph 500 ended every org investigation before Gmail was asked."""
    class Broken(LikeGraph):
        def list_with(self, address, start, end, **kw):
            from connectonion.provider_credentials import ProviderCredentialError
            raise ProviderCredentialError("provider_unavailable", "Microsoft Graph API error (HTTP 500).",
                                          "co outlook inbox", status=500)

    class Gmail(LikeGraph):
        def list_with(self, address, start, end, **kw):
            self.asked.append(address)
            return LikeGraph.list_with(self, "unsw", start, end)

    gmail = Gmail()
    items, coverage = inv.gather("UNSW", ["unsw.edu.au"], days=90, clients={"outlook": Broken(), "gmail": gmail},
                                 subscriptions={}, record="orgs/unsw.md")
    assert gmail.asked[0] == "unsw.edu.au"          # Gmail takes the bare domain
    assert any(l.startswith("outlook") and "server search failed (HTTP 500); not searched" in l for l in coverage)
    assert [i["text"].split("\n")[-1] for i in items] == ["body 1"]


def test_a_person_handle_shaped_like_a_domain_is_not_a_domain_search():
    """"vern.chan" is a person's alias, not a domain; people keep their own path."""
    class Listing(Quiet):
        listed = 0
        def list_between(self, s, e, n):
            self.listed += 1
            return []
        def list_with(self, *a, **k): raise AssertionError("searched a person by domain")

    box = Listing()
    inv.gather("Vern", ["vern.chan", "Vern"], days=14, clients={"outlook": box}, subscriptions={},
               record="people/vern.md")
    assert box.listed


def test_session_progress_carries_a_count_and_never_repeats_a_line(tmp_path, monkeypatch):
    """Sessions printed up to 24 identical "gathering claude-code sessions" lines and
    no count (#1963): a reader could not tell progress from a loop."""
    from connectonion.rem.source import Batch
    batches = iter([Batch([{"text": "a", "timestamp": "2026-07-01T00:00:00+00:00"}] * 40, {"n": 1}),
                    Batch([], {"n": 2}),
                    Batch([{"text": "b", "timestamp": "2026-07-02T00:00:00+00:00"}] * 3, {"n": 3}),
                    Batch([], {"n": 3})])
    monkeypatch.setattr(inv, "collect", lambda *a, **k: next(batches))
    lines = []
    inv.gather("Vern", ["vern"], days=14, clients={}, record="people/vern.md",
               subscriptions={"claude-code": {"kind": "claude-code", "root": str(tmp_path)}},
               stage_progress=lambda stage, *counts: lines.append(stage))
    assert lines == ["gathering claude-code sessions: 40 scanned", "gathering claude-code sessions: 43 scanned"]


def test_a_mailbox_not_searched_is_named_in_coverage():
    _, coverage = inv.gather("Vern Chan", ["vern.chan@unsw.edu.au"], days=30, clients={"outlook": Quiet()},
                             subscriptions={"gmail": {"kind": "gmail", "unsubscribed": True}})
    assert "gmail: unsubscribed by the user; not searched" in coverage
    _, coverage = inv.gather("Vern Chan", ["vern.chan@unsw.edu.au"], days=30, clients={}, subscriptions={})
    assert any(line.startswith("outlook: not connected (co auth microsoft)") for line in coverage)


def test_a_model_the_login_cannot_run_is_named_with_the_fix(tmp_path, monkeypatch):
    """Codex 0.155 refuses Spark for ChatGPT logins at the first turn; the provider's
    JSON told nobody what to do next."""
    root = _notebook(tmp_path, "codex")
    refused = json.dumps({"outcome": "error", "error": 'turn failed: {"status":400,"error":{"message":'
                          '"The \'gpt-5.3-codex-spark\' model is not supported when using Codex with a ChatGPT account."}}'})
    monkeypatch.setattr("subprocess.run", lambda *a, **k: types.SimpleNamespace(stdout=refused, stderr="", returncode=1))
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/co")
    config = read_config(root)
    from connectonion.rem.runner import RunFailed, run_task
    with pytest.raises(RunFailed, match="co rem config set model gpt-6-luna"):
        run_task(root, "prompt", config, "investigate")


def test_a_listed_source_nobody_cites_is_dropped_not_a_reason_to_refuse_the_page(tmp_path, monkeypatch):
    """A real Ian Chan page was refused whole because its Sources listed the old
    page as [1] and no sentence cited it. The listing is harmless; the page was not."""
    from pathlib import Path
    from connectonion.rem.files import Notebook

    def fake_run(argv, cwd, capture_output, text, timeout, env=None):
        import re
        path = Path(re.search(r'NEW file (.+?candidate.md)', argv[-1])[1])
        page = next(Path(cwd).glob('investigate-*/notebook/people/vern.md')).read_text()
        page = page.replace("## Who they are\n- Unknown — not investigated yet",
                            "## Who they are\n- Vern works at UNSW. [W1]", 1)
        page = page.replace("## Sources\n- (none yet)",
                            "## Sources\n- [1] Existing page people/vern.md, prior context only.\n"
                            "- [W1] https://www.unsw.edu.au/staff/vern-chan, observed 2026-09-23.", 1)
        path.write_text(page.replace("- Unknown — not investigated yet", "- Unknown"))
        return types.SimpleNamespace(stdout=json.dumps({"outcome": "natural", "result": "ok", "usage": None}),
                                     stderr="", returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/co")
    root = _notebook(tmp_path, "codex")
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    page = Notebook(root).read("people/vern.md")
    assert "Vern works at UNSW. [W1]" in page
    assert "[W1] https://www.unsw.edu.au/staff/vern-chan" in page and "[1] Existing page" not in page


def test_a_message_read_through_a_digest_can_still_be_cited_by_its_own_id():
    """Ody Zhou's 201 mails were digested first, and the page cited the real
    message ids the digests named -- all refused, because the digest item kept
    only "gmail +4". Everyone with enough mail to need a digest was refused."""
    from connectonion.rem.extract import extraction_item
    from connectonion.rem.page_review import validate
    from connectonion.rem.files import Notebook
    import tempfile
    from pathlib import Path
    root = Path(tempfile.mkdtemp()) / "rem"
    prepare(root)
    notebook = Notebook(root)
    notebook.stub_person("people/ody.md", "Ody Zhou", ["ody"], email="zhouodywork@gmail.com")
    original = notebook.read("people/ody.md")
    chunk = [{"source": "gmail:3a7a430fcee5", "timestamp": "2026-08-01T00:00:00+00:00", "text": "a"},
             {"source": "gmail:db0abd133958:Draft_v8.docx", "timestamp": "2026-08-02T00:00:00+00:00", "text": "b"}]
    items = [extraction_item("Ody drafted v8 of the Emma agreement (gmail:db0abd133958).", chunk)]
    candidate = original.replace("## Who they are\n- Unknown — not investigated yet",
                                 "## Who they are\n- Ody drafts contracts. [1]", 1).replace(
        "## Sources\n- (none yet)",
        "## Sources\n- [1] `gmail:3a7a430fcee5`, `gmail:db0abd133958:Draft_v8.docx`, observed 2026-09-23.", 1)
    assert validate("people/ody.md", candidate, original, items) == []
    forged = candidate.replace("gmail:3a7a430fcee5", "gmail:ffffffffffff").replace(
        "`gmail:db0abd133958:Draft_v8.docx`, ", "")
    assert validate("people/ody.md", forged, original, items)          # an id no digest read is still refused
    session = [{"source": "claude-code:3994b2ee-ff35:81", "timestamp": "2026-08-30T00:00:00+00:00", "text": "c"},
               {"source": "gmail:c74572cd7d0e", "timestamp": "2026-08-31T00:00:00+00:00", "text": "d"}]
    items.append(extraction_item("Dora reviewed the deck.", session))
    whole = original.replace("## Who they are\n- Unknown — not investigated yet",
                             "## Who they are\n- Dora reviews decks. [1]", 1).replace(
        "## Sources\n- (none yet)", "## Sources\n- [1] `claude-code:3994b2ee-ff35`, observed 2026-08-30.", 1)
    assert validate("people/ody.md", whole, original, items) == []     # the whole session it came from


def test_the_owners_own_address_never_lands_on_someone_elses_page(tmp_path, monkeypatch):
    """Dora's page listed xietianle@outlook.com -- the user's own Outlook -- as her
    email and handle, from mail the two of them exchanged. The owner's addresses
    are known; they are removed mechanically, the rest of the page is kept."""
    from pathlib import Path
    from connectonion.rem.files import Notebook, state_path, write_json

    def fake_run(argv, cwd, capture_output, text, timeout, env=None):
        import re
        path = Path(re.search(r'NEW file (.+?candidate.md)', argv[-1])[1])
        page = next(Path(cwd).glob('investigate-*/notebook/people/vern.md')).read_text()
        page = re.sub(r'^- Email: .*$', '- Email: vern.chan@unsw.edu.au; me@outlook.com', page, count=1, flags=re.M)
        page = re.sub(r'^- Handles: .*$', '- Handles: me@outlook.com', page, count=1, flags=re.M)
        page = page.replace("## Who they are\n- Unknown — not investigated yet",
                            "## Who they are\n- Vern works at UNSW. [W1]", 1).replace(
            "## Sources\n- (none yet)", "## Sources\n- [W1] https://www.unsw.edu.au/staff/vern-chan, observed 2026-09-23.", 1)
        path.write_text(page.replace("- Unknown — not investigated yet", "- Unknown"))
        return types.SimpleNamespace(stdout=json.dumps({"outcome": "natural", "result": "ok", "usage": None}),
                                     stderr="", returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/co")
    root = _notebook(tmp_path, "codex")
    write_json(state_path(root, "map.json"), {"owner": {"record": "people/me.md", "addresses": ["me@outlook.com"]}})
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    page = Notebook(root).read("people/vern.md")
    assert "me@outlook.com" not in page
    assert "- Email: vern.chan@unsw.edu.au" in page and "- Handles: Unknown" in page


def test_the_owners_page_reads_what_the_owner_sent_from_every_address():
    """`investigate me` passes all the owner's addresses. A mailbox knows only its
    own login, so the others were searched for as if they were other people and
    the first real run found 6 of about 150 sent mails."""
    class Box:
        def my_addresses(self): return {"me@outlook.com"}
        def list_with(self, *a, **k): raise AssertionError("the owner is not a correspondent to search for")
        def list_between(self, start, end, n):
            return [{"id": "a", "from": "me@outlook.com", "to": ["x@y.z"], "date": start, "subject": "s"},
                    {"id": "b", "from": "Me <me@mail.example.org>", "to": ["x@y.z"], "date": start, "subject": "s"},
                    {"id": "c", "from": "x@y.z", "to": ["me@outlook.com"], "date": start, "subject": "s"}]
        def get_email_body(self, i): return f"body {i}"
    items, coverage = inv.gather("Me", ["me@outlook.com", "me@mail.example.org"], days=7,
                                 clients={"outlook": Box()}, subscriptions={}, sent_only=True)
    assert sorted(i["text"] for i in items) == ["body a", "body b"]          # both addresses, only what was sent
    assert "kept the owner's own sent mail" in coverage[0]


def test_a_mailbox_left_out_on_purpose_says_why_not_that_it_is_disconnected():
    """A project page skips mail by design; its coverage said "not connected (co auth
    microsoft)", which sends a user to log in again for nothing."""
    items, coverage = inv.gather("Aurora", ["/work/aurora"], days=7, clients={}, subscriptions={},
                                 mail_skipped="not read for a project page; name its mail with --handle")
    assert "outlook: not read for a project page; name its mail with --handle; not searched" in coverage
    assert not any("co auth" in line for line in coverage)


def test_project_gather_withholds_unnamed_followup_after_other_project_in_same_session(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).isoformat()
    window = [
        {"role": "user", "source": "claude-code:session:12", "project": "/work/other",
         "timestamp": stamp, "text": "Build the Other product's reply listener."},
        {"role": "user", "source": "claude-code:session:50", "project": "/work/tide",
         "timestamp": stamp, "text": "Why no reply?"},
        {"role": "user", "source": "claude-code:session:90", "project": "/work/tide",
         "timestamp": stamp, "text": "Tide: fix the parser."},
    ]
    monkeypatch.setattr(inv, "_window_items", lambda *args, **kwargs: (window, 0))
    items, coverage = inv.gather("Tide", ["/work/tide", "Tide"], days=7, clients={},
                                 subscriptions={"claude": {"kind": "claude-code", "root": str(tmp_path),
                                                           "enabled": True}}, record="projects/tide.md")
    assert [item["source"] for item in items] == ["claude-code:session:90"]
    assert any("1 unnamed follow-up(s) withheld" in line for line in coverage)


def test_project_writer_does_not_receive_collector_coverage_as_evidence(tmp_path, monkeypatch):
    root = _notebook(tmp_path, "codex")
    repo = tmp_path / "tide"
    repo.mkdir()
    (repo / "README.md").write_text("Tide reads a local log.\n")
    inv.Notebook(root).stub_project("projects/tide.md", "Tide", [str(repo)])
    messages = [{"role": "user", "source": "codex:session:10", "project": str(repo),
                 "timestamp": "2026-10-02T00:00:00+00:00", "text": "Check Tide's local log."}]
    monkeypatch.setattr(inv, "gather", lambda *args, **kwargs: (messages, ["codex: one input read"]))
    seen = []
    result = inv.investigate(root, "projects/tide.md", "Tide", [str(repo)], days=7,
                             clients={}, subscriptions={},
                             runner=lambda notebook, items, config, stage: seen.extend(items) or {"changed": []})
    assert not any(item.get("source") == "investigation:coverage" for item in seen)
    assert "codex: one input read" in result["coverage"]


def test_repository_only_project_investigation_records_zero_session_coverage(tmp_path, monkeypatch):
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.project_material import page_state
    root = _notebook(tmp_path, "codex")
    repo = tmp_path / "tide"
    repo.mkdir()
    (repo / "README.md").write_text("Tide reads a local log.\n")
    inv.Notebook(root).stub_project("projects/tide.md", "Tide", [str(repo)])
    write_json(state_path(root, "projects/tide/state.json"), {"messages": 5})
    monkeypatch.setattr(inv, "gather", lambda *args, **kwargs: ([], ["no session inputs assigned"]))
    seen = []
    inv.investigate(root, "projects/tide.md", "Tide", [str(repo)], days=7,
                    clients={}, subscriptions={},
                    runner=lambda notebook, items, config, stage: seen.extend(items) or {"changed": []})
    assert any(item.get("role") == "project-input-scope" and item.get("inputs_read") == 0 for item in seen)
    assert not any(item.get("source") == "investigation:coverage" for item in seen)
    assert page_state(root, "projects/tide.md")["last_page_coverage"] == {
        "inputs_read": 0, "inputs_available": 5, "days": 7, "scope": "archived"}


def test_the_status_line_never_names_the_evidence_layout_as_a_source():
    """#1962: pages were stamped `(outlook, gmail, codex, claude-code, evidence)`;
    evidence is how the material was laid out, not where it came from."""
    coverage = [
        "outlook (me@x.y): searched on the server for t@x.y over 150 days, 50 matched, 50 bodies read",
        "gmail (me@g.com): searched on the server for t@x.y over 150 days, 0 matched, 0 bodies read",
        "codex: 1,200 messages in window, 0 related to subject, 0 read (handle or project match)",
        "claude-code: 900 messages in window, 3 related to subject, 3 read (handle or project match)",
        "whatsapp: no chats chosen, not searched",
        "evidence: 2,160,000 chars gathered, written to 303 files and searched, not summarised first",
        "Requested investigation window: 150 days ending 2026-09-30",
        # #2045: any note, not only the ones listed by name, stays off the line.
        "3 gathered item(s) already cited on the page, not re-read",
        "Requested investigation window (people update): 4 days",
    ]

    assert inv.searched_sources(coverage) == ["outlook", "gmail", "codex", "claude-code"]


def test_an_accepted_investigation_refreshes_the_index(tmp_path):
    from connectonion.rem import store
    notebook = inv.Notebook(tmp_path)
    notebook.stub_person("people/river.md", "River", ["river@example.test"], email="river@example.test")
    store.refresh(tmp_path)
    assert not store.person(tmp_path, "people/river.md")["written"]
    notebook.write("people/river.md", notebook.read("people/river.md").replace("- Role: Unknown", "- Role: Designer [1]"))
    inv.record_result(tmp_path, notebook, "people/river.md", [], ["gmail"], changed=True)
    indexed = store.person(tmp_path, "people/river.md")
    assert indexed["written"]
    assert indexed["role"] == "Designer"


def test_project_investigation_retains_its_partial_input_window(tmp_path):
    from connectonion.rem.project_material import page_state
    from connectonion.rem.reader import snapshot
    notebook = inv.Notebook(tmp_path)
    record = "projects/tide.md"
    notebook.stub_project(record, "Tide", ["/work/tide"])
    inv.record_result(tmp_path, notebook, record, [], ["codex"],
                      project_coverage={"inputs_read": 3, "inputs_available": 5, "days": 150,
                                        "scope": "archived"})
    assert page_state(tmp_path, record)["last_page_coverage"]["inputs_read"] == 3
    shown = next(row for row in snapshot(tmp_path)["records"] if row["path"] == record)
    assert shown["project_coverage"] == {"inputs_read": 3, "inputs_available": 5, "days": 150,
                                         "scope": "archived"}


def test_an_accepted_investigation_drops_the_map_s_mail_count_from_history():
    """#2045: after reading 32 of Jiexuan Deng's mails the page still said
    "Observed mail count: 2", the map's window-limited count."""
    page = ("# Jiexuan\n\n## History\n- Observed mail count: 2; first: 2026-09-23; last: 2026-09-23 [1]\n"
            "- 2026-09-29: agreed the pilot scope [2]\n\n## Sources\n- [1] map\n- [2] outlook:abc\n")
    dropped = inv.drop_map_count(page)
    assert "Observed mail count" not in dropped
    assert "- 2026-09-29: agreed the pilot scope [2]\n\n## Sources\n" in dropped
    only = "# J\n\n## History\n- Observed mail count: 2; first: x [1]\n\n## Sources\n- [1] map\n"
    assert inv.drop_map_count(only) == only   # History's only entry stays


def test_a_page_investigated_before_is_read_again_only_since_then(tmp_path, monkeypatch):
    """Owner, 2026-09-30: the script already read everything before the last
    investigation into the page; asking again re-read months to add a week."""
    from datetime import date, timedelta
    root = _notebook(tmp_path, "codex")
    notebook = inv.Notebook(root)
    assert inv.window_since(notebook.read("people/vern.md")) == 730        # never investigated: two years
    ten_days_ago = (date.today() - timedelta(days=10)).isoformat()
    page = notebook.read("people/vern.md").replace("· not investigated yet", f"· investigated {ten_days_ago} (gmail)")
    notebook.write("people/vern.md", page)
    assert 10 <= inv.window_since(page) <= 12                               # UTC vs local date at the edges

    seen = {}
    # One new mail: with none, the run stops before the model (#1974).
    monkeypatch.setattr(inv, "gather", lambda *a, **kw: (
        [{"source": "gmail:1", "role": "other", "timestamp": "2026-09-29", "text": "New."}], []))

    def write(book, material, config, **kw):
        seen["coverage"] = next(i["text"] for i in material if i["role"] == "coverage")
        return {"changed": [], "usage": None}

    out = inv.investigate(root, "people/vern.md", "Vern", ["vern@x.y"], days=11, clients={}, subscriptions={},
                          runner=write)
    assert f"Page last investigated {ten_days_ago}" in seen["coverage"]
    assert "Newly supplied originals may predate that run" in seen["coverage"]
    assert not any(s.startswith("Page last") for s in inv.searched_sources(out["coverage"]))


def test_a_page_written_from_its_sources_starts_the_next_window_too():
    """#1983: `projects write` stamped `written <date>`, which the window did not
    count, so the next investigation re-read 150 days (1.58M tokens)."""
    from datetime import date, timedelta
    written = (date.today() - timedelta(days=2)).isoformat()
    page = f"# Proj\n\nInvestigation: mapped 2026-09-01 · written {written} (own messages: codex)\n"
    assert inv.last_investigated(page) == date.fromisoformat(written)
    assert 2 <= inv.window_since(page) <= 4


def test_only_whole_addresses_are_searched_on_the_mail_server():
    """#1954: a handle still carrying a citation or prose is not an address; Gmail
    matched 677 unrelated mails for one such handle."""
    class Box(Quiet):
        asked = []
        def list_between(self, s, e, n): raise AssertionError("listed the whole mailbox")
        def list_with(self, address, start, end):
            self.asked.append(address)
            return []

    box = Box()
    inv.gather("Tamara", ["tamara.berryman@unsw.edu.au", "tamara.berryman@unsw.edu.au [2]",
                          "Tamara Berryman; t@x.y [2]", "Tamara"], days=7, clients={"gmail": box}, subscriptions={})

    assert box.asked == ["tamara.berryman@unsw.edu.au"]


def test_investigation_reads_the_main_checkout_not_a_stale_agent_worktree(tmp_path):
    # A throwaway worktree read as the project's state wrote "version 1.8.9b2"
    # the day 1.9.0a1 shipped (#1955).
    main = tmp_path / 'connectonion'
    (main / '.git/worktrees/agent-a1').mkdir(parents=True)
    (main / 'pyproject.toml').write_text('version = "1.9.0a1"')
    worktree = main / '.claude/worktrees/agent-a1'
    worktree.mkdir(parents=True)
    (worktree / '.git').write_text(f'gitdir: {main}/.git/worktrees/agent-a1\n')
    (worktree / 'pyproject.toml').write_text('version = "1.8.9b2"')
    page = f'# connectonion\n## Paths\n- {worktree} [3]\n- /elsewhere/notes\n- Sessions: 9\n## Sources\n'
    corrected = inv.collapse_worktree_paths(page)
    assert inv.project_paths(corrected) == [str(main), '/elsewhere/notes']
    assert '- Sessions: 9\n' in corrected
    assert inv.collapse_worktree_paths(corrected) == corrected
    assert inv.project_file_inventory(page) == [str(main / 'pyproject.toml')]


# ------------------------------------------------ #1974: no stamp without material


def test_nothing_gathered_refuses_before_any_model_call_and_does_not_stamp(tmp_path, monkeypatch):
    """1.9.0a2 stamped founders@unsw "investigated" from the page and the coverage note alone."""
    root = _notebook(tmp_path, 'codex')
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: (
        [], ['gmail (me@x.y): searched on the server for vern@x.y over 150 days, 0 matched, 0 bodies read']))
    before = inv.Notebook(root).read('people/vern.md')
    with pytest.raises(inv.NothingFound) as caught:
        inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], days=7, clients={}, subscriptions={},
                        runner=lambda *a, **kw: pytest.fail('no model call without material'))
    assert inv.Notebook(root).read('people/vern.md') == before
    message = str(caught.value)
    assert 'not marked investigated' in message
    assert '`co rem investigate people/vern.md --handle ADDRESS`' in message
    assert 'gmail' in message


def test_empty_digests_stop_before_the_page_turn_and_keep_their_usage(tmp_path, monkeypatch):
    """The founders@unsw log: 8 bodies read, "summarised in 0 chunk(s)", page stamped anyway."""
    from connectonion.rem.extract import NOTHING
    from connectonion.rem.files import state_path, write_json
    root = _notebook(tmp_path, 'codex')
    config = read_config(root)
    write_json(state_path(root, "tier.json"), {"tier": "summary", "runner": config["runner"],
                                               "model": config["model"], "checked_at": "2026-09-30"})
    rows = [{'source': f'gmail:{i}', 'role': 'other', 'timestamp': f'2026-09-{i + 1:02d}',
             'text': 'x' * 40_000} for i in range(8)]
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: (rows, ['gmail: 8 matched, 8 bodies read']))
    with pytest.raises(inv.NothingFound) as caught:
        inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], days=7, clients={}, subscriptions={},
                        runner=lambda *a, **kw: pytest.fail('no page turn on empty digests'),
                        extractor=lambda chunk, settings, kind: {'notes': NOTHING,
                                                                 'usage': {'input_tokens': 100}})
    assert caught.value.usage['input_tokens'] >= 100
    assert 'investigated 2' not in inv.Notebook(root).read('people/vern.md')


def test_the_skill_is_checked_before_minutes_of_gathering(tmp_path, monkeypatch):
    """A relative PYTHONPATH made the model's co ai import an older connectonion
    and fail with "Skill 'rem-investigate' not found" -- after the gather."""
    from connectonion.rem import runner
    root = _notebook(tmp_path, 'codex')

    def missing(root, stage):
        raise inv.RemError("co ai cannot find the rem-investigate Skill")
    monkeypatch.setattr(runner, 'check_skill', missing)
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: pytest.fail('checked before gathering'))
    with pytest.raises(inv.RemError, match='rem-investigate Skill'):
        inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], days=7, clients={}, subscriptions={})


def test_the_routed_original_evidence_copy_is_deleted_when_the_run_ends(tmp_path, monkeypatch):
    from connectonion.rem import inquiry
    root = _notebook(tmp_path, 'codex')
    monkeypatch.setattr(inquiry, 'routing', lambda root: {'plan': 'x'})
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: (
        [{'source': 'gmail:1', 'role': 'other', 'timestamp': '2026-09-01', 'text': 'Vern wrote.'}], ['gmail: 1']))
    inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], days=7, clients={}, subscriptions={},
                    runner=lambda *a, **kw: {'changed': [], 'usage': None})
    assert not list((root / '.state' / 'evidence').glob('*.json'))


def test_a_person_turn_is_told_the_org_pages_its_company_can_link_to(tmp_path, monkeypatch):
    """The page Skills say to link Company to the org page; 0 of 4 did, because the
    turn was never told which org pages exist (#1974)."""
    root = _notebook(tmp_path, 'codex')
    notebook = inv.Notebook(root)
    notebook.stub_org('orgs/unsw-1234.md', 'UNSW Sydney', ['unsw.edu.au'])
    notebook.stub_org('orgs/acme-5678.md', 'Acme', ['acme.example'])
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: (
        [{'source': 'gmail:1', 'role': 'other', 'timestamp': '2026-09-01', 'text': 'Vern wrote.'}], ['gmail: 1']))
    received = []
    inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern', 'vern.chan@unsw.edu.au'], days=7, clients={},
                    subscriptions={}, runner=lambda notebook, items, config, stage: received.extend(items) or
                    {'changed': [], 'usage': None})
    orgs = next(item for item in received if item['role'] == 'org-pages')
    assert 'orgs/unsw-1234.md — UNSW Sydney (unsw.edu.au)' in orgs['text'] and 'acme' not in orgs['text']
    assert '[Name](../orgs/<file>.md)' in orgs['text']


def test_a_project_turn_is_given_the_notebook_s_organisations(tmp_path):
    notebook = inv.Notebook(tmp_path)
    notebook.stub_org('orgs/acme-5678.md', 'Acme', ['acme.example'])
    notebook.stub_project('projects/tide.md', 'Tide', ['/w/tide'])
    assert inv.org_pages(notebook, 'projects/tide.md', ['/w/tide']) == ['orgs/acme-5678.md — Acme']
    assert inv.org_pages(notebook, 'people/nobody.md', ['someone@else.example']) == []


# ------------------------------------------------ #1982: a checkout on an old branch is not the project's state


def _repo(tmp_path):
    """A main checkout left on an August branch while main moved on to 1.9.0a3."""
    import os
    import subprocess
    repo = tmp_path / 'work' / 'connectonion'
    repo.mkdir(parents=True)

    def git(*args, date='2026-09-29T10:00:00+00:00'):
        env = {**os.environ, 'GIT_AUTHOR_DATE': date, 'GIT_COMMITTER_DATE': date, 'GIT_AUTHOR_NAME': 't',
               'GIT_AUTHOR_EMAIL': 't@x.y', 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@x.y',
               'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}
        subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, env=env)
    git('init', '-q', '-b', 'main')
    (repo / 'pyproject.toml').write_text('[project]\nversion = "1.8.0a3"\n')
    git('add', '.')
    git('commit', '-qm', 'August', date='2026-08-30T10:00:00+00:00')
    git('branch', 'feat/1.8-paid-browser-release')
    (repo / 'pyproject.toml').write_text('[project]\nversion = "1.9.0a3"\n')
    git('commit', '-qam', 'September')
    git('update-ref', 'refs/remotes/origin/main', 'main')
    git('checkout', '-q', 'feat/1.8-paid-browser-release')
    return repo


def test_a_checkout_weeks_behind_the_newest_session_is_flagged_and_the_version_comes_from_origin_main(tmp_path):
    """1.9.0a3: the main checkout was on an August branch, so the page said 1.8.0a3."""
    text = inv.checkout_state(str(_repo(tmp_path)), newest_session='2026-09-29')
    assert 'branch feat/1.8-paid-browser-release, HEAD committed 2026-08-30' in text
    assert 'origin/main, last committed 2026-09-29' in text
    assert 'version 1.9.0a3' in text and '1.8.0a3' not in text
    assert '30 days older than the newest session' in text


def test_a_checkout_on_the_current_line_is_recorded_without_a_warning(tmp_path):
    import subprocess
    repo = _repo(tmp_path)
    subprocess.run(['git', '-C', str(repo), 'checkout', '-q', 'main'], check=True, capture_output=True)
    text = inv.checkout_state(str(repo), newest_session='2026-09-29')
    assert 'branch main, HEAD committed 2026-09-29' in text and 'older than' not in text
    assert inv.checkout_state(str(tmp_path / 'not-a-repo')) == ''


def test_a_project_turn_is_given_the_checkout_state_as_citable_evidence(tmp_path, monkeypatch):
    root = _notebook(tmp_path, 'codex')
    repo = _repo(tmp_path)
    inv.Notebook(root).stub_project('projects/co.md', 'connectonion', [str(repo)], last_seen='2026-09-29')
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: ([], ['codex: 0 sessions in window']))
    received = []
    inv.investigate(root, 'projects/co.md', 'connectonion', [str(repo)], days=150, clients={}, subscriptions={},
                    runner=lambda notebook, items, config, stage: received.extend(items) or
                    {'changed': [], 'usage': None})
    state = next(item for item in received if item['role'] == 'checkout-state')
    assert state['origin'] == f'git:{repo}:checkout-state' and state['source'].startswith('project-source:')
    assert 'older than the newest session' in state['text']


# ------------------------------------------------ #1984: an empty since-window calls no model


def _investigated(root, record, days_ago):
    from datetime import date, timedelta
    notebook = inv.Notebook(root)
    day = (date.today() - timedelta(days=days_ago)).isoformat()
    page = notebook.read(record).replace("· not investigated yet", f"· investigated {day} (gmail)")
    # A real investigation cites what it read; one that cites nothing is hollow (#1974).
    notebook.write(record, page.replace("- (none yet)", "- [1] gmail:0123456789ab"))
    return day


def test_a_since_window_that_gathered_nothing_calls_no_model_and_says_nothing_new(tmp_path, monkeypatch):
    """1.9.0a3: Tamara's window since her last investigation gathered 0 items,
    0 mails and 0 sessions, and still made a 92k-token turn that deleted one line."""
    root = _notebook(tmp_path, 'codex')
    day = _investigated(root, 'people/vern.md', 3)
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: (
        [], ['gmail (me@x.y): searched on the server for vern@x.y over 4 days, 0 matched, 0 bodies read',
             'codex: 0 sessions in window']))
    before = inv.Notebook(root).read('people/vern.md')
    with pytest.raises(inv.NothingNew) as caught:
        inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], days=4, clients={}, subscriptions={},
                        runner=lambda *a, **kw: pytest.fail('no model call for an empty window'))
    assert inv.Notebook(root).read('people/vern.md') == before
    message = str(caught.value)
    assert f'Nothing new since {day}' in message and 'gmail' in message
    assert '--handle' not in message   # the handles found the subject before; nothing is wrong with them


def test_mail_the_page_already_cites_is_not_new_material(tmp_path, monkeypatch):
    """#2015: re-investigating Richard straight after re-read the same one mail
    (the window is whole days) and spent 102k tokens to find it "already
    represented as source [21]"."""
    root = _notebook(tmp_path, 'codex')
    _investigated(root, 'people/vern.md', 0)        # the page cites gmail:0123456789ab
    cited = {'source': 'gmail:0123456789ab', 'timestamp': '2026-09-30T09:00:00+00:00', 'text': 'same mail'}
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: ([cited], ['gmail (me@x.y): 1 matched, 1 bodies read']))
    with pytest.raises(inv.NothingNew) as caught:
        inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], days=1, clients={}, subscriptions={},
                        runner=lambda *a, **kw: pytest.fail('no model call for mail the page already cites'))
    assert 'already cited on the page' in str(caught.value)


def test_new_reply_keeps_exact_cited_request_outside_update_window(tmp_path):
    import hashlib
    from datetime import datetime, timedelta, timezone
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.mail_archive import retain_message
    from connectonion.rem.evidence import write_evidence

    root = _notebook(tmp_path, 'codex')
    record = 'people/vern.md'
    now = datetime.now(timezone.utc)
    write_json(state_path(root, 'mail/archive.json'), {
        'phase': 'complete', 'providers': ['outlook', 'gmail'], 'owner_addresses': ['me@example.org'],
        'range_start': (now - timedelta(days=90)).isoformat(), 'range_end': now.isoformat()})
    rows = [('outlook', 'ask', 'scope', ['vern.chan@unsw.edu.au'], 'Please approve integration A only.', 30),
            ('outlook', 'reply', 'scope', [], 'Approved integration A only.', 0.1),
            ('outlook', 'other-ask', 'other-scope', ['vern.chan@unsw.edu.au'], 'Please approve B.', 30),
            ('gmail', 'provider-collision', 'scope', ['vern.chan@unsw.edu.au'], 'Please approve C.', 30),
            ('outlook', 'unthreaded', '', ['vern.chan@unsw.edu.au'], 'Please approve D.', 30)]
    for provider, native, thread, cc, body, days in rows:
        retain_message(root, provider, {'id': native, 'thread_id': thread, 'from': 'lead@school.example',
            'to': ['me@example.org'], 'cc': cc, 'subject': 'Scope approval',
            'date': (now - timedelta(days=days)).isoformat()}, body, fetched_at=now.isoformat())
    source = lambda provider, native: provider + ':' + hashlib.sha256(native.encode()).hexdigest()[:12]
    _investigated(root, record, 2)
    notebook = inv.Notebook(root)
    cited = '\n'.join(f'- [{i}] {source(provider, native)}' for i, (provider, native, *_) in enumerate(rows, 1)
                      if native != 'reply')
    before = notebook.read(record).replace('- [1] gmail:0123456789ab', cited)
    notebook.write(record, before)
    received = []

    def runner(notebook, items, config, stage):
        received.extend(items)
        return {'changed': [], 'usage': None}

    result = inv.investigate(root, record, 'Vern', ['vern.chan@unsw.edu.au'], days=3,
                             clients={}, subscriptions={}, runner=runner)
    mail = {i['source']: i for i in received if i['source'].startswith(('outlook:', 'gmail:'))}
    assert set(mail) == {source('outlook', 'ask'), source('outlook', 'reply')}
    request, reply = mail[source('outlook', 'ask')], mail[source('outlook', 'reply')]
    assert request['text'] == 'Please approve integration A only.'
    assert request['thread'] == reply['thread'] == 'mail:outlook:scope'
    assert request['comparison_scope'] and not request.get('relationship_scope')
    assert reply['relationship_scope'] and not reply.get('comparison_scope')
    assert request['input_scope'] and request['captured_at'] and request['retained_at']
    assert not any(i.get('role') == 'facts' for i in received)
    assert any('1 previously cited mail source(s)' in line for line in result['coverage'])
    assert not any('it already reflects material before' in line for line in result['coverage'])
    assert notebook.read(record).partition('\nInvestigation:')[0] == before.partition('\nInvestigation:')[0]
    packet = write_evidence(tmp_path / 'comparison', list(mail.values()))
    rendered = '\n'.join(p.read_text() for p in packet['index'].parent.rglob('*.md'))
    assert 'Provider thread: mail:outlook:scope' in rendered and 'Comparison scope:' in rendered


def test_attachment_citation_does_not_mean_carrier_mail_was_read(tmp_path, monkeypatch):
    root = _notebook(tmp_path, 'codex')
    _investigated(root, 'people/vern.md', 1)
    notebook = inv.Notebook(root)
    notebook.write('people/vern.md', notebook.read('people/vern.md').replace(
        'gmail:0123456789ab', 'gmail:0123456789ab:agreement.pdf'))
    carrier = {'source': 'gmail:0123456789ab', 'timestamp': '2026-09-30T09:00:00+00:00',
               'text': 'The terms in this email differ from the attached agreement.'}
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: ([carrier], ['gmail: 1 bodies read']))
    received = []
    inv.investigate(root, 'people/vern.md', 'Vern', ['vern'], days=3, clients={}, subscriptions={},
                    runner=lambda notebook, items, config, stage: received.extend(items) or {'changed': []})
    assert carrier in received


@pytest.mark.parametrize('fresh', [[], [{'source': 'outlook:new', 'role': 'attachment', 'thread': 'mail:outlook:t'}],
                                  [{'source': 'codex:new', 'thread': 'mail:outlook:t'}],
                                  [{'source': 'outlook:new', 'thread': ''}]])
def test_comparison_needs_new_threaded_mail_not_attachment_or_chat(tmp_path, monkeypatch, fresh):
    monkeypatch.setattr('connectonion.rem.mail_archive.person_material',
                        lambda *a, **kw: pytest.fail('no archive reread without new threaded mail'))
    assert inv._mail_comparison(tmp_path, 'people/vern.md', [], [], fresh, {'outlook:old'}, {}) == []


def test_comparison_preserves_context_scope_owner_filter_and_unsubscribe(tmp_path, monkeypatch):
    old = [{'source': 'outlook:other', 'role': 'other', 'thread': 'mail:outlook:t',
            'relationship_scope': 'Not this person’s statement or contact.'},
           {'source': 'outlook:own', 'role': 'user', 'thread': 'mail:outlook:t'}]
    monkeypatch.setattr('connectonion.rem.mail_archive.person_material', lambda *a, **kw: ({'outlook': old}, None, None))
    fresh = [{'source': 'outlook:new', 'role': 'user', 'thread': 'mail:outlook:t'}]
    cited = {i['source'] for i in old}
    comparison = inv._mail_comparison(tmp_path, 'people/vern.md', [], [], fresh, cited, {})
    assert comparison[0]['relationship_scope'] == old[0]['relationship_scope']
    own = inv._mail_comparison(tmp_path, 'people/me.md', [], [], fresh, cited, {}, sent_only=True)
    assert [i['source'] for i in own] == ['outlook:own']
    assert inv._mail_comparison(tmp_path, 'people/vern.md', [], [], fresh, cited,
                                {'outlook': {'unsubscribed': True}}) == []


def test_a_project_s_file_list_alone_is_not_new_material_for_a_page_investigated_before(tmp_path, monkeypatch):
    """A file list is not new when its captured contents are already represented."""
    root = _notebook(tmp_path, 'codex')
    folder = tmp_path / 'work' / 'tide'
    folder.mkdir(parents=True)
    (folder / 'README.md').write_text('# Tide\n')
    inv.Notebook(root).stub_project('projects/tide.md', 'Tide', [str(folder)])
    _investigated(root, 'projects/tide.md', 5)
    from connectonion.rem.project_pages import repository_snapshots
    source = repository_snapshots(inv.project_file_texts([str(folder / 'README.md')]))[0]['source']
    notebook = inv.Notebook(root)
    notebook.write('projects/tide.md', notebook.read('projects/tide.md').replace('gmail:0123456789ab', source))
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: ([], ['codex: 0 sessions in window']))
    with pytest.raises(inv.NothingNew):
        inv.investigate(root, 'projects/tide.md', 'Tide', [str(folder)], days=6, clients={}, subscriptions={},
                        runner=lambda *a, **kw: pytest.fail('no model call on the file list alone'))


def test_a_project_never_investigated_is_still_read_from_its_files(tmp_path, monkeypatch):
    root = _notebook(tmp_path, 'codex')
    folder = tmp_path / 'work' / 'tide'
    folder.mkdir(parents=True)
    (folder / 'README.md').write_text('# Tide\n')
    inv.Notebook(root).stub_project('projects/tide.md', 'Tide', [str(folder)])
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: ([], ['codex: 0 sessions in window']))
    called = []
    inv.investigate(root, 'projects/tide.md', 'Tide', [str(folder)], days=150, clients={}, subscriptions={},
                    runner=lambda *a, **kw: called.append(1) or {'changed': [], 'usage': None})
    assert called == [1]


def test_a_person_with_nothing_new_leaves_the_update_queue(tmp_path, monkeypatch):
    """Without a record of the empty pass the same person was gathered again on every run."""
    from datetime import datetime, timezone
    from connectonion.rem import people_pages
    from connectonion.rem.files import state_path, write_json
    root = _notebook(tmp_path, 'codex')
    _investigated(root, 'people/vern.md', 3)
    write_json(state_path(root, 'people/activity.json'), {'people/vern.md': datetime.now(timezone.utc).isoformat()})
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: ([], ['gmail: 0 matched']))
    row = next(r for r in people_pages.queue(root) if r['record'] == 'people/vern.md')
    assert row['mode'] == 'update'
    with pytest.raises(inv.NothingNew):
        people_pages.investigate_person(root, row, clients={}, subscriptions={})
    assert 'people/vern.md' not in {r['record'] for r in people_pages.queue(root)}


# ------------------------------------------------ #2041: a refused page waits for newer material


def _refusing(*a, **kw):
    from connectonion.rem.runner import RunFailed
    raise RunFailed("Candidate rejected, kept at x: Page is 20,493 characters (was 18,730), over the 20,000 limit",
                    {'input_tokens': 643_000})


def test_a_refused_investigation_is_not_retried_on_the_same_material(tmp_path, monkeypatch):
    """1.9.0a7: Ody Zhou's page was refused at 20,493 characters (643k tokens),
    stayed first in the queue with the same window, and the next run re-read
    the same mail for 933k more."""
    from connectonion.rem.runner import RunFailed
    root = _notebook(tmp_path, 'codex')
    mail = {'source': 'gmail:aaa', 'timestamp': '2026-09-30T09:00:00+00:00', 'text': 'Ody wrote.'}
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: ([mail], ['gmail: 1 matched']))
    args = dict(days=4, clients={}, subscriptions={})
    with pytest.raises(RunFailed):
        inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], runner=_refusing, **args)
    with pytest.raises(inv.NothingNew) as caught:
        inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], **args,
                        runner=lambda *a, **kw: pytest.fail('no model call for material already refused'))
    assert 'waits for newer material' in str(caught.value) and '20,000 limit' in str(caught.value)


def test_newer_material_after_a_refusal_runs_again_and_clears_it(tmp_path, monkeypatch):
    from connectonion.rem.runner import RunFailed
    root = _notebook(tmp_path, 'codex')
    old = {'source': 'gmail:aaa', 'timestamp': '2026-09-30T09:00:00+00:00', 'text': 'Ody wrote.'}
    new = {'source': 'gmail:bbb', 'timestamp': '2026-10-01T09:00:00+00:00', 'text': 'Ody wrote again.'}
    gathered = [[old]]
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: (gathered[0], ['gmail']))
    args = dict(days=4, clients={}, subscriptions={})
    with pytest.raises(RunFailed):
        inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], runner=_refusing, **args)
    gathered[0] = [old, new]
    called = []
    inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], **args,
                    runner=lambda *a, **kw: called.append(1) or {'changed': [], 'usage': None})
    assert called == [1] and inv.refused_for(root, 'people/vern.md') == {}


def test_a_failure_that_is_not_a_refusal_is_retried(tmp_path, monkeypatch):
    """A timeout or a crashed harness says nothing about the material."""
    from connectonion.rem.runner import RunFailed
    root = _notebook(tmp_path, 'codex')
    mail = {'source': 'gmail:aaa', 'timestamp': '2026-09-30T09:00:00+00:00', 'text': 'Ody wrote.'}
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: ([mail], ['gmail']))

    def timing_out(*a, **kw):
        raise RunFailed('Runner timed out after 1800 seconds', None)
    with pytest.raises(RunFailed):
        inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], days=4, clients={}, subscriptions={},
                        runner=timing_out)
    assert inv.refused_for(root, 'people/vern.md') == {}


def test_a_quick_pass_reports_coverage_limits_in_the_reply_not_on_the_page(tmp_path, monkeypatch):
    """#1975: coverage stays off the page; the runner records it and the model says it in its reply."""
    root = _notebook(tmp_path, 'codex')
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: (
        [{'source': 'gmail:1', 'role': 'other', 'timestamp': '2026-09-01', 'text': 'Vern wrote.'}], ['gmail: 1']))
    received = []
    inv.investigate(root, 'people/vern.md', 'Vern Chan', ['vern'], days=7, clients={}, subscriptions={}, quick=True,
                    runner=lambda notebook, items, config, stage: received.extend(items) or
                    {'changed': [], 'usage': None})
    scope = next(item for item in received if item['role'] == 'quick-first-pass')['text']
    assert 'Uncertainties' not in scope and 'final reply' in scope
    from connectonion.rem.runner import task_prompt
    prompt = task_prompt(tmp_path, received, 'investigate')
    assert 'Search the evidence index and relevant local archives' in prompt


def test_investigate_me_marks_the_page_as_the_owners_and_drops_the_how_the_user_writes_heading(tmp_path, monkeypatch):
    """#2008: the owner's page followed the person template ("How the user writes
    to them: Not applicable"); `investigate me` now hands it over as the owner's."""
    from connectonion.rem.page_review import validate
    root = _notebook(tmp_path, "codex")
    monkeypatch.setattr(inv, "gather", lambda *args, **kwargs: ([
        {"source": "codex:s:1", "role": "user", "timestamp": "2026-09-01", "text": "ship the reader"}],
        ["codex: 1 messages in window, 1 related to subject, 1 read"]))
    seen = []

    def runner(notebook, items, config, stage):
        seen.extend(items)
        return {"changed": []}

    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=5, clients={}, subscriptions={},
                    runner=runner, sent_only=True)
    page = next(item for item in seen if item["role"] == "page")
    assert page["owner"] is True
    assert "## How the user writes to them" in page["text"]   # an older page keeps it until rewritten
    inv.Notebook(root).stub_person("people/ody.md", "Ody", ["ody@x.example"], email="ody@x.example")
    seen.clear()
    inv.investigate(root, "people/ody.md", "Ody", ["ody"], days=5, clients={}, subscriptions={}, runner=runner)
    assert "owner" not in next(item for item in seen if item["role"] == "page")
    written = inv.Notebook(root).read("people/vern.md").replace("## How the user writes to them\n- Unknown — not "
                                                                "investigated yet\n\n", "")
    assert not any("How the user writes" in e for e in validate("people/vern.md", written, written, [], owner=True))
    assert any("How the user writes" in e for e in validate("people/vern.md", written, written, []))


def test_a_gmail_date_with_no_timezone_is_read_as_utc():
    """#2013: a `-0000` Date parsed to a naive time, and co rem refused it."""
    from connectonion.useful_tools.gmail import _iso_date

    assert _iso_date("Thu, 09 Jul 2026 01:50:17 -0000", "2026-07-01T00:00:00+00:00") == "2026-07-09T01:50:17+00:00"
    assert _iso_date("Thu, 09 Jul 2026 11:50:17 +1000", "x") == "2026-07-09T11:50:17+10:00"
    assert _iso_date("not a date", "2026-07-01T00:00:00+00:00") == "2026-07-01T00:00:00+00:00"


def test_one_saved_mail_with_an_unreadable_date_is_skipped_not_the_whole_run(tmp_path, monkeypatch):
    """#2013: one naive date in the init archive stopped `investigate me` and init's
    first page with "Source contains an invalid timestamp"."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    good = {"_mail_id": "a", "role": "user", "speaker": "me@x.y", "timestamp": (now - timedelta(days=2)).isoformat(),
            "text": "kept", "source": "gmail:a"}
    naive = {**good, "_mail_id": "b", "timestamp": "2026-07-09T01:50:17", "text": "undated", "source": "gmail:b"}
    monkeypatch.setattr("connectonion.rem.mail_archive.person_material",
                        lambda root, record, *, handles=(): ({"gmail": [good, naive]}, now - timedelta(days=30), now))

    items, coverage = inv.gather("Me", ["me@x.y"], days=7, clients={}, subscriptions={},
                                 archive_root=tmp_path, record="people/me.md")

    assert [i["text"] for i in items] == ["kept"]
    assert "gmail: 1 saved message(s) skipped for an unreadable date" in coverage


# ------------------------------------------- the 1.9.0a6 acceptance run (#2027)


def test_the_owners_turn_is_handed_the_recent_projects_dated_and_a_persons_is_not(tmp_path, monkeypatch):
    """#2027: of 1,477 session messages read, 3 were cited, and the owner page's
    `Who they are` named no project of the last weeks."""
    from connectonion.rem.files import state_path, write_json
    root = _notebook(tmp_path, "codex")
    write_json(state_path(root, "map.json"), {"started": "2026-09-30T04:45:06+00:00", "projects": [
        {"name": "browser", "record": "projects/browser.md", "sessions": 17, "first": "2026-08-30",
         "last": "2026-09-27"},
        {"name": "connectonion", "record": "projects/connectonion.md", "sessions": 158, "first": "2026-09-07",
         "last": "2026-09-30"},
        {"name": "old-thing", "record": "projects/old.md", "sessions": 40, "first": "2026-06-01",
         "last": "2026-07-01"}]})
    monkeypatch.setattr(inv, "gather", lambda *args, **kwargs: ([
        {"source": "codex:s:1", "role": "user", "project": "/work/connectonion",
         "timestamp": "2026-09-01", "text": "Decide how the reader presents a verified change."}], ["codex: 1"]))
    seen = []

    def runner(notebook, items, config, stage):
        seen.extend(items)
        return {"changed": []}

    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=5, clients={}, subscriptions={},
                    runner=runner, sent_only=True)
    recent = next(item for item in seen if item["role"] == "recent-projects")["text"]
    lines = [line for line in recent.splitlines() if line.startswith("- ")]
    assert lines == ["- connectonion (projects/connectonion.md): 158 sessions, 2026-09-07 to 2026-09-30",
                     "- browser (projects/browser.md): 17 sessions, 2026-08-30 to 2026-09-27"]
    assert "old-thing" not in recent and "working on now" in recent
    assert "codex:s:1" in next(item for item in seen if item["role"] == "owner-work-evidence")["text"]
    seen.clear()
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=5, clients={}, subscriptions={},
                    runner=runner)
    assert not any(item["role"] == "recent-projects" for item in seen)
    assert not any(item["role"] == "owner-work-evidence" for item in seen)


def test_a_daily_run_says_each_pages_outcome_and_records_its_stage_and_seconds(tmp_path, co_ai, monkeypatch):
    """#2044: outcomes appeared only in a 200-line dump at the end, and "Seconds: Unknown".
    #2043: a daily run's tokens had no stage in logs --usage."""
    from connectonion.rem.daily import outcome_line, run_daily
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: kind == "outlook")
    monkeypatch.setattr("connectonion.rem.daily.mail_client", lambda kind, **kw: Quiet())
    root = _pinned_notebook(tmp_path, "codex")
    said = []

    def person(root, page, **kw):
        return {"usage": {"input_tokens": 1200}, "changed": [page["path"]]}
    result = run_daily(root, scheduled=True, say=said.append, person_one=person,
                       maintain=lambda root, scheduled: {"outcome": "no_change", "items": 0, "changed": []})
    run = result["run"]
    assert any(line.startswith("Updated people/") and line.endswith("(accepted)") for line in said), said
    assert run["usage_by_stage"] == {"investigate": {"input_tokens": 1200}}
    assert isinstance(run["seconds"], float)
    refused = outcome_line({"page": "people/y.md", "outcome": "refused",
                            "why": "Candidate rejected: over 20,000 characters " + "x " * 200})
    assert refused.startswith("Refused people/y.md: Candidate rejected: over 20,000 characters")
    assert len(refused) < 200 and refused.endswith("…")
    assert outcome_line({"page": "people/z.md", "outcome": "nothing_new", "why": "long"}) == "Nothing new for people/z.md"

def test_one_run_reads_the_sessions_once_for_every_subject(tmp_path, monkeypatch):
    """A real first run (2026-10-01) re-read 1,300 session files for every
    person; six threads under one GIL took 13 minutes a person. The window's
    sessions are read once and each subject picks its own from them."""
    from connectonion.rem.source import Batch
    seen = []

    def collect(sub, cursor, *limits):
        seen.append(cursor)
        if not cursor:
            return Batch([{"text": "odi accepted the terms", "timestamp": "2026-09-01", "source": "codex:1"}],
                         {"offset": 40})
        if cursor == {"offset": 40}:
            return Batch([{"text": "vern booked the room", "timestamp": "2026-09-02", "source": "codex:2"}],
                         {"offset": 80})
        return Batch([], cursor)

    monkeypatch.setattr(inv, "collect", collect)
    subs = {"codex": {"kind": "codex", "root": str(tmp_path)}}
    ody, _ = inv.gather("Ody Zhou", ["odi"], days=30, clients={}, subscriptions=subs)
    vern, coverage = inv.gather("Vern Chan", ["vern"], days=30, clients={}, subscriptions=subs)
    assert [i["source"] for i in ody] == ["codex:1"] and [i["source"] for i in vern] == ["codex:2"]
    assert seen == [{}, {"offset": 40}, {"offset": 80}]
    assert "2 messages" in next(line for line in coverage if line.startswith("codex"))


def test_historical_person_gather_keeps_legacy_and_current_codex_messages(tmp_path, monkeypatch):
    legacy = [{"id": "legacy", "timestamp": "2025-11-04T15:24:50Z", "instructions": "Harness"},
              {"type": "message", "id": "old-user", "role": "user",
               "content": [{"type": "input_text", "text": "Vern asked about the placement"}]}]
    current = [{"type": "session_meta", "payload": {"id": "current", "cwd": "/work/demo"}},
               {"type": "response_item", "timestamp": "2026-09-07T05:00:00Z",
                "payload": {"type": "message", "role": "user",
                            "content": [{"type": "input_text", "text": "Vern needs revised scope"}]}}]
    current += [{"type": "response_item", "timestamp": "2026-09-07T05:00:00Z",
                 "payload": {"type": "message", "role": "user", "content": [
                     {"type": "input_text", "text": f"Vern follow-up {index}"}]}} for index in range(450)]
    current.append({"type": "response_item", "timestamp": "2026-09-07T05:00:00Z",
                    "payload": {"type": "message", "role": "user", "future_field": True,
                                "content": [{"type": "input_text", "text": "Vern hidden by unknown format"}]}})
    for name, rows in (("legacy", legacy), ("current", current)):
        (tmp_path / f"rollout-{name}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    calls, original = [], inv.collect
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(inv, 'collect', counted)
    items, coverage = inv.gather("Vern", ["Vern"], days=730, clients={}, subscriptions={
        "codex": {"kind": "codex", "root": str(tmp_path)}})
    assert {item["text"] for item in items} == {"Vern asked about the placement", "Vern needs revised scope",
                                               *(f"Vern follow-up {index}" for index in range(450))}
    assert len(calls) <= 3, "full-window gathering must not repeatedly re-hash hundreds of tiny batches"
    assert any("1 related legacy message(s)" in line and "individual message times" in line for line in coverage)
    assert any("1 user-slot message(s) in an unfamiliar format were not read" in line for line in coverage)
    assert not any("unreadable" in line for line in coverage)


@pytest.mark.parametrize('tier', ['agent', 'summary'])
def test_file_only_investigation_keeps_exact_cited_snapshot_after_live_file_changes(tmp_path, monkeypatch, tier):
    from connectonion.rem import project_pages
    from connectonion.rem.reader_model import cited_context
    root = _notebook(tmp_path, 'codex')
    repo = tmp_path / 'project'
    repo.mkdir()
    original = '# Tide\n' + 'a' * 300000 + '\nThe full source ends here.'
    live = repo / 'README.md'
    live.write_text(original)
    notebook = inv.Notebook(root)
    record = 'projects/tide.md'
    notebook.stub_project(record, 'Tide', [str(repo)])
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: ([], ['codex: 0 sessions']))
    monkeypatch.setattr('connectonion.rem.tier.current', lambda *a: tier)
    seen = {}

    def runner(book, items, config, stage):
        index = next((i for i in items if i['role'] == 'evidence-index'), None)
        if tier == 'agent':
            assert index is not None
            source = next(s for s in index['sources'] if s.startswith('project-source:'))
            material = '\n'.join(p.read_text() for p in Path(index['file']).parent.rglob('*.md'))
            assert 'The full source ends here.' in material
        else:
            item = next(i for i in items if i['role'] == 'project-file')
            source = item['source']
            assert item['text'].endswith('[truncated]') and 'The full source ends here.' not in item['text']
        seen['source'] = source
        live.write_text('# Tide\nChanged while the page is written.')
        page = book.read(record).replace('- (none yet)', '- [1] ' + source)
        book.write(record, page)
        return {'changed': [record], 'usage': None}

    inv.investigate(root, record, 'Tide', [str(repo)], days=30, clients={}, subscriptions={}, runner=runner)
    saved = project_pages.repository_context(root, seen['source'])
    expected = original if tier == 'agent' else original[:2000] + '\n[truncated]'
    assert saved and saved['excerpt'] == expected.strip()[:project_pages.REPOSITORY_EXCERPT_CHARS]
    retained = next((root / '.state/project-sources').glob('*.json'))
    body = json.loads(retained.read_text())
    assert body['text'] == expected and body['origin'] == 'file:' + str(live)
    assert body['captured_at'] and body['file_modified_at']
    assert retained.stat().st_mode & 0o777 == 0o600
    assert cited_context(root, [{'text': '- [1] ' + seen['source']}])[seen['source']]['excerpt'] == saved['excerpt']
    assert not list((root / '.state/evidence').rglob('*.md'))


def test_explicit_project_keeps_only_cited_live_session_input_for_reader(tmp_path, monkeypatch):
    from connectonion.rem.reader_model import cited_context
    root = _notebook(tmp_path, 'codex')
    repo = tmp_path / 'tide'
    repo.mkdir()
    record = 'projects/tide.md'
    notebook = inv.Notebook(root)
    notebook.stub_project(record, 'Tide', [str(repo)])
    cited = 'claude-code:session-123:42'
    other = 'claude-code:session-123:84'
    long_input = 'Background. ' * 80 + 'The Tide release still needs a hook fix.'
    messages = [{'role': 'user', 'source': source, 'timestamp': '2026-10-01T12:00:00+00:00',
                 'project': str(repo), 'text': body} for source, body in
                [(cited, long_input),
                 (other, 'Unrelated session input.')]]
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: (messages, ['claude-code: 2 sessions']))

    def runner(book, items, config, stage):
        book.write(record, book.read(record) + f'\n- [1] {cited} — 2026-10-01\n')
        return {'changed': [record], 'usage': None}

    inv.investigate(root, record, 'Tide', [str(repo)], days=30, clients={}, subscriptions={}, runner=runner)
    contexts = cited_context(root, [{'text': f'- [1] {cited} — 2026-10-01'}])
    assert contexts[cited]['excerpt'] == messages[0]['text']
    assert 'Your input only' in contexts[cited]['input_scope']
    assert len(list((root / '.state/session-sources').glob('*.json'))) == 1


def test_file_inventory_includes_package_manifest_without_all_json_data(tmp_path):
    (tmp_path / 'package.json').write_text('{"name":"tide"}')
    (tmp_path / 'customers.json').write_text('{"private":"data"}')
    page = '# Tide\n\n## Paths\n- ' + str(tmp_path)
    assert inv.project_file_inventory(page) == [str(tmp_path / 'package.json')]


@pytest.mark.parametrize('outcome', ['unchanged', 'rejected', 'digest'])
def test_file_snapshot_retention_follows_the_successful_run_and_keeps_original_before_digest(tmp_path, monkeypatch, outcome):
    root = _notebook(tmp_path, 'codex')
    folder = tmp_path / 'work' / 'tide'
    folder.mkdir(parents=True)
    (folder / 'README.md').write_text('# Tide\nThe original README body.')
    (folder / 'uncited.md').write_text('This was supplied but not cited.')
    record = 'projects/tide.md'
    notebook = inv.Notebook(root)
    notebook.stub_project(record, 'Tide', [str(folder)])
    monkeypatch.setattr(inv, 'gather', lambda *a, **kw: ([], ['codex: 0 sessions']))
    seen = {}
    if outcome == 'digest':
        monkeypatch.setattr('connectonion.rem.tier.current', lambda *a: 'summary')
        from connectonion.rem.runner import instructions
        overhead = len(instructions('investigate', page_kind='project')) + len(notebook.read(record)) + 4000
        monkeypatch.setattr('connectonion.rem.runner.INLINE_LIMIT', overhead + 1500)
        (folder / 'README.md').write_text('# Tide\nThe original README body.' + 'a' * 1900)
        (folder / 'uncited.md').write_text('b' * 1900)

    def extractor(items, config, kind):
        source = next(i['source'] for i in items if i.get('origin') == 'file:' + str(folder / 'README.md'))
        seen['source'] = source
        return {'notes': 'A summary-only claim [' + source + ']', 'usage': None}

    def runner(book, items, config, stage):
        if outcome == 'rejected':
            raise inv.RemError('candidate rejected')
        if outcome == 'digest':
            assert any('summary-only' in i['text'] for i in items)
            book.write(record, book.read(record).replace('- (none yet)', '- [1] ' + seen['source']))
            return {'changed': [record], 'usage': None}
        return {'changed': [], 'usage': None}

    if outcome == 'rejected':
        with pytest.raises(inv.RemError, match='rejected'):
            inv.investigate(root, record, 'Tide', [str(folder)], days=30, clients={}, subscriptions={}, runner=runner)
        with pytest.raises(inv.NothingNew):
            inv.investigate(root, record, 'Tide', [str(folder)], days=30, clients={}, subscriptions={},
                            runner=lambda *a, **kw: pytest.fail('same rejected file material'))
    else:
        inv.investigate(root, record, 'Tide', [str(folder)], days=30, clients={}, subscriptions={}, runner=runner,
                        extractor=extractor)
    saved = list((root / '.state/project-sources').glob('*.json'))
    if outcome == 'digest':
        assert len(saved) == 1
        body = json.loads(saved[0].read_text())
        assert 'original README body' in body['text'] and 'summary-only' not in body['text']
    else:
        assert saved == []
    if outcome == 'unchanged':
        # Even uncited, previously supplied files must not trigger repeated paid investigations.
        with pytest.raises(inv.NothingNew):
            inv.investigate(root, record, 'Tide', [str(folder)], days=30, clients={}, subscriptions={},
                            runner=lambda *a, **kw: pytest.fail('identical supplied material'))
        (folder / 'README.md').write_text('# Tide\nChanged without any new session.')
        inv.investigate(root, record, 'Tide', [str(folder)], days=30, clients={}, subscriptions={}, runner=runner)
