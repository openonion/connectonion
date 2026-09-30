"""People investigated recent correspondents first, in portions, from new mail only (#1943 stage 3, #1723).

A fake mailbox and fake investigations; never the operator's mail or a model.
"""

import json
import stat
from datetime import datetime, timedelta, timezone

import pytest

from connectonion.rem import daily, people_pages
from connectonion.rem.config import prepare as prepare_notebook
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.people_pages import correspondents_since, estimate, queue, write_pages
from connectonion.rem.runner import RunFailed

NOW = datetime.now(timezone.utc)
OWNER = "owner@example.org"


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat()


class FakeMail:
    """list_between in the shape useful_tools returns: metadata only."""

    def __init__(self, messages):
        self.messages = messages
        self.listings = []

    def list_between(self, start, end, max_results=200):
        self.listings.append((start, end))
        return [m for m in self.messages if start <= m["date"] < end]


def mail(sender, to, date, subject="Hello"):
    return {"id": f"{sender}-{date}", "from": sender, "to": [to], "cc": [], "subject": subject, "date": date}


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "rem"
    prepare_notebook(root)
    notebook = Notebook(root)
    rows = []
    for slug, name, days in (("ada", "Ada Lovelace", 2), ("bob", "Bob Stone", 30), ("cy", "Cy Young", 5),
                             ("dee", "Dee Old", 60)):
        notebook.stub_person(f"people/{slug}.md", name, [f"{slug}@example.org"], email=f"{slug}@example.org")
        rows.append({"record": f"people/{slug}.md", "addresses": [f"{slug}@example.org"], "mails": 10 + len(slug),
                     "last": ago(days)[:10], "classification": "unassessed"})
    notebook.stub_person("people/owner.md", "Owner", [OWNER], email=OWNER)
    notebook.stub_person("people/bot.md", "Alerts", ["alerts@example.org"], email="alerts@example.org")
    rows += [{"record": "people/owner.md", "classification": "account owner"},
             {"record": "people/bot.md", "addresses": ["alerts@example.org"], "last": ago(1)[:10],
              "classification": "automated candidate"}]
    write_json(state_path(root, "map.json"), {"owner": {"record": "people/owner.md", "addresses": [OWNER]},
                                              "people": rows, "projects": [], "orgs": []})
    return root


def investigated(root, record, day):
    notebook = Notebook(root)
    text = notebook.read(record).replace("· not investigated yet", f"· investigated {day} (gmail)")
    notebook.write(record, text)


# ---------------------------------------------------------------- order and windows


def test_recent_correspondents_come_first_then_older_newest_first(root):
    rows = queue(root)
    assert [row["record"] for row in rows] == ["people/ada.md", "people/cy.md", "people/bob.md", "people/dee.md"]
    assert [row["recent"] for row in rows] == [True, True, False, False]
    assert {row["mode"] for row in rows} == {"full"} and rows[0]["days"] == people_pages.FIRST_WINDOW_DAYS
    # The owner and an automated sender are never in it.
    assert not {"people/owner.md", "people/bot.md"} & {row["record"] for row in rows}


def test_a_page_investigated_since_its_last_mail_waits(root):
    investigated(root, "people/ada.md", NOW.date().isoformat())
    assert "people/ada.md" not in {row["record"] for row in queue(root)}


def test_new_mail_after_an_investigation_is_an_update_over_only_the_days_since(root):
    investigated(root, "people/ada.md", (NOW - timedelta(days=10)).date().isoformat())
    row = next(row for row in queue(root) if row["record"] == "people/ada.md")
    assert (row["mode"], row["days"]) == ("update", 11)


def test_mail_later_the_same_day_is_new_when_the_run_time_is_known(root):
    # Noon, so "three hours ago" is the same calendar day whenever the suite runs;
    # at 00:00-03:00 UTC it fell on yesterday and the window was two days.
    noon = NOW.replace(hour=12, minute=0, second=0, microsecond=0)
    investigated(root, "people/ada.md", noon.date().isoformat())
    people_pages.mark_investigated(root, "people/ada.md", noon - timedelta(hours=3))
    write_json(state_path(root, "people/activity.json"), {"people/ada.md": (noon - timedelta(hours=1)).isoformat()})
    row = next(row for row in queue(root, now=noon) if row["record"] == "people/ada.md")
    assert (row["mode"], row["days"]) == ("update", 1)


def test_since_keeps_only_people_active_after_it(root):
    assert [row["record"] for row in queue(root, since=ago(3))] == ["people/ada.md"]


def test_the_cost_counts_calls_and_the_mail_a_full_investigation_reads(root):
    investigated(root, "people/ada.md", (NOW - timedelta(days=10)).date().isoformat())
    cost = estimate(queue(root)[:2])
    assert (cost["model_calls"], cost["updates"], cost["mails_mapped"]) == (2, 1, 12)


def test_one_person_is_one_investigation_over_their_window_with_every_handle(root, monkeypatch):
    seen = {}

    def investigate(root, record, subject, handles, *, days, **kw):
        seen.update(record=record, subject=subject, handles=handles, days=days, max_calls=kw["max_calls"])
        return {"changed": [record]}
    monkeypatch.setattr("connectonion.rem.investigate.investigate", investigate)
    row = {"record": "people/ada.md", "days": 11, "mode": "update"}
    people_pages.investigate_person(root, row, clients={}, subscriptions={}, max_calls=3)
    assert seen == {"record": "people/ada.md", "subject": "Ada Lovelace", "days": 11, "max_calls": 3,
                    "handles": ["ada@example.org", "Ada Lovelace"]}
    done = json.loads(state_path(root, "people/investigated.json").read_text())
    assert done["people/ada.md"] >= NOW.isoformat()[:10]


# ---------------------------------------------------------------- what is new since the last run


def test_one_listing_finds_who_wrote_and_never_the_owner(root):
    client = FakeMail([mail("Ada <ada@example.org>", OWNER, ago(0.1)),
                       mail(f"Owner <{OWNER}>", "cy@example.org", ago(0.05)),
                       mail("Zed <zed@example.org>", OWNER, ago(0.1))])
    found = correspondents_since(root, {"gmail": client}, since=NOW - timedelta(days=1), now=NOW)
    assert found == {"records": ["people/ada.md", "people/cy.md"], "listed": {"gmail": 3}}
    assert len(client.listings) == 1
    # The next listing starts where this one ended, less an hour.
    correspondents_since(root, {"gmail": client}, since=NOW - timedelta(days=5), now=NOW + timedelta(hours=2))
    assert datetime.fromisoformat(client.listings[1][0]) == NOW - timedelta(hours=1)
    # A new mail makes the person's page an update even though the map is older.
    investigated(root, "people/ada.md", (NOW - timedelta(days=3)).date().isoformat())
    assert next(r for r in queue(root) if r["record"] == "people/ada.md")["mode"] == "update"


def test_what_is_kept_is_private_metadata(root):
    correspondents_since(root, {"gmail": FakeMail([mail("Ada <ada@example.org>", OWNER, ago(0.1),
                                                        subject="Secret pilot terms")])},
                         since=NOW - timedelta(days=1), now=NOW)
    folder = state_path(root, "people")
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    for name in ("activity.json", "refresh.json"):
        assert stat.S_IMODE((folder / name).stat().st_mode) == 0o600
        assert "Secret" not in (folder / name).read_text()


# ---------------------------------------------------------------- portions


def test_a_portion_stops_at_the_gate(root):
    started = []
    gates = iter(["", "", "the Codex week is at 70%, at or past the 70% floor kept for your own work"])
    result = write_pages(queue(root)[:3], write=lambda row: started.append(row["record"]), gate=lambda: next(gates))
    assert started == ["people/ada.md", "people/cy.md"] and "70%" in result["stopped"]


def test_one_refusal_does_not_stop_the_portion(root):
    def write(row):
        if row["record"] == "people/ada.md":
            raise RunFailed("Candidate rejected, kept at x: bad")
    result = write_pages(queue(root)[:2], write=write)
    assert [row["outcome"] for row in result["pages"]] == ["refused", "accepted"]


# ---------------------------------------------------------------- the daily round (#1723)


def _round(monkeypatch, *, clients=None, meter=None):
    monkeypatch.setattr(daily, "subscriptions", lambda root: {})
    monkeypatch.setattr(daily, "_clients", lambda sources: clients or {})
    monkeypatch.setattr(daily.quota, "read", lambda config, request=None: meter or {"unknown": "no meter"})


def no_change(root):
    return {"outcome": "no_change"}


def test_the_first_run_of_the_day_investigates_unfinished_people_most_recent_first(root, monkeypatch):
    _round(monkeypatch)
    order = []
    result = daily.run_daily(root, maintain=no_change,
                             person_one=lambda root, row, **kw: order.append((row["record"], row["days"])) or {})
    assert [record for record, _ in order] == ["people/ada.md", "people/cy.md", "people/bob.md", "people/dee.md"]
    assert result["run"]["phase"] == "daily-investigation" and result["run"]["runner_attempts"] == 8
    assert result["investigation"]["left"] == 4   # the fakes wrote nothing


def test_the_first_portion_is_bounded_by_its_calls(root, monkeypatch):
    _round(monkeypatch)
    monkeypatch.setattr(daily, "INVESTIGATION_CALLS", 2)
    order = []
    daily.run_daily(root, maintain=no_change, person_one=lambda root, row, **kw: order.append(row["record"]) or {})
    assert order == ["people/ada.md", "people/cy.md"]


def test_a_refused_person_does_not_end_the_first_portion(root, monkeypatch):
    _round(monkeypatch)
    order = []

    def person(root, row, **kw):
        order.append(row["record"])
        if row["record"] == "people/ada.md":
            raise RunFailed("Candidate rejected, kept at x: bad", {"input_tokens": 5})
        return {"changed": [row["record"]]}
    result = daily.run_daily(root, maintain=no_change, person_one=person)
    assert order[:2] == ["people/ada.md", "people/cy.md"] and result["outcome"] == "completed"
    assert result["run"]["pages"][0]["outcome"] == "refused" and result["run"]["usage"] == {"input_tokens": 5}


def test_later_runs_follow_only_what_is_new(root, monkeypatch):
    client = FakeMail([])
    _round(monkeypatch, clients={"gmail": client})
    first = daily.run_daily(root, maintain=no_change, person_one=lambda *a, **k: {})
    assert first["run"]["phase"] == "daily-investigation"
    for slug in ("ada", "bob", "cy", "dee"):
        investigated(root, f"people/{slug}.md", (NOW - timedelta(days=4)).date().isoformat())
    # Bob writes after the first run; nobody else does.
    client.messages.append(mail("Bob <bob@example.org>", OWNER, datetime.now(timezone.utc).isoformat()))
    followed, projects = [], []
    second = daily.run_daily(root, maintain=no_change,
                             person_one=lambda root, row, **kw: followed.append((row["record"], row["mode"],
                                                                                 row["days"])) or {},
                             project_one=lambda root, record, **kw: projects.append(record) or {})
    assert second["run"]["phase"] == "daily-update" and second["run"]["runner_attempts"] == 1
    assert followed == [("people/bob.md", "update", 5)] and projects == []
    assert len(client.listings) == 1                                  # one listing, not a search per person
    third = daily.run_daily(root, maintain=no_change, person_one=lambda *a, **k: pytest.fail("nothing is new"))
    assert third["reason"] == "nothing_new"


def test_later_runs_stop_at_the_floor_and_say_what_is_left(root, monkeypatch):
    client = FakeMail([])
    meter = {"used_percent": 75, "window_minutes": 10080, "resets_at": int(NOW.timestamp()) + 86400, "plan": "pro"}
    _round(monkeypatch, clients={"gmail": client}, meter=meter)
    first = daily.run_daily(root, maintain=no_change, person_one=lambda *a, **k: pytest.fail("past the floor"))
    assert "70%" in first["reason"] and first["run"]["phase"] == "daily-investigation"
    client.messages.append(mail("Ada <ada@example.org>", OWNER, datetime.now(timezone.utc).isoformat()))
    second = daily.run_daily(root, maintain=no_change, person_one=lambda *a, **k: pytest.fail("past the floor"))
    assert "70%" in second["reason"] and second["left"] >= 1


def test_project_pages_with_new_messages_are_followed_with_since(root, monkeypatch):
    from connectonion.rem import project_pages
    _round(monkeypatch)
    daily.run_daily(root, maintain=no_change, person_one=lambda *a, **k: {})
    calls = []
    monkeypatch.setattr(project_pages, "queue", lambda root, since="", **kw: calls.append(since) or [
        {"record": "projects/tide.md", "mode": "update", "last_activity": ago(0), "recent": True}])
    written = []
    result = daily.run_daily(root, maintain=no_change, person_one=lambda *a, **k: pytest.fail("no new mail"),
                             project_one=lambda root, record, **kw: written.append(record) or {"changed": [record]})
    assert written == ["projects/tide.md"] and calls and calls[0]
    assert result["run"]["pages"][0]["outcome"] == "accepted"
