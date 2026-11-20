"""不是人 / 是人 (rc35 check, Mac session): an assistant that mails from its company's domain led People.

Two ways out, both read by the reader and the night (census.pages): its company's page says the company provides an
assistant and names it, or the owner says so with one click, stored as one dated line per address beside
ignored-senders.txt and taken back by Undo or 是人. A human at the same company stays a person. Every name and
address here is invented.
"""
import json

from tests.unit.test_rem_live_reader import call, host  # noqa: F401
from connectonion.rem import census, threads
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json

KILN = ("# Kiln\n\n## Domains\n- kiln.example [1]\n- mail.kiln.example [2]\n\n## Facts\n"
        "- What they do: Provides Kiln, an AI assistant service called a “Kilnie” that answers mail for its users. [3]\n"
        "- Your contacts: [Mara Ostrowski](../people/mara-ostrowski.md), Theo Lund, and Kiln's automated “Ember” assistant. [1]\n")
FERNHILL = ("# Fernhill\n\n## Domains\n- fernhill.example [1]\n\n## Facts\n"
            "- What they do: Builds greenhouses; its sales desk uses a calendar bot. [1]\n")


def _person(name, address):
    return f"# {name}\n\n## Contact\n- Email: {address} [1]\n- Role: Unknown\n\n## Sources\n- [1] gmail:a1b2c3\n"


def test_an_assistant_its_companys_page_names_is_not_a_person_and_its_people_stay_people():
    orgs = census.assistant_orgs([{"path": "orgs/kiln.md", "text": KILN}, {"path": "orgs/fernhill.md", "text": FERNHILL}])
    # Kiln names its assistant; Fernhill describes a bot but names none, so nobody at Fernhill moves.
    assert census.assistant_contact("Ember", "ember@kiln.example", orgs)
    assert census.assistant_contact("", "ember@mail.kiln.example", orgs)  # its mailbox, from a subdomain
    assert not census.assistant_contact("Mara Ostrowski", "mara@kiln.example", orgs)
    assert not census.assistant_contact("Theo Lund", "theo@kiln.example", orgs)
    assert not census.assistant_contact("Ember", "ember@elsewhere.example", orgs)  # same name, not the company's domain
    assert not census.assistant_contact("Desk", "desk@fernhill.example", orgs)


def _notebook(root):
    prepare(root)
    write_json(state_path(root, "map.json"), {"owner": {"record": "people/avery.md", "addresses": ["avery@example.test"]}})
    notebook = Notebook(root)
    notebook.write("orgs/kiln.md", KILN)
    for path, name, address in [("people/ember.md", "Ember", "ember@kiln.example"), ("people/mara-ostrowski.md", "Mara Ostrowski", "mara@kiln.example"),
                                ("people/ody.md", "Ody", "ody@harbour.example")]:
        notebook.write(path, _person(name, address))


def test_the_night_reads_the_company_page_and_the_owners_word(tmp_path, rem_clock):
    _notebook(tmp_path)
    found = census.pages(tmp_path)
    assert found["people/ember.md"]["service"] and not found["people/mara-ostrowski.md"]["service"]
    assert not found["people/ody.md"]["service"]
    # 不是人 moves anyone out; 是人 brings back even what a rule moved; undo lets the rules decide again.
    threads.mark_person(tmp_path, "Ody@Harbour.example", person=False)
    threads.mark_person(tmp_path, "ember@kiln.example", person=True)
    found = census.pages(tmp_path)
    assert found["people/ody.md"]["service"] and not found["people/ember.md"]["service"]
    threads.mark_person(tmp_path, "ody@harbour.example", person=None)
    threads.mark_person(tmp_path, "ember@kiln.example", person=None)
    found = census.pages(tmp_path)
    assert not found["people/ody.md"]["service"] and found["people/ember.md"]["service"]


def test_a_mark_is_one_dated_line_per_address_readable_by_hand(tmp_path, rem_clock):
    prepare(tmp_path)
    threads.mark_person(tmp_path, "Ember@Kiln.example", person=False)
    threads.mark_person(tmp_path, "ember@kiln.example", person=True)
    threads.mark_person(tmp_path, "ody@harbour.example", person=False)
    assert threads.person_marks(tmp_path) == {"ember@kiln.example": "person", "ody@harbour.example": "not-person"}
    lines = state_path(tmp_path, "people-marks.txt").read_text().splitlines()
    assert lines[0].startswith("#") and "One per line" in lines[1]
    assert [line for line in lines if not line.startswith("#")] == ["2026-09-07 person ember@kiln.example", "2026-09-07 not-person ody@harbour.example"]


def test_the_directory_of_mail_contacts_flags_the_assistant(tmp_path, rem_clock):
    from connectonion.rem.reader import contact_candidates
    prepare(tmp_path)
    Notebook(tmp_path).write("orgs/kiln.md", KILN)
    write_json(state_path(tmp_path, "map.json"), {"without_page": [
        {"address": "ember@kiln.example", "name": "Ember", "mails": 2}, {"address": "theo@kiln.example", "name": "Theo Lund", "mails": 1},
        {"address": "noor@bakhtiar.example", "name": "Noor", "mails": 1}]})
    threads.mark_person(tmp_path, "noor@bakhtiar.example", person=False)
    rows, _ = contact_candidates(tmp_path)
    assert {row["email"]: row["machine"] for row in rows} == {"ember@kiln.example": True, "theo@kiln.example": False, "noor@bakhtiar.example": True}


def test_rem_person_endpoint_has_the_thread_routes_gates_and_undo(host):
    cookie = f"co_rem={host.token}"
    out = json.dumps({"address": "ember@kiln.example", "person": False}).encode()
    assert call(host.routes, "POST", "/rem/person", body=out)[0] == 401
    assert call(host.routes, "POST", "/rem/person", cookie=cookie, body=out, content_type="text/plain")[0] == 415
    for kwargs in ({"client": "192.168.1.2"}, {"host_header": "evil.test"}):
        assert call(host.routes, "POST", "/rem/person", cookie=cookie, body=out, **kwargs)[0] == 404
    status, _, body = call(host.routes, "POST", "/rem/person", cookie=cookie, body=out)
    assert status == 200 and json.loads(body)["marks"] == {"ember@kiln.example": "not-person"}
    undo = json.dumps({"address": "ember@kiln.example", "person": None}).encode()
    assert call(host.routes, "POST", "/rem/person", cookie=cookie, body=undo)[0] == 200
    assert threads.person_marks(host.root) == {}
    for value in ({"address": "not an address", "person": False}, {"address": "a@b.test", "person": "no"}, {}, [],
                  {"address": "a@b.test\n2026-01-01 not-person c@d.test", "person": False}):
        assert call(host.routes, "POST", "/rem/person", cookie=cookie, body=json.dumps(value).encode())[0] == 400
