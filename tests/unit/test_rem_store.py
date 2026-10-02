"""co rem's SQLite index beside the pages (#2067): built from the files, read by the views.

The fixture is a small notebook with fake mail and a fake coding session: two
correspondents, the owner, an organisation, a project, an archived body and an
investigation run. Every date is written into the files; nothing reads the clock.
"""

import json
import os
import sqlite3

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json

OWNER = "me@example.org"


def _jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _person_row(record, address, mails, last, **extra):
    return {"record": record, "classification": "unassessed", "address": address, "name": record,
            "mails": mails, "sent": 1, "received": mails - 1, "first": "2026-07-01", "last": last,
            "addresses": [address], "needs_review": False, **extra}


def _pages(root):
    notebook = Notebook(root)
    notebook.stub_person("people/ody.md", "Ody Zhou", ["ody@acme.test"], email="ody@acme.test")
    page = notebook.read("people/ody.md").replace("- Company: Unknown", "- Company: Acme [2]").replace(
        "- Phone: Unknown", "- Phone: +61 400 000 000 [3]").replace(
        "## Open threads\n- Unknown — not investigated yet",
        "## Open threads\n- Ody owes the contract [4]\n- We owe the invoice [5]")
    page = page.replace("not investigated yet", "investigated 2026-09-27")
    page = page.replace("## Who they are\n", "## Who they are\nPartner on [Atlas](../projects/atlas.md). "
                        "Last contact: 2026-09-21. [1]\n")
    notebook.write("people/ody.md", page)
    notebook.stub_person("people/tam.md", "Tamara", ["tam@uni.test"], email="tam@uni.test")
    notebook.stub_person("people/me.md", "Me", [OWNER], email=OWNER)
    notebook.stub_org("orgs/acme.md", "Acme", ["acme.test"], ["people/ody.md"])
    notebook.stub_project("projects/atlas.md", "Atlas", ["/repo/atlas"])
    return notebook


def _map(root):
    write_json(state_path(root, "map.json"), {
        "phase": "mapped", "owner": {"record": "people/me.md", "addresses": [OWNER]},
        "people": [{"record": "people/me.md", "classification": "account owner"},
                   _person_row("people/ody.md", "ody@acme.test", 3, "2026-09-20"),
                   _person_row("people/tam.md", "tam@uni.test", 1, "2026-08-02")],
        "orgs": [{"record": "orgs/acme.md", "domain": "acme.test", "domains": ["acme.test"],
                  "people": ["people/ody.md"], "classification": "unassessed"}],
        "projects": [{"record": "projects/atlas.md", "name": "Atlas", "paths": ["/repo/atlas"],
                      "worktrees": [], "sessions": 2, "first": "2026-08-01", "last": "2026-09-19"}],
        "automated_correspondents": []})


def _mail(root):
    from connectonion.rem.mail_archive import message_path
    rows = [
        {"type": "mail", "source": "gmail", "id": "m1", "date": "2026-09-18T09:00:00+00:00",
         "from": "Ody Zhou <ody@acme.test>", "to": [OWNER], "cc": [], "subject": "Contract"},
        {"type": "mail", "source": "gmail", "id": "m2", "date": "2026-09-19T09:00:00+00:00",
         "from": OWNER, "to": ["ody@acme.test"], "cc": ["tam@uni.test"], "subject": "Re: Contract"},
        {"type": "mail", "source": "gmail", "id": "m3", "date": "2026-09-20T09:00:00+00:00",
         "from": "ody@acme.test", "to": [OWNER], "cc": [], "subject": "RE: Fwd: contract"},
        {"type": "mail", "source": "gmail", "id": "m4", "date": "2026-08-02T09:00:00+00:00",
         "from": "tam@uni.test", "to": [OWNER], "cc": [], "subject": "Contract"},
        {"type": "session", "source": "codex", "path": "/s/1.jsonl", "cwd": "/repo/atlas",
         "modified": "2026-09-19T00:00:00+00:00"},
    ]
    _jsonl(state_path(root, "source-inventory.jsonl"), rows)
    path = message_path(root, "gmail", "m1")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, {"provider": "gmail", "id": "m1", "subject": "Contract", "body": "Please sign."})


def _sessions(root):
    folder = state_path(root, "projects/atlas")
    _jsonl(folder / "messages.jsonl", [
        {"source": "codex:s1:2", "tool": "codex", "timestamp": "2026-09-19T10:05:00+00:00",
         "cwd": "/repo/atlas", "text": "now the tests"},
        {"source": "codex:s1:1", "tool": "codex", "timestamp": "2026-09-19T10:00:00+00:00",
         "cwd": "/repo/atlas", "text": "build the parser"}])
    write_json(folder / "state.json", {"record": "projects/atlas.md", "sessions": 1})


def _runs(root):
    write_json(state_path(root, "runs/run_1.json"), {
        "id": "run_1", "record": "people/ody.md", "stage": "write", "outcome": "written", "model": "m",
        "started_at": "2026-09-27T01:00:00+00:00", "finished_at": "2026-09-27T01:05:00+00:00",
        "seconds": 300.0, "usage": {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 50}})


def notebook(root):
    prepare(root)
    _pages(root)
    _map(root)
    _mail(root)
    _sessions(root)
    _runs(root)
    return root


def test_the_people_table_has_the_crm_columns_and_the_census_count(tmp_path):
    from connectonion.rem import store
    from connectonion.rem.census import counts
    root = notebook(tmp_path)
    store.refresh(root)
    rows = store.people_table(root)
    assert len(rows) == counts(root)["people"]["mapped"]
    ody = next(row for row in rows if row["record"] == "people/ody.md")
    assert ody["name"] == "Ody Zhou" and ody["emails"] == ["ody@acme.test"]
    assert (ody["company"], ody["phone"], ody["role"]) == ("Acme", "+61 400 000 000", "")   # cited, Unknown is empty
    assert ody["mails"] == 3 and ody["first_contact"] == "2026-07-01"
    assert ody["last_contact"] == "2026-09-21"          # the page's own, later than the map's 2026-09-20
    assert ody["open_threads"] == 2 and ody["written"] and ody["listed"]
    assert [row["record"] for row in rows][0] == "people/ody.md"        # most recent contact first
    assert os.stat(state_path(root, "rem.db")).st_mode & 0o777 == 0o600


def test_a_facts_block_wins_and_every_labelled_fact_is_kept(tmp_path):
    from connectonion.rem import store
    root = notebook(tmp_path)
    pages = Notebook(root)
    # A stub opens on `## Facts` since #2068; a legacy `## Contact` below it loses to it.
    pages.write("people/tam.md", pages.read("people/tam.md").replace("- Role: Unknown", "- Role: Lecturer [1]")
                .replace("- Location: Unknown", "- Location: Sydney [2]\n- Pronouns: she/her [3]")
                .replace("## Insight", "## Contact\n- Role: Tutor [4]\n\n## Insight"))
    store.refresh(root)
    tam = store.person(root, "people/tam.md")
    assert tam["role"] == "Lecturer" and tam["location"] == "Sydney"
    assert tam["facts"]["Pronouns"] == "she/her"           # a field with no column yet is still readable
    assert tam["facts"]["Email"] == "tam@uni.test"


def test_filters_and_sorting(tmp_path):
    from connectonion.rem import store
    root = notebook(tmp_path)
    store.refresh(root)
    assert [r["record"] for r in store.people_table(root, company="acme")] == ["people/ody.md"]
    assert [r["record"] for r in store.people_table(root, open_only=True)] == ["people/ody.md"]
    assert [r["record"] for r in store.people_table(root, query="tamara")] == ["people/tam.md"]
    recent = store.people_table(root, recent_days=10, today="2026-09-25")
    assert [r["record"] for r in recent] == ["people/ody.md"]
    by_name = store.people_table(root, sort="name", descending=False)
    assert [r["name"] for r in by_name] == sorted(r["name"] for r in by_name)


def test_a_mail_thread_reads_in_order_and_bodies_load_on_demand(tmp_path):
    from connectonion.rem import store
    root = notebook(tmp_path)
    store.refresh(root)
    contract = store.threads(root, "people/ody.md")[0]
    messages = store.thread(root, contract["thread"])
    assert [m["id"] for m in messages] == ["gmail:m1", "gmail:m2", "gmail:m3"]   # Re:/Fwd: folded, time order
    assert "body" not in messages[0]
    loaded = store.thread(root, contract["thread"], bodies=True)
    assert loaded[0]["body"] == "Please sign." and loaded[1]["body"] is None      # m2 was never archived
    # The same subject with a different person is a different conversation.
    assert "gmail:m4" not in [m["id"] for m in messages]


def test_a_coding_session_is_a_thread_too(tmp_path):
    from connectonion.rem import store
    root = notebook(tmp_path)
    store.refresh(root)
    messages = store.thread(root, "session:codex:s1", bodies=True)
    assert [m["body"] for m in messages] == ["build the parser", "now the tests"]


def test_stale_session_line_never_returns_another_messages_body(tmp_path):
    from connectonion.rem import store
    from connectonion.rem.reader_model import cited_context, cited_conversations
    root = notebook(tmp_path)
    store.refresh(root)
    context = cited_context(root, [{'text': '- [1] codex:s1:1'}])
    assert context['codex:s1:1']['excerpt'] == 'build the parser'
    assert 'Assistant replies and tool results are not included' in context['codex:s1:1']['input_scope']
    conversation = cited_conversations(root, context)['session:codex:s1']
    assert all('does not verify what was completed' in row['input_scope'] for row in conversation['messages'])
    path = state_path(root, 'projects/atlas/messages.jsonl')
    saved = [json.loads(line) for line in path.read_text().splitlines()]
    _jsonl(path, [{'source': 'codex:s1:new', 'text': 'Unrelated earlier input'}, *saved])
    assert all(row['body'] is None for row in store.thread(root, 'session:codex:s1', bodies=True))
    assert cited_context(root, [{'text': '- [1] codex:s1:1'}]) == {}
    assert cited_conversations(root, context) == {}


def test_edges_join_people_to_orgs_and_projects(tmp_path):
    from connectonion.rem import store
    root = notebook(tmp_path)
    store.refresh(root)
    found = {(e["kind"], e["other"]): e for e in store.edges(root, "people/ody.md")}
    assert found[("org", "orgs/acme.md")]["count"] == 3
    assert found[("org", "orgs/acme.md")]["last_contact"] == "2026-09-21"
    assert found[("project", "projects/atlas.md")]["via"] == "page link"
    assert [e["person"] for e in store.edges(root, "orgs/acme.md")] == ["people/ody.md"]
    assert store.person(root, "people/ody.md")["edges"]


def test_runs_carry_their_tokens(tmp_path):
    from connectonion.rem import store
    root = notebook(tmp_path)
    store.refresh(root)
    with sqlite3.connect(state_path(root, "rem.db")) as db:
        assert db.execute("select input_tokens, cached_input_tokens, output_tokens from runs").fetchall() == [
            (1000, 400, 50)]


def _everything(root):
    from connectonion.rem import store
    return (store.people_table(root, include_unlisted=True), store.threads(root, "people/ody.md"),
            store.edges(root, "people/ody.md"))


def test_a_build_is_incremental_and_the_same_from_scratch(tmp_path):
    from connectonion.rem import store
    root = notebook(tmp_path)
    assert set(store.refresh(root)["rebuilt"]) == {"pages", "mail", "sessions", "runs"}
    assert store.refresh(root)["rebuilt"] == []                   # nothing changed, nothing written
    pages = Notebook(root)
    pages.write("people/tam.md", pages.read("people/tam.md").replace("- Role: Unknown", "- Role: Dean"))
    assert store.refresh(root)["rebuilt"] == ["pages"]
    built = _everything(root)
    state_path(root, "rem.db").unlink()
    store.refresh(root)
    assert _everything(root) == built


def test_an_unknown_schema_or_a_broken_file_is_built_again(tmp_path):
    from connectonion.rem import store
    root = notebook(tmp_path)
    store.refresh(root)
    with sqlite3.connect(state_path(root, "rem.db")) as db:
        db.execute("update meta set value = '999' where key = 'schema_version'")
    db.close()
    assert len(store.refresh(root)["rebuilt"]) == 4
    for suffix in ("-wal", "-shm"):
        state_path(root, "rem.db" + suffix).unlink(missing_ok=True)
    state_path(root, "rem.db").write_bytes(b"not a database at all")
    assert len(store.refresh(root)["rebuilt"]) == 4
    assert store.people_table(root)


def test_a_reader_never_creates_or_writes_the_file(tmp_path):
    from connectonion.rem import store
    root = notebook(tmp_path)
    assert store.people_table(root) == [] and store.thread(root, "x") == [] and store.person(root, "p") is None
    assert not state_path(root, "rem.db").exists()


def test_a_failed_build_is_skipped_with_its_reason(tmp_path, monkeypatch, capsys):
    from connectonion.rem import store
    root = notebook(tmp_path)

    def broken(_root):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(store, "refresh", broken)
    assert store.refresh_safely(root) == {"skipped": "OperationalError: disk I/O error"}
    assert "co rem: store skipped: OperationalError: disk I/O error" in capsys.readouterr().err


def test_the_map_builds_the_store_after_tidy(tmp_path):
    from connectonion.rem import store
    from connectonion.rem.map import build_map
    prepare(tmp_path)
    skills = tmp_path / "installed"
    skills.mkdir()
    report = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert "rebuilt" in report["store"]
    assert state_path(tmp_path, "rem.db").is_file()
    assert store.people_table(tmp_path) == []


def test_co_rem_list_people_table_prints_the_crm_columns(tmp_path):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import store
    root = notebook(tmp_path)
    store.refresh(root)
    runner = CliRunner()
    plain = runner.invoke(app, ["rem", "--root", str(root), "list", "people", "--table"])
    assert plain.exit_code == 0, plain.output
    header = plain.output.splitlines()[0]
    for column in ("Name", "Company", "Role", "Email", "Phone", "Last contact", "Mails", "Open", "Status"):
        assert column in header
    assert "Ody Zhou" in plain.output and "Acme" in plain.output and "Next:" in plain.output
    data = json.loads(runner.invoke(app, ["rem", "--root", str(root), "--json", "list", "people", "--table"]).output)
    assert data["data"][0]["record"] == "people/ody.md" and data["data"][0]["company"] == "Acme"


def test_rem_full_gmail_window_defers_headers_until_after_split():
    from connectonion.useful_tools.gmail import Gmail

    gets = []

    class Call:
        def __init__(self, result): self.result = result
        def execute(self, num_retries=0): return self.result

    class Messages:
        def list(self, **kw): return Call({"messages": [{"id": "a"}, {"id": "b"}]})
        def get(self, **kw):
            gets.append(kw["id"])
            return Call({"payload": {"headers": []}})

    class Users:
        def messages(self): return Messages()

    class Service:
        def users(self): return Users()

    gmail = Gmail.__new__(Gmail)
    gmail._get_service = lambda: Service()
    window = gmail.list_between_for_rem("2026-09-01T00:00:00+00:00",
                                        "2026-09-08T00:00:00+00:00", 2)
    assert window == [{"id": "a"}, {"id": "b"}]
    assert gets == []
    gmail.list_between("2026-09-01T00:00:00+00:00", "2026-09-08T00:00:00+00:00", 2)
    assert gets == ["a", "b"]


def test_the_provider_thread_id_reaches_the_inventory(monkeypatch):
    """Gmail's threadId and Graph's conversationId, kept from the listing on (owner's decision, #2067)."""
    from connectonion.rem.source_inventory import SourceInventory
    from connectonion.useful_tools.gmail import Gmail
    from connectonion.useful_tools.outlook import Outlook

    class Call:
        def __init__(self, result): self.result = result
        def execute(self, num_retries=0): return self.result

    class Messages:
        def list(self, **kw): return Call({"messages": [{"id": "a", "threadId": "t-1"}]})
        def get(self, **kw):
            return Call({"id": kw["id"], "snippet": "", "labelIds": [], "payload": {"headers": [
                {"name": "From", "value": "a@x.y"}, {"name": "Subject", "value": "s"},
                {"name": "Date", "value": "Thu, 10 Sep 2026 10:00:00 +0000"}]}})

    class Service:
        def users(self): return type("Users", (), {"messages": lambda self: Messages()})()
    gmail = Gmail.__new__(Gmail)
    gmail._get_service = lambda: Service()
    assert gmail.list_between("2026-09-01T00:00:00+00:00", "2026-09-20T00:00:00+00:00")[0]["thread_id"] == "t-1"
    outlook = Outlook.__new__(Outlook)
    message = {"id": "1", "conversationId": "c-1", "from": {"emailAddress": {"address": "a@x.y", "name": ""}},
               "toRecipients": [], "ccRecipients": [], "subject": "s", "receivedDateTime": "2026-09-10T00:00:00Z",
               "bodyPreview": "", "isRead": True}
    monkeypatch.setattr(outlook, "_request", lambda *a, **k: {"value": [message]}, raising=False)
    row = outlook.list_between("2026-09-01T00:00:00+00:00", "2026-09-20T00:00:00+00:00")[0]
    assert row["thread_id"] == "c-1"
    inventory = SourceInventory.__new__(SourceInventory)
    inventory.records = []
    inventory.mail("outlook", row)
    assert inventory.records[0]["thread"] == "c-1"


def test_a_provider_thread_id_wins_over_the_subject(tmp_path):
    from connectonion.rem import store
    root = notebook(tmp_path)
    path = state_path(root, "source-inventory.jsonl")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["thread"] = rows[3]["thread"] = "T9"      # m1 (Ody) and m4 (Tamara) are one provider thread
    _jsonl(path, rows)
    store.refresh(root)
    assert [m["id"] for m in store.thread(root, "mail:gmail:T9")] == ["gmail:m4", "gmail:m1"]
    contract = [t["thread"] for t in store.threads(root, "people/ody.md")]
    assert "mail:gmail:T9" in contract and len(contract) == 2   # m2, m3 have no id yet: still the subject hash


def test_the_sync_summary_says_the_index_in_the_status_layout():
    from rich.text import Text
    from connectonion.cli.commands.rem_look import COLUMN
    from connectonion.cli.commands.rem_output import sync_summary

    def plain(store):
        drawn = sync_summary({"items": 2, "changed": [], "outcome": "completed", "store": store})
        return [line for line in Text.from_markup(drawn).plain.splitlines() if "Index" in line or "→" in line]
    built = plain({"rebuilt": ["pages"], "rows": {"people": 330, "messages": 4057}})
    assert built == ["Index" + " " * (COLUMN - 5) + "330 people · 4,057 messages"]
    skipped = plain({"skipped": "OperationalError: disk I/O error"})
    assert skipped[0].startswith("Index" + " " * (COLUMN - 5) + "✗ not updated: OperationalError")
    assert skipped[1] == " " * COLUMN + "→ co rem sync"


def test_the_table_before_any_build_says_how_to_make_one(tmp_path):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    root = notebook(tmp_path)
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "list", "people", "--table"])
    assert result.exit_code == 0 and "No people table yet" in result.output
    assert result.output.rstrip().endswith(f"{root} sync")     # the Next line, spelled with this --root
