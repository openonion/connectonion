"""People investigated by an agent searching prepared evidence, recent first (#1943 stage 3, #1850, #1723).

A fake mailbox and a fake runner; never the operator's mail or a model.
"""

import json
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from connectonion.wiki import daily, people_evidence, people_pages
from connectonion.wiki.config import prepare as prepare_notebook
from connectonion.wiki.files import Notebook, WikiError, state_path, write_json
from connectonion.wiki.mail_archive import message_path, person_index_path
from connectonion.wiki.people_evidence import materialize, pending, person_state, prepare, stored
from connectonion.wiki.people_pages import queue, write_page, write_pages
from connectonion.wiki.runner import RunFailed

NOW = datetime.now(timezone.utc)
OWNER = "owner@example.org"
CONFIG = {"runner": "codex", "model": "default"}


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat()


class FakeMail:
    """list_with / list_between / get_email_body in the shapes useful_tools return."""

    def __init__(self, messages):
        self.messages = messages
        self.searches, self.bodies, self.listings = [], [], []

    def _on(self, message, address):
        return address in " ".join([message["from"], *message["to"], *message.get("cc", [])])

    def list_with(self, address, start, end, max_results=1000):
        self.searches.append((address, start, end))
        return [{k: v for k, v in m.items() if k != "body"} for m in self.messages
                if self._on(m, address) and start <= m["date"] < end]

    def list_between(self, start, end, max_results=200):
        self.listings.append((start, end))
        return [{k: v for k, v in m.items() if k != "body"} for m in self.messages if start <= m["date"] < end]

    def get_email_body(self, message_id):
        self.bodies.append(message_id)
        message = next(m for m in self.messages if m["id"] == message_id)
        return f"From: {message['from']}\n--- Email Body ---\n{message['body']}"


def mail(id, sender, to, days, body, subject="Hello", cc=()):
    return {"id": id, "from": sender, "to": list(to), "cc": list(cc), "subject": subject,
            "date": ago(days), "body": body}


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "wiki"
    prepare_notebook(root)
    notebook = Notebook(root)
    people = [("ada", "Ada Lovelace", 2), ("bob", "Bob Stone", 30), ("cy", "Cy Young", 5), ("dee", "Dee Old", 60)]
    rows = []
    for slug, name, days in people:
        notebook.stub_person(f"people/{slug}.md", name, [f"{slug}@example.org"], email=f"{slug}@example.org")
        rows.append({"record": f"people/{slug}.md", "addresses": [f"{slug}@example.org"], "mails": 3,
                     "last": ago(days)[:10], "classification": "unassessed"})
    notebook.stub_person("people/owner.md", "Owner", [OWNER], email=OWNER)
    notebook.stub_person("people/bot.md", "Alerts", ["alerts@example.org"], email="alerts@example.org")
    rows += [{"record": "people/owner.md", "classification": "account owner"},
             {"record": "people/bot.md", "addresses": ["alerts@example.org"], "last": ago(1)[:10],
              "classification": "automated candidate"}]
    write_json(state_path(root, "map.json"), {"owner": {"record": "people/owner.md", "addresses": [OWNER]},
                                              "people": rows, "projects": [], "orgs": []})
    return root


def ada_mail():
    signature = "Kind regards, Ada Lovelace, Head of Data, Harbour Analytics. Direct line +61 2 5550 0142"
    return FakeMail([
        mail("a1", "Ada Lovelace <ada@example.org>", [OWNER], 20, "Priya suggested I write to you. " + signature,
             subject="Introduction"),
        mail("a2", f"Owner <{OWNER}>", ["ada@example.org"], 10, "Happy to talk. Owner", subject="Re: Introduction"),
        mail("a3", "Ada Lovelace <ada@example.org>", [OWNER], 2,
             "Pilot is six weeks, A$12,000. Signed SOW by 3 October.\n\nOn Mon, Owner wrote:\n> Happy to talk.",
             subject="Pilot"),
        mail("x1", "Zed <zed@example.org>", [OWNER], 3, "unrelated"),
    ])


def candidate_writer(seen, *, fact="Ada is Head of Data at Harbour Analytics.", extra=""):
    """A runner that writes the page it was given back, with one cited fact."""
    def run(workdir, prompt, config, stage):
        seen.append(prompt)
        candidate = Path(re.search(r"NEW file (\S+candidate\.md)", prompt)[1])
        page = (candidate.parent / "page.md").read_text()
        source = re.search(r"\b(?:gmail|outlook):[0-9a-f]{12}\b", prompt)[0]
        page = page.replace("## Who they are\n- Unknown — not investigated yet",
                            f"## Who they are\n- {fact} [1]{extra}", 1)
        page = page.replace("## Sources\n- (none yet)", f"## Sources\n- [1] {source} — 2026-09-28", 1)
        candidate.write_text(page)
        return {"outcome": "natural", "usage": {"input_tokens": 1000, "output_tokens": 10}, "result": "ok"}
    return run


# ---------------------------------------------------------------- the script (step 1)


def test_prepare_fetches_only_what_is_missing_and_never_the_owners_mail(root):
    # One body init already saved: reused, not fetched again.
    saved = message_path(root, "gmail", "a1")
    saved.parent.mkdir(parents=True, exist_ok=True)
    write_json(saved, {"provider": "gmail", "id": "a1", "date": ago(20), "from": "Ada <ada@example.org>",
                       "to": [OWNER], "cc": [], "subject": "Introduction", "body": "saved body"})
    index = person_index_path(root, "people/ada.md")
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps({"provider": "gmail", "id": "a1", "date": ago(20),
                                 "message": str(saved.relative_to(root))}) + "\n")
    client = ada_mail()
    report = prepare(root, "people/ada.md", clients={"gmail": client})
    assert [address for address, *_ in client.searches] == ["ada@example.org"]   # never the owner's
    assert sorted(client.bodies) == ["a2", "a3"]
    assert (report["reused"], report["fetched"], report["items"]) == (1, 2, 3)
    assert {row["source"] for row in stored(root, "people/ada.md")} == {
        people_evidence.mail_source("gmail", i) for i in ("a1", "a2", "a3")}
    # The report is counts, never what was said.
    assert "Pilot" not in json.dumps(report) and "A$12,000" not in json.dumps(report)


def test_a_later_prepare_searches_only_since_the_last_one(root):
    client = ada_mail()
    prepare(root, "people/ada.md", clients={"gmail": client}, now=NOW - timedelta(days=1))
    client.searches.clear(), client.bodies.clear()
    prepare(root, "people/ada.md", clients={"gmail": client}, now=NOW)
    start = datetime.fromisoformat(client.searches[0][1])
    assert NOW - timedelta(days=1, hours=2) < start < NOW - timedelta(hours=20)
    assert client.bodies == []   # everything already saved


def test_bodies_fetched_in_one_run_are_bounded_newest_first(root):
    client = ada_mail()
    report = prepare(root, "people/ada.md", clients={"gmail": client}, fetch_limit=1)
    assert client.bodies == ["a3"] and report["not_fetched"] == 2


def test_the_evidence_is_private(root):
    prepare(root, "people/ada.md", clients={"gmail": ada_mail()})
    home = state_path(root, "people/ada")
    assert stat.S_IMODE(state_path(root, "people").stat().st_mode) == 0o700
    assert stat.S_IMODE(home.stat().st_mode) == 0o700
    for name in ("index.jsonl", "state.json"):
        assert stat.S_IMODE((home / name).stat().st_mode) == 0o600, name
    assert stat.S_IMODE(message_path(root, "gmail", "a3").stat().st_mode) == 0o600
    # The index holds references, not bodies.
    assert "six weeks" not in (home / "index.jsonl").read_text()


def test_each_evidence_file_opens_with_what_to_cite(root, tmp_path):
    prepare(root, "people/ada.md", clients={"gmail": ada_mail()})
    rows, mode = pending(root, "people/ada.md")
    out = materialize(root, "people/ada.md", tmp_path / "task", rows)
    files = sorted((tmp_path / "task/evidence/mail").glob("*.md"))
    assert len(files) == 3 and mode == "first"
    newest = files[-1].read_text()
    source = people_evidence.mail_source("gmail", "a3")
    assert newest.startswith(f"### {source} · ") and "Direction: from this person" in newest
    assert "quoted earlier thread below" in newest            # the reply, then the thread, marked
    assert "Direction: from the user to this person" in files[1].read_text()
    assert f"· {source} · mail/" in out["index"] and {i["source"] for i in out["items"]} >= {source}


def test_whatsapp_lines_and_session_mentions_are_found_by_full_name_not_first_name(root, tmp_path):
    home = tmp_path / "wa"
    home.mkdir()
    rows = [{"id": "w1", "chat": "g1@g.us", "at": ago(1), "sender_name": "Ada Lovelace", "text": "see you at 3"},
            {"id": "w2", "chat": "g1@g.us", "at": ago(1), "sender_name": "Ada Other", "text": "not her"}]
    (home / "received.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    project = state_path(root, "projects/tide")
    project.mkdir(parents=True)
    messages = [{"source": "codex:s1:1", "timestamp": ago(1), "text": "Ask Ada Lovelace about the pilot"},
                {"source": "codex:s1:2", "timestamp": ago(1), "text": "ask Ada about lunch"}]
    (project / "messages.jsonl").write_text("".join(json.dumps(m) + "\n" for m in messages))
    subs = {"whatsapp": {"kind": "whatsapp", "root": str(home), "enabled": True, "chats": ["g1@g.us"]}}
    report = prepare(root, "people/ada.md", subscriptions=subs)
    texts = [row.get("text") for row in stored(root, "people/ada.md")]
    assert (report["chats"], report["mentions"]) == (1, 1)
    # "Ada Other" in the chat and "ask Ada about lunch" name a different Ada, or none.
    assert sorted(texts) == ["Ask Ada Lovelace about the pilot", "see you at 3"]


# ---------------------------------------------------------------- order and portions


def test_recent_correspondents_come_first_then_older_newest_first(root):
    rows = queue(root)
    assert [row["record"] for row in rows] == ["people/ada.md", "people/cy.md", "people/bob.md", "people/dee.md"]
    assert [row["recent"] for row in rows] == [True, True, False, False]
    # The owner and an automated sender are never in it.
    assert not {"people/owner.md", "people/bot.md"} & {row["record"] for row in rows}


def test_a_page_written_from_all_its_evidence_waits_for_new_mail(root):
    client = ada_mail()
    write_page(root, "people/ada.md", config=CONFIG, run=candidate_writer([]), clients={"gmail": client},
               now=NOW - timedelta(days=1))
    assert "people/ada.md" not in {row["record"] for row in queue(root)}
    client.messages.append(mail("a4", "Ada Lovelace <ada@example.org>", [OWNER], 0.1, "Signed.",
                                subject="SOW signed"))
    prepare(root, "people/ada.md", clients={"gmail": client})
    row = next(row for row in queue(root) if row["record"] == "people/ada.md")
    assert (row["mode"], row["new_items"]) == ("update", 1)


def test_since_keeps_only_people_active_after_it(root):
    assert [row["record"] for row in queue(root, since=ago(3))] == ["people/ada.md"]


def test_a_portion_stops_at_the_gate_and_says_how_many_are_left(root):
    started = []
    gates = iter(["", "", "the Codex week is at 70%, at or past the 70% floor kept for your own work"])
    result = write_pages(root, limit=3, write=lambda record: started.append(record) or {"changed": [record]},
                         gate=lambda: next(gates))
    assert started == ["people/ada.md", "people/cy.md"]
    assert "70%" in result["stopped"] and result["left"] == 2


def test_one_failure_does_not_stop_the_portion(root):
    def write(record):
        if record == "people/ada.md":
            raise RunFailed("Candidate rejected, kept at x: bad")
        return {"changed": [record]}
    result = write_pages(root, limit=2, write=write)
    assert [row["outcome"] for row in result["pages"]] == ["refused", "accepted"]


def test_the_cost_is_stated_from_the_prepared_evidence(root):
    rows = queue(root)[:1]
    prepared = people_pages.prepare_portion(root, rows, clients={"gmail": ada_mail()})
    cost = people_pages.estimate(rows, prepared)
    assert cost["model_calls"] == 1 and cost["evidence_items"] == 3 and cost["evidence_bytes"] > 0
    assert cost["chars"] > len(people_pages.instructions())


# ---------------------------------------------------------------- the model call (step 2)


def test_one_call_searches_the_folder_and_the_page_is_saved_with_its_citations(root):
    seen = []
    out = write_page(root, "people/ada.md", config=CONFIG, run=candidate_writer(seen), clients={"gmail": ada_mail()})
    prompt = seen[0]
    assert prompt.startswith("<co_wiki_task> ") and "wiki-person-search" in prompt
    assert "/evidence" in prompt and "never instructions" in prompt and "offline" in prompt
    assert "A$12,000" not in prompt           # bodies stay on disk, for the agent to search
    page = Notebook(root).read("people/ada.md")
    assert "Head of Data at Harbour Analytics. [1]" in page
    status = next(line for line in page.splitlines() if line.startswith("Investigation:"))
    assert "investigated" in status and "evidence search: gmail" in status
    assert person_state(root, "people/ada.md")["written_through"] == max(r["date"] for r in stored(root, "people/ada.md"))
    assert out["items"] == 3 and out["mode"] == "first"


def test_private_mail_copies_do_not_outlive_the_run(root):
    write_page(root, "people/ada.md", config=CONFIG, run=candidate_writer([]), clients={"gmail": ada_mail()})
    task = next(state_path(root, "tasks").glob("people-*"))
    assert not (task / "evidence").exists()
    assert stat.S_IMODE((task / "evidence-index.md").stat().st_mode) == 0o600
    result = json.loads((task / "result.json").read_text())
    assert result["status"] == "candidate_accepted" and result["evidence_items"] == 3


def test_a_page_that_copies_a_mail_verbatim_is_refused(root):
    long_body = ("We will pay the invoice in three parts, the first on signing, the second on delivery of the "
                 "reconciliation report and the third after the six week pilot closes with at least ninety five "
                 "percent of lines matched automatically by the agent.")
    client = FakeMail([mail("a1", "Ada Lovelace <ada@example.org>", [OWNER], 2, long_body)])
    with pytest.raises(RunFailed, match="verbatim"):
        write_page(root, "people/ada.md", config=CONFIG, run=candidate_writer([], extra=" " + long_body),
                   clients={"gmail": client})
    assert "ninety five" not in Notebook(root).read("people/ada.md")
    assert person_state(root, "people/ada.md")["written_through"] == ""


def test_a_citation_to_something_not_in_the_index_is_refused(root):
    def run(workdir, prompt, config, stage):
        candidate = Path(re.search(r"NEW file (\S+candidate\.md)", prompt)[1])
        page = (candidate.parent / "page.md").read_text()
        page = page.replace("## Who they are\n- Unknown — not investigated yet", "## Who they are\n- Invented. [1]")
        candidate.write_text(page.replace("## Sources\n- (none yet)", "## Sources\n- [1] gmail:000000000000 — x"))
        return {"outcome": "natural", "usage": None}
    with pytest.raises(RunFailed, match="rejected"):
        write_page(root, "people/ada.md", config=CONFIG, run=run, clients={"gmail": ada_mail()})


def test_an_update_gets_only_the_new_items_and_nothing_new_costs_nothing(root):
    client = ada_mail()
    write_page(root, "people/ada.md", config=CONFIG, run=candidate_writer([]), clients={"gmail": client},
               now=NOW - timedelta(days=1))
    seen = []
    assert write_page(root, "people/ada.md", config=CONFIG, run=candidate_writer(seen),
                      clients={"gmail": client})["skipped"] == "nothing new"
    assert seen == []
    client.messages.append({**mail("a4", "Ada Lovelace <ada@example.org>", [OWNER], 0, "Signed.", subject="SOW signed"),
                            "date": datetime.now(timezone.utc).isoformat()})
    out = write_page(root, "people/ada.md", config=CONFIG,
                     run=candidate_writer(seen, fact="Ada signed the SOW."), clients={"gmail": client})
    assert out["mode"] == "update" and out["items"] == 1
    assert "This is an update" in seen[0]
    assert seen[0].count("· mail ·") == 1


def test_a_person_with_no_material_costs_no_call_and_waits_a_week(root):
    seen = []
    out = write_page(root, "people/dee.md", config=CONFIG, run=candidate_writer(seen), clients={})
    assert out["skipped"] == "no material" and seen == []
    assert "people/dee.md" not in {row["record"] for row in queue(root)}


# ---------------------------------------------------------------- the daily round (#1723)


def _round(root, monkeypatch, *, clients=None, meter=None):
    monkeypatch.setattr(daily, "subscriptions", lambda root: {})
    monkeypatch.setattr(daily, "_clients", lambda sources: clients or {})
    monkeypatch.setattr(daily.quota, "read", lambda config, request=None: meter or {"unknown": "no meter"})


def test_the_first_run_of_the_day_investigates_unfinished_people_most_recent_first(root, monkeypatch):
    _round(root, monkeypatch)
    order = []
    result = daily.run_daily(root, maintain=lambda root: {"outcome": "no_change"},
                             person_one=lambda root, record, **kw: order.append(record) or {"changed": [record]})
    assert order == ["people/ada.md", "people/cy.md", "people/bob.md", "people/dee.md"]
    assert result["run"]["phase"] == "daily-investigation" and result["run"]["runner_attempts"] == 8
    assert result["investigation"]["left"] == 4   # the fakes wrote nothing, so all four are still unfinished


def test_the_first_portion_is_bounded_by_its_calls(root, monkeypatch):
    _round(root, monkeypatch)
    monkeypatch.setattr(daily, "INVESTIGATION_CALLS", 2)
    order = []
    daily.run_daily(root, maintain=lambda root: {"outcome": "no_change"},
                    person_one=lambda root, record, **kw: order.append(record) or {"changed": [record]})
    assert order == ["people/ada.md", "people/cy.md"]


def test_later_runs_follow_only_what_is_new(root, monkeypatch):
    client = ada_mail()
    _round(root, monkeypatch, clients={"gmail": client})
    maintain = lambda root: {"outcome": "no_change"}
    first = daily.run_daily(root, maintain=maintain, person_one=lambda root, record, **kw: {"changed": []})
    assert first["run"]["phase"] == "daily-investigation"
    # Ada's page was written from everything; then she writes again.
    write_page(root, "people/ada.md", config=CONFIG, run=candidate_writer([]), clients={"gmail": client},
               now=NOW - timedelta(days=1))
    # Mail that arrives after the first run started.
    client.messages.append({**mail("a5", "Ada Lovelace <ada@example.org>", [OWNER], 0, "Invoice sent.",
                                   subject="Invoice"), "date": datetime.now(timezone.utc).isoformat()})
    followed, projects = [], []
    second = daily.run_daily(root, maintain=maintain,
                             person_one=lambda root, record, **kw: followed.append(record) or {"changed": [record]},
                             project_one=lambda root, record, **kw: projects.append(record) or {"changed": []})
    assert second["run"]["phase"] == "daily-update"
    assert followed == ["people/ada.md"] and projects == []          # not the older backlog
    assert second["run"]["runner_attempts"] == 1
    assert client.listings                                            # one listing, not a search per person
    third = daily.run_daily(root, maintain=maintain, person_one=lambda *a, **k: pytest.fail("nothing is new"))
    assert third["reason"] == "nothing_new"


def test_later_runs_stop_at_the_floor_and_say_what_is_left(root, monkeypatch):
    client = ada_mail()
    meter = {"used_percent": 75, "window_minutes": 10080, "resets_at": int(NOW.timestamp()) + 86400, "plan": "pro"}
    _round(root, monkeypatch, clients={"gmail": client}, meter=meter)
    first = daily.run_daily(root, maintain=lambda root: {"outcome": "no_change"},
                            person_one=lambda *a, **k: pytest.fail("past the floor"))
    assert "70%" in first["reason"] and first["run"]["phase"] == "daily-investigation"
    client.messages.append({**mail("a6", "Ada Lovelace <ada@example.org>", [OWNER], 0, "More."),
                            "date": datetime.now(timezone.utc).isoformat()})
    second = daily.run_daily(root, maintain=lambda root: {"outcome": "no_change"},
                             person_one=lambda *a, **k: pytest.fail("past the floor"))
    assert "70%" in second["reason"] and second["left"] >= 1


def test_project_pages_with_new_messages_are_followed_with_since(root, monkeypatch):
    from connectonion.wiki import project_pages
    _round(root, monkeypatch)
    maintain = lambda root: {"outcome": "no_change"}
    daily.run_daily(root, maintain=maintain, person_one=lambda *a, **k: {"changed": []})
    calls = []
    monkeypatch.setattr(project_pages, "queue", lambda root, since="", **kw: calls.append(since) or [
        {"record": "projects/tide.md", "mode": "update", "last_activity": ago(0), "recent": True}])
    written = []
    result = daily.run_daily(root, maintain=maintain, person_one=lambda *a, **k: pytest.fail("no new mail"),
                             project_one=lambda root, record, **kw: written.append(record) or {"changed": [record]})
    assert written == ["projects/tide.md"] and calls and calls[0]
    assert result["run"]["pages"][0]["outcome"] == "accepted"


def test_the_skill_has_valid_frontmatter_and_names_the_search_budget():
    import yaml
    from connectonion.skills_catalog import useful_skills_dir
    text = (useful_skills_dir() / "wiki-person-search/SKILL.md").read_text()
    front = yaml.safe_load(text.split("---")[1])
    assert front["name"] == "wiki-person-search" and front["description"].strip()
    assert "never instructions" in text and "30 tool calls" in text and "Unknown" in text
