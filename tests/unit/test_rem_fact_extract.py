"""Facts read from the material with no model, and kept when the model drops them (#2068)."""

import pytest

from connectonion.rem import facts
from connectonion.rem.fact_extract import extract, facts_item
from connectonion.rem.page_review import validate


def mail(source, when, text, speaker="Mia Chen <mia.chen@harbour.example>", role="other", subject="Re: pilot"):
    return {"role": role, "speaker": speaker, "timestamp": when, "subject": subject, "text": text,
            "source": source}


SIGNED = ("Hi Alex,\nThanks, the scope looks right.\n\nBest regards,\nMia Chen\n"
          "Head of Data Platform | Harbour Analytics\nT: +61 2 5550 0142\nM: 0400 555 019\n"
          "https://www.linkedin.com/in/mia-chen-data\n")
HANDLES = ["mia.chen@harbour.example", "Mia Chen"]


def found(rows, field):
    return [row for row in rows if row["field"] == field]


def test_a_phone_only_in_a_signature_is_found_with_its_label():
    rows = extract([mail("gmail:a1", "2026-08-04T01:00:00+00:00", SIGNED)], HANDLES)
    phones = found(rows, "Phone")
    assert [(p["value"], p["qualifier"]) for p in phones] == [("+61 2 5550 0142", "work"), ("0400 555 019", "mobile")]
    assert all(p["source"] == "gmail:a1" and p["date"] == "2026-08-04" for p in phones)
    assert found(rows, "Links")[0]["value"] == "https://www.linkedin.com/in/mia-chen-data"


@pytest.mark.parametrize('flattened', [False, True])
def test_meeting_dial_in_numbers_are_not_restorable_contact_phones(flattened):
    text = ('Mia Chen\nJoin Zoom Meeting\nOne tap mobile\n+61 2 5550 0188\n'
            'Dial by your location\n+61 8 5550 0177\nMeeting ID: 123 456 789\n')
    text = ('Coaching session invitation details. ' * 5 + text.replace('\n', ' ')) if flattened else text
    rows = extract([mail('outlook:meeting', '2026-08-04T01:00:00+00:00', text)], HANDLES)
    assert not found(rows, 'Phone')
    assert found(rows, 'Calendar')
    both = extract([mail('outlook:meeting', '2026-08-04T01:00:00+00:00', text),
                    mail('outlook:direct', '2026-08-05T01:00:00+00:00', SIGNED)], HANDLES)
    assert all(row['source'] == 'outlook:direct' for row in found(both, 'Phone'))
    assert len(found(both, 'Phone')) == 2


def test_the_signature_block_is_handed_over_for_role_and_company():
    rows = extract([mail("gmail:a1", "2026-08-04T01:00:00+00:00", SIGNED)], HANDLES)
    block = found(rows, "Signature")[0]["value"]
    assert "Head of Data Platform | Harbour Analytics" in block and "Thanks" not in block


@pytest.mark.timeout(2)
def test_long_non_invitation_mail_does_not_backtrack_over_every_possible_zoom_subdomain():
    rows = extract([mail("outlook:long", "2026-08-04T00:00:00Z", "x" * 30_000)], HANDLES)
    assert not found(rows, "Calendar")
    assert found(rows, "Last contact")[0]["value"] == "2026-08-04"


@pytest.mark.parametrize("url", ["https://zoom.us/j/123", "https://harbour.zoom.us/j/123"])
def test_zoom_link_alone_keeps_invitation_numbers_out_of_phone(url):
    rows = extract([mail("outlook:link", "2026-08-04T00:00:00Z", SIGNED + url)], HANDLES)
    assert not found(rows, "Phone")
    assert found(rows, "Calendar")


def test_legacy_flattened_zoom_invitation_does_not_restore_a_rejected_phone():
    text = ('Purpose of this meeting is to understand the pilot vision. ' * 4
            + 'Mia Chen is inviting you to a scheduled Zoom meeting.'
            + 'Join from PC, Mac, Linux, iOS or Android: https://harbour.zoom.us/j/123456789'
            + 'Or iPhone one-tap :Australia: +61255500188,,123456789# or +61855500177,,123456789#'
            + 'Or Telephone:Dial(for higher quality, dial a number based on your current location)')
    rows = extract([mail('outlook:legacy', '2026-08-04T01:00:00+00:00', text,
                         subject='Pilot support | Alex')], HANDLES)
    assert not found(rows, 'Phone')
    assert found(rows, 'Calendar')
    candidate = PAGE.replace('Mia leads the pilot [1].',
                             'Mia leads the pilot; previously listed numbers were meeting dial-ins [1].')
    kept, restored = facts.keep_extracted('people/mia.md', candidate, rows)
    assert '- Phone: Unknown' in kept
    assert not any(row['field'] == 'Phone' for row in restored)


def test_a_body_the_provider_flattened_to_one_line_still_gives_its_signature_and_phone():
    flat = ("Hi Alex, " + "thanks for the notes on the pilot scope and the timeline we discussed. " * 4
            + "Kind regards, Mia Chen Head of Data Platform Harbour Analytics Mobile: +61 400 555 019")
    rows = extract([mail("outlook:g7", "2026-08-04T01:00:00+00:00", flat)], HANDLES)
    assert [(r["value"], r["qualifier"]) for r in found(rows, "Phone")] == [("+61 400 555 019", "mobile")]
    assert found(rows, "Signature")[0]["value"].startswith("Mia Chen Head of Data Platform")


def test_a_company_only_in_the_domain_is_named_but_a_mailbox_provider_is_not():
    rows = extract([mail("outlook:b2", "2026-08-04T01:00:00+00:00", "Sure, Thursday.\nMia")], HANDLES)
    assert found(rows, "Company domain")[0]["value"] == "harbour.example"
    gmail = extract([mail("gmail:c3", "2026-08-04T01:00:00+00:00", "ok",
                          speaker="Mia <mia88@gmail.com>")], ["mia88@gmail.com"])
    assert not found(gmail, "Company domain")


def test_a_role_only_in_a_calendar_invite_is_handed_over_as_the_invite_line():
    invite = ("Invitation: Pilot kickoff @ Thu 21 Aug 2026 2pm - 3pm (AEST)\n"
              "Attendees: Alex Rivera (organiser); Mia Chen, Procurement Lead, Harbour Analytics\n"
              "Join with Google Meet: https://meet.google.com/abc-defg-hij\n")
    rows = extract([mail("gmail:d4", "2026-08-15T01:00:00+00:00", invite, speaker="Alex <alex@rivera.example>",
                         role="user", subject="Invitation: Pilot kickoff")], HANDLES)
    lines = [row["value"] for row in found(rows, "Calendar")]
    assert any("Procurement Lead" in line for line in lines)


def test_earliest_retained_mail_does_not_become_first_contact():
    rows = extract([mail("gmail:a1", "2026-08-04T01:00:00+00:00", "hi"),
                    mail("gmail:a2", "2026-09-10T01:00:00+00:00", "ok", role="user", speaker="Alex <a@r.example>")],
                   HANDLES)
    assert not found(rows, "First contact")
    assert found(rows, "Last contact")[0]["value"] == "2026-09-10"
    assert found(rows, "Last contact")[0]["source"] == "gmail:a2"


@pytest.mark.parametrize("zone, last", [
    ("Australia/Sydney", "2026-08-01"),
    ("America/Los_Angeles", "2026-07-31"),
    ("UTC", "2026-07-31"),
])
def test_last_contact_and_signature_dates_use_notebook_timezone_in_timestamp_order(zone, last):
    # Same UTC day, reverse input order: source choice needs full instants.
    rows = extract([mail("outlook:late", "2026-07-31T23:03:58Z", SIGNED),
                    mail("outlook:early", "2026-07-31T00:23:51Z", "hello")],
                   HANDLES, timezone=zone)
    assert not found(rows, "First contact")
    assert found(rows, "Last contact")[0]["value"] == last
    assert found(rows, "Last contact")[0]["source"] == "outlook:late"
    assert all(row["date"] == last for row in found(rows, "Phone") + found(rows, "Signature"))


def test_numbers_that_are_not_phones_are_left_alone():
    text = "Invoice 2026-08-04 total 123456789 ref 4412 9934 0011 2299\nMia Chen\n"
    assert not found(extract([mail("gmail:e5", "2026-08-04T01:00:00+00:00", text)], HANDLES), "Phone")


def test_someone_elses_mail_does_not_give_the_subject_a_phone():
    other = mail("gmail:f6", "2026-08-04T01:00:00+00:00", "Regards,\nDana\nM: +61 411 222 333",
                 speaker="Dana <dana@other.example>")
    assert not found(extract([other], HANDLES), "Phone")


def test_the_item_tells_the_turn_to_cite_the_source_not_the_item():
    rows = extract([mail("gmail:a1", "2026-08-04T01:00:00+00:00", SIGNED)], HANDLES)
    item = facts_item(rows)
    assert item["role"] == "facts" and item["source"] == "investigation:facts"
    assert "Phone: +61 2 5550 0142 (work) — gmail:a1, 2026-08-04" in item["text"]
    assert item["facts"] == rows


PAGE = """# Mia Chen

Mia leads the pilot [1]. Last contact: 2026-09-10 [1].

## Facts
- Email: mia.chen@harbour.example
- Phone: Unknown
- Last contact: 2026-09-10 [1]

## Sources
- [1] gmail:a2 — 2026-09-10, high
"""


def test_a_phone_the_model_dropped_is_put_back_with_its_source():
    rows = extract([mail("gmail:a1", "2026-08-04T01:00:00+00:00", SIGNED)], HANDLES)
    kept, restored = facts.keep_extracted("people/mia.md", PAGE, rows)
    assert "- Phone: +61 2 5550 0142 (work) [2]; 0400 555 019 (mobile) [2]" in kept
    assert "- [2] gmail:a1 — 2026-08-04\n" in kept
    assert {r["field"] for r in restored} == {"Phone"}           # no Links line: nothing to fill
    assert facts.keep_extracted("people/mia.md", kept, rows)[1] == []
    upgraded, restored = facts.keep_extracted("people/mia.md", facts.upgrade("people/mia.md", PAGE), rows)
    assert {r["field"] for r in restored} == {"Phone", "Links"}
    assert "- First contact: Unknown" in upgraded and "- Last contact: 2026-09-10 [1]" in upgraded


def test_a_phone_already_on_the_page_in_another_format_is_not_added_twice():
    page = PAGE.replace("- Phone: Unknown", "- Phone: +61 (2) 5550-0142 [1]; +61 400 555 019 (mobile) [1]")
    rows = [r for r in extract([mail("gmail:a1", "2026-08-04T01:00:00+00:00", SIGNED)], HANDLES)
            if r["field"] == "Phone"]
    assert facts.keep_extracted("people/mia.md", page, rows) == (page, [])


def test_a_date_the_model_corrected_is_not_overwritten():
    rows = [{"field": "Last contact", "value": "2026-09-01", "qualifier": "", "source": "gmail:z", "date": "2026-09-01"}]
    assert facts.keep_extracted("people/mia.md", PAGE, rows) == (PAGE, [])


def test_a_last_contact_date_uses_the_notebook_calendar_when_it_cites_the_same_original():
    item = mail('gmail:a2', '2026-09-09T23:30:00Z', SIGNED)
    rows = [r for r in extract([item], HANDLES, timezone='Australia/Sydney') if r['field'] == 'Last contact']
    page = PAGE.replace('- Last contact: 2026-09-10 [1]', '- Last contact: 2026-09-09 [1]')
    page += '\n## History\n- 2026-09-10: A separate milestone already has the right date [1].\n'
    kept, changed = facts.keep_extracted('people/mia.md', page, rows)
    assert '- Last contact: 2026-09-10 [1]' in kept
    assert changed == rows
    assert facts.keep_extracted('people/mia.md', kept, rows) == (kept, [])


@pytest.mark.parametrize('current', ['2026-09-09 (approximate) [1]', '2026-09-09 [1][2]'])
def test_contact_calendar_repair_keeps_qualified_or_multiple_source_interpretations(current):
    rows = [{'field': 'Last contact', 'value': '2026-09-10', 'qualifier': '', 'source': 'gmail:a2',
             'date': '2026-09-10'}]
    page = PAGE.replace('- Last contact: 2026-09-10 [1]', '- Last contact: ' + current)
    assert facts.keep_extracted('people/mia.md', page, rows) == (page, [])


def test_a_fact_from_the_carrier_email_does_not_cite_its_attachment_instead():
    page = PAGE.replace('gmail:a2 —', 'gmail:a2:Signed contract.pdf —')
    row = {'field': 'Phone', 'value': '+61 2 5550 0142', 'qualifier': 'work', 'source': 'gmail:a2',
           'date': '2026-09-10', 'own': True}
    kept, restored = facts.keep_extracted('people/mia.md', page, [row])
    assert '- Phone: +61 2 5550 0142 (work) [2]' in kept
    assert '- [1] gmail:a2:Signed contract.pdf —' in kept
    assert '- [2] gmail:a2 — 2026-09-10' in kept
    assert restored == [row]


class Signed:
    """One mail from Vern whose phone is only in his signature."""
    def my_addresses(self): return {"me@x.y"}
    def list_between(self, s, e, n):
        return [{"id": "s1", "from": "Vern Chan <vern.chan@unsw.edu.au>", "to": ["me@x.y"], "subject": "Hello",
                 "date": s}]
    def get_email_body(self, i):
        return "Hi, see you Thursday.\n\nRegards,\nVern Chan\nGlobal Program Manager\nM: +61 412 000 111\n"


def test_the_turn_is_handed_the_facts_and_the_dropped_phone_comes_back(tmp_path, monkeypatch):
    from connectonion.rem import investigate as inv
    from connectonion.rem import runner
    from connectonion.rem.config import prepare, set_config
    monkeypatch.setattr("connectonion.rem.runner.check_skill", lambda root, stage: None)
    root = tmp_path / "rem"
    prepare(root)
    set_config(root, ["schedule.timezone", "Australia/Sydney"])
    notebook = inv.Notebook(root)
    notebook.stub_person("people/vern.md", "Vern Chan", ["vern"], email="vern.chan@unsw.edu.au")
    original = notebook.read("people/vern.md")
    seen = {}
    monkeypatch.setattr(Signed, "list_between", lambda self, s, e, n: [
        {"id": "s1", "from": "Vern Chan <vern.chan@unsw.edu.au>", "to": ["me@x.y"],
         "subject": "Hello", "date": "2026-09-30T23:03:58Z"}])

    def write(nb, items, config, stage):
        seen["facts"] = next(i for i in items if i["role"] == "facts")
        source = next(i["source"] for i in items if i.get("role") == "other")
        page = (original.replace("Unknown — not investigated yet. Last contact: Unknown.",
                                 "Vern runs the programme [1]. Last contact: 2026-09-30 [1].")
                .replace("- Unknown — not investigated yet", "- Unknown")
                .replace("- Role: Unknown", "- Role: Global Program Manager [1]")
                .replace("- (none yet)", f"- [1] {source} — 2026-09-30, high"))
        candidate = tmp_path / "candidate.md"
        candidate.write_text(page)
        runner._promote_candidate(nb, "people/vern.md", candidate, original, items, tmp_path, None)
        return {"changed": ["people/vern.md"], "usage": None}

    result = inv.investigate(root, "people/vern.md", "Vern Chan", ["vern", "vern.chan@unsw.edu.au"], days=5,
                             clients={"outlook": Signed()}, subscriptions={}, runner=write)
    assert "Phone: +61 412 000 111 (mobile)" in seen["facts"]["text"]
    assert found(seen["facts"]["facts"], "Last contact")[0]["value"] == "2026-10-01"
    assert "Dates use Australia/Sydney" in seen["facts"]["text"]
    assert "earliest retained mail does not establish first contact" in seen["facts"]["text"]
    page = notebook.read("people/vern.md")
    assert "- Phone: +61 412 000 111 (mobile) [1]" in page        # same message, same number
    assert result["facts"]["after"]["filled"] > result["facts"]["before"]["filled"]
    assert result["facts"]["extracted"] >= 3                        # email, phone and last contact


class Thread(Signed):
    """Vern gives a number in his own words; David, copied in, signs with his office line."""
    def list_between(self, s, e, n):
        return [{"id": "s1", "from": "Vern Chan <vern.chan@unsw.edu.au>", "to": ["me@x.y"], "subject": "Hello",
                 "date": "2026-09-30T23:03:58Z"},
                {"id": "s2", "from": "David Burt <david.burt@unsw.edu.au>", "to": ["me@x.y", "vern.chan@unsw.edu.au"],
                 "subject": "Re: Hello", "date": "2026-09-29T01:00:00Z"}]
    def get_email_body(self, i):
        return ("Call me on 0457 222 333 any time.\n\nRegards,\nVern Chan\nM: +61 412 000 111\n" if i == "s1" else
                "Thanks both.\n\nKind regards,\nDavid Burt\nDirector of Entrepreneurship\nT: +61 2 9065 4432\n")


def test_a_phone_from_someone_elses_signature_is_taken_off_and_one_they_gave_in_their_words_stays(tmp_path, monkeypatch):
    """#2348: Vern's page carried David Burt's office line from David's signature in the
    thread. The rule that kept only signature phones also took Dannielle's own
    "give me a call on …" and refused her page over the source left uncited (1.9.2b3 trial)."""
    from connectonion.rem import investigate as inv
    from connectonion.rem import runner
    from connectonion.rem.config import prepare
    monkeypatch.setattr("connectonion.rem.runner.check_skill", lambda root, stage: None)
    root = tmp_path / "rem"
    prepare(root)
    notebook = inv.Notebook(root)
    notebook.stub_person("people/vern.md", "Vern Chan", ["vern"], email="vern.chan@unsw.edu.au")
    original = notebook.read("people/vern.md")
    seen = {}

    def write(nb, items, config, stage):
        seen["facts"] = next(i for i in items if i["role"] == "facts")["text"]
        mine, davids = (next(i["source"] for i in items if i.get("role") == "other" and name in i.get("speaker", ""))
                        for name in ("Vern", "David"))
        page = (original.replace("Unknown — not investigated yet. Last contact: Unknown.",
                                 "Vern runs the programme [1]. Last contact: 2026-09-30 [1].")
                .replace("- Unknown — not investigated yet", "- Unknown")
                .replace("- Phone: Unknown", "- Phone: 0457 222 333 (mobile) [1]; +61 2 9065 4432 (work) [2]")
                .replace("- (none yet)", f"- [1] {mine} — 2026-09-30, high\n- [2] {davids} — 2026-09-29"))
        candidate = tmp_path / "candidate.md"
        candidate.write_text(page)
        runner._promote_candidate(nb, "people/vern.md", candidate, original, items, tmp_path, None)
        return {"changed": ["people/vern.md"], "usage": None}

    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern", "vern.chan@unsw.edu.au"], days=5,
                    clients={"outlook": Thread()}, subscriptions={}, runner=write)
    assert "Someone else's phone: +61 2 9065 4432 (David Burt)" in seen["facts"]
    page = notebook.read("people/vern.md")
    assert "0457 222 333 (mobile) [1]" in page and "9065" not in page
    assert "- [2]" not in page   # David's mail, cited by nothing else now, goes rather than refuse the page


def test_an_unknown_company_links_the_organisation_page_for_the_persons_mail_domain(tmp_path, monkeypatch):
    """#2349: 28 of 53 `Company: Unknown` people wrote from a domain the notebook has an
    organisation page for; the turn left it Unknown, code knows the domain."""
    from connectonion.rem import investigate as inv
    from connectonion.rem import runner
    from connectonion.rem.config import prepare
    monkeypatch.setattr("connectonion.rem.runner.check_skill", lambda root, stage: None)
    root = tmp_path / "rem"
    prepare(root)
    notebook = inv.Notebook(root)
    notebook.stub_person("people/vern.md", "Vern Chan", ["vern"], email="vern.chan@unsw.edu.au")
    notebook.stub_org("orgs/unsw.md", "UNSW Sydney", ["unsw.edu.au"])
    original = notebook.read("people/vern.md")

    def write(nb, items, config, stage):
        mine = next(i["source"] for i in items if i.get("role") == "other" and "Vern" in i.get("speaker", ""))
        page = (original.replace("Unknown — not investigated yet. Last contact: Unknown.",
                                 "Vern runs the programme [1]. Last contact: 2026-09-30 [1].")
                .replace("- Unknown — not investigated yet", "- Unknown")
                .replace("- (none yet)", f"- [1] {mine} — 2026-09-30, high"))
        candidate = tmp_path / "candidate.md"
        candidate.write_text(page)
        runner._promote_candidate(nb, "people/vern.md", candidate, original, items, tmp_path, None)
        return {"changed": ["people/vern.md"], "usage": None}

    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern", "vern.chan@unsw.edu.au"], days=5,
                    clients={"outlook": Signed()}, subscriptions={}, runner=write)
    assert "- Company: [UNSW Sydney](../orgs/unsw.md) [1]" in notebook.read("people/vern.md")
    review = __import__("json").loads((tmp_path / "review.json").read_text())
    assert review["company_from_domain"]["domain"] == "unsw.edu.au"   # code-made changes are on record


def test_a_page_that_already_cites_the_mail_gets_its_lost_phone_without_a_model_call(tmp_path, monkeypatch):
    """Ody's case: the signature mail was cited, so nothing was new, and the phone stayed Unknown."""
    from connectonion.rem import investigate as inv
    from connectonion.rem.config import prepare
    monkeypatch.setattr("connectonion.rem.runner.check_skill", lambda root, stage: None)
    root = tmp_path / "rem"
    prepare(root)
    notebook = inv.Notebook(root)
    notebook.stub_person("people/vern.md", "Vern Chan", ["vern"], email="vern.chan@unsw.edu.au")
    source = "outlook:" + __import__("hashlib").sha256(b"s1").hexdigest()[:12]
    page = (notebook.read("people/vern.md").replace("- Unknown — not investigated yet", "- Unknown")
            .replace("- (none yet)", f"- [1] {source} — 2026-09-30, high")
            .replace("- Role: Unknown", "- Role: Global Program Manager [1]")
            .replace("· not investigated yet", "· investigated 2026-09-29 (outlook)"))
    notebook.write("people/vern.md", page)
    with pytest.raises(inv.NothingNew):
        inv.investigate(root, "people/vern.md", "Vern Chan", ["vern", "vern.chan@unsw.edu.au"], days=5,
                        clients={"outlook": Signed()}, subscriptions={},
                        runner=lambda *a, **k: pytest.fail("no model call"))
    kept = notebook.read("people/vern.md")
    assert "- Phone: +61 412 000 111 (mobile) [1]" in kept
    assert "- First contact: Unknown" in kept          # an update's window is not the whole history


def test_a_new_fact_without_a_citation_is_refused_but_a_mapped_address_is_not():
    original = PAGE
    items = [{"role": "page", "record": "people/mia.md"}, {"source": "gmail:a2"}]
    candidate = PAGE.replace("- Phone: Unknown", "- Phone: +61 2 5550 0142")
    errors = validate("people/mia.md", candidate, original, items)
    assert any("Fact without a citation: Phone" in e for e in errors)
    assert not any("Email" in e for e in errors if e.startswith("Fact without"))


# ------------------------------------------- contact facts are right or Unknown (contacts audit, #2348, #2135)

NOTICE = ("Hi all,\nPlease see the notice below about the co-working space.\n\n"
          "There will be a power outage on Saturday 7 February.\n"
          "Thank you for your understanding as we continue to improve the building.\n"
          "For more information contact Pat Lee, Facilities Manager, Estate Management\n"
          "Ph 0491 570 156\nEmail p.lee@harbour.example\n")


@pytest.mark.parametrize("subject", ["Important Notice - Co Working access + power outage Feb", "Co Working access"])
def test_a_number_under_someone_elses_name_in_the_subjects_own_mail_is_not_theirs(subject):
    """P1: Nina forwarded an estate notice; "Thank you for your understanding…" opened a
    "signature" and the facilities manager's mobile was restored onto her page."""
    rows = extract([mail("outlook:n1", "2026-02-03T01:00:00+00:00", NOTICE, subject=subject)], HANDLES)
    assert not found(rows, "Phone")
    kept, restored = facts.keep_extracted("people/mia.md", PAGE, rows)
    assert "0466" not in kept and not [r for r in restored if r["field"] == "Phone"]


LUMA = ("https://luma.com/xfkmdqae\nBuild Your AI Sales Engine\nAug 20, 6:00 PM GMT+10 · Harbour Tower\n\n"
        "Mia Chen\n\nPlease meet us in the ground floor lobby at 6:00pm. If you are late and did not see us, "
        "call Sam 0491570006\nView Event: https://luma.com/xfkmdqae\n"
        "You received this email because you are part of Build Your AI Sales Engine on Luma.\n")
RELAY = "Mia Chen <usr-s2godxk@user.luma-mail.com>"


def test_a_luma_host_copy_gives_no_phone_and_its_relay_is_no_email():
    """P2/E2: the relay joined Ody's handles by display name; his name line opened a
    "signature" and "call Larry 0405…" became his phone in 8 of 8 runs."""
    item = mail("gmail:l1", "2026-08-20T06:20:45+00:00", LUMA, speaker=RELAY,
                subject="[Host Copy] New message in Build Your AI Sales Engine")
    rows = extract([item], [*HANDLES, "usr-s2godxk@user.luma-mail.com"])
    assert not found(rows, "Phone") and not found(rows, "Email") and not found(rows, "Company domain")
    assert "0405" not in facts_item(rows)["text"]


def test_a_number_named_for_someone_else_in_a_signature_is_not_the_subjects():
    text = "Thanks,\nMia Chen\nHarbour Analytics\nAfter hours call Sam 0491 570 006\nM: 0400 555 019\n"
    rows = extract([mail("gmail:s1", "2026-08-04T01:00:00+00:00", text)], HANDLES)
    assert [p["value"] for p in found(rows, "Phone")] == ["0400 555 019"]


def test_a_block_after_a_thank_you_that_never_names_the_sender_gives_no_phone():
    text = "Thank you\nFacilities desk\nPh 0491 570 156\n"
    assert not found(extract([mail("gmail:t1", "2026-08-04T01:00:00+00:00", text)], HANDLES), "Phone")


def test_one_number_in_two_formats_is_one_row():
    """Morgan's care line came as 1800 737 633 and +61 1800 737 633 and went on her page twice (P3)."""
    text = "Regards,\nMia Chen\nT: 1800 737 633\n"
    other = "Regards,\nMia Chen\nO +61 1800 737 633\n"
    rows = extract([mail("gmail:m1", "2026-08-04T01:00:00+00:00", text),
                    mail("gmail:m2", "2026-08-05T01:00:00+00:00", other)], HANDLES)
    assert len(found(rows, "Phone")) == 1


def test_a_restored_phone_or_address_must_be_the_subjects_own():
    rows = [{"field": "Phone", "value": "0491 570 006", "qualifier": "", "source": "gmail:l1", "date": "2026-08-20"}]
    assert facts.keep_extracted("people/mia.md", PAGE, rows) == (PAGE, [])


def test_last_contact_is_human_mail_between_them_not_a_broadcast_or_notice():
    """T2: Tamara's kitchen-etiquette note to about 30 startups became her Last contact."""
    everyone = {"from": "Mia Chen <mia.chen@harbour.example>", "to": [f"p{n}@x.example" for n in range(30)], "cc": []}
    rows = extract([
        mail("gmail:h1", "2026-09-01T01:00:00+00:00", "Thursday works.\nMia"),
        {**mail("gmail:b1", "2026-10-06T01:00:00+00:00", "Kitchen etiquette reminder"), "participants": everyone},
        mail("gmail:n1", "2026-10-07T01:00:00+00:00", "Your weekly digest", speaker="Mia Chen <noreply@harbour.example>"),
        {**mail("gmail:u1", "2026-10-08T01:00:00+00:00", "Updates", role="user", speaker="Alex <a@r.example>"),
         "participants": {"from": "Alex <a@r.example>", "to": ["someone@else.example"], "cc": []}},
    ], [*HANDLES, "noreply@harbour.example"])
    assert found(rows, "Last contact")[0]["source"] == "gmail:h1"


@pytest.mark.parametrize("handle", ["agentmail.cc", "@agentmail.cc"])
@pytest.mark.parametrize("domain", ["agentmail.cc", "team.agentmail.cc"])
def test_org_domain_last_contact_uses_human_mail_and_reaches_the_page(tmp_path, handle, domain):
    """2026-10-16 first-run trial: orgs cited two-way mail but Last contact stayed Unknown."""
    from connectonion.rem.files import Notebook
    from connectonion.rem.project_claim_review import packet

    adi = f"Adi <adi@{domain}>"
    sent = {**mail("gmail:sent", "2026-08-22T01:00:00Z", "Can we talk?", speaker="Me <me@x.example>", role="user"),
            "participants": {"from": "me@x.example", "to": [adi], "cc": []}}
    reply = {**mail("gmail:reply", "2026-09-03T01:00:00Z", "Regards,\nAdi\nM: 0400 555 019\n", speaker=adi),
             "participants": {"from": adi, "to": ["me@x.example"], "cc": []}}
    broadcast = {**sent, "source": "gmail:broadcast", "timestamp": "2026-10-06T01:00:00Z",
                 "participants": {"to": [f"p{n}@{domain}" for n in range(40)], "cc": []}}
    items = [sent, reply, broadcast]
    rows = extract(items, [handle])
    assert found(extract([sent], [handle]), "Last contact")[0]["source"] == "gmail:sent"
    assert not found(extract([broadcast], [handle]), "Last contact")
    unaddressed = mail("gmail:unaddressed", "2026-10-07T01:00:00Z", "Hello", speaker="Me <me@x.example>", role="user")
    assert not found(extract([unaddressed], [handle]), "Last contact")
    assert rows == [{"field": "Last contact", "value": "2026-09-03", "qualifier": "",
                     "source": "gmail:reply", "date": "2026-09-03"}]

    notebook = Notebook(tmp_path)
    record = "orgs/agentmail.md"
    notebook.stub_org(record, "AgentMail", ["agentmail.cc"])
    page, restored = facts.keep_extracted(record, notebook.read(record), rows)
    assert "- Last contact: 2026-09-03 [1]" in page
    assert "- [1] gmail:reply — 2026-09-03" in page
    assert "- First contact: Unknown" in page
    assert restored == rows
    audit, missing = packet(notebook, page, items=[facts_item(rows), *items])
    assert not missing
    assert audit["runner_facts"] == [{"field": "Last contact", "value": "2026-09-03", "source": "gmail:reply"}]


@pytest.mark.parametrize("speaker, role, recipients, subject", [
    ("noreply@agentmail.cc", "other", ["me@x.example"], "Digest"),
    ("adi@agentmail.cc", "other", ["me@x.example"], "Important Notice"),
    ("adi@agentmail.cc", "other", [f"p{n}@agentmail.cc" for n in range(40)], "Hello all"),
    ("adi@notagentmail.cc", "other", ["me@x.example"], "Hello"),
    ("adi@agentmail.cc.evil.example", "other", ["me@x.example"], "Hello"),
    ("someone@else.example", "other", ["adi@agentmail.cc"], "Hello"),
    ("me@x.example", "user", ["someone@else.example"], "Hello"),
    ("me@x.example", "user", [], "Hello"),
])
def test_org_domain_last_contact_rejects_notices_broadcasts_and_unrelated_mail(speaker, role, recipients, subject):
    item = {**mail("gmail:excluded", "2026-10-07T01:00:00Z", "Hello", speaker=speaker, role=role, subject=subject),
            "participants": {"to": recipients, "cc": []}}
    assert not found(extract([item], ["@agentmail.cc"]), "Last contact")


# ------------------------------------------- promotion keeps a contact detail only when the mail shows it

def contact_page(email, phone, sources):
    return ("# Mia Chen\n\nMia runs the pilot [1].\n\n## Facts\n"
            f"- Email: {email}\n- Phone: {phone}\n- Company: Unknown\n\n## Sources\n"
            + "".join(f"- [{n}] {source} — 2026-08-20\n" for n, source in enumerate(sources, 1)))


def test_promotion_drops_a_number_from_a_luma_notice_and_keeps_one_given_in_their_own_words(tmp_path):
    """P2 kept "call Larry"; Andrew's "ring me at 0481…" through the same relay is his (contacts audit)."""
    from connectonion.rem.config import prepare
    from connectonion.rem.page_review import verify_contacts
    prepare(tmp_path)
    own = LUMA.replace("If you are late and did not see us, call Sam 0491570006",
                       "If anyone is lost, ring me at 0491570157")
    items = [mail("gmail:l1", "2026-08-20T06:20:45+00:00", LUMA, speaker=RELAY,
                  subject="[Host Copy] New message in Build Your AI Sales Engine"),
             mail("gmail:l2", "2026-08-21T06:20:45+00:00", own, speaker=RELAY,
                  subject="[Host Copy] New message in Build Your AI Sales Engine")]
    page = contact_page("Unknown", "0491570006 [1]; 0491570157 [2]", ["gmail:l1", "gmail:l2"])
    text, removed = verify_contacts(tmp_path, "people/mia.md", page, items)
    assert "- Phone: 0491570157 [2]\n" in text and removed == ["0491570006 [1]"]


def test_promotion_keeps_a_number_an_airbnb_relay_shows_under_their_name(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.page_review import verify_contacts
    prepare(tmp_path)
    body = ("--- Email Body ---\nhttps://www.airbnb.com.au/?c=x\nYou’ve got a new message\n"
            "Mia Chen - Harbour Homes\nSure my number is +61491570158\nReply <https://www.airbnb.com.au/x>\n")
    items = [mail("outlook:a1", "2026-08-25T23:29:20Z", body, speaker="Airbnb <express@airbnb.com>",
                  subject="You’ve got a new message")]
    page = contact_page("Unknown", "+61 491 570 158 [1]", ["outlook:a1"])
    assert verify_contacts(tmp_path, "people/mia.md", page, items) == (page, [])


def test_promotion_drops_a_number_from_a_notice_the_subject_forwarded(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.page_review import verify_contacts
    prepare(tmp_path)
    items = [mail("outlook:n1", "2026-02-03T01:00:00+00:00", NOTICE + "\nBest regards,\nMia Chen\nM: 0400 555 019\n",
                  subject="Co Working access")]
    page = contact_page("Unknown", "0491 570 156 (work) [1]; 0400 555 019 (mobile) [1]", ["outlook:n1"])
    text, removed = verify_contacts(tmp_path, "people/mia.md", page, items)
    assert "- Phone: 0400 555 019 (mobile) [1]\n" in text and removed == ["0491 570 156 (work) [1]"]


def test_promotion_keeps_only_addresses_they_send_from_or_are_written_to_at_by_name(tmp_path):
    """E1/E2: Luma relays sat in Email; E5: addresses from a signature they never write from."""
    from connectonion.rem.config import prepare
    from connectonion.rem.page_review import verify_contacts
    prepare(tmp_path)
    items = [{**mail("gmail:a1", "2026-08-04T01:00:00+00:00", SIGNED),
              "participants": {"from": "Mia Chen <mia.chen@harbour.example>", "to": ["me@x.y"], "cc": []}},
             {**mail("gmail:a2", "2026-08-05T01:00:00+00:00", "ok", role="user", speaker="Me <me@x.y>"),
              "participants": {"from": "Me <me@x.y>", "to": ['"Mia Chen" <mia@home.example>'], "cc": []}}]
    page = contact_page("mia.chen@harbour.example, usr-abc@user.luma-mail.com, mia@home.example, "
                        "z1234567@ad.harbour.example", "Unknown", ["gmail:a1"])
    page = page.replace("- Company: Unknown", "- Company: Unknown\n- Handles: mia; usr-abc@user.luma-mail.com")
    text, removed = verify_contacts(tmp_path, "people/mia.md", page, items)
    assert "- Email: mia.chen@harbour.example; mia@home.example\n" in text
    assert "- Handles: mia\n" in text
    assert sorted(removed) == ["usr-abc@user.luma-mail.com", "usr-abc@user.luma-mail.com", "z1234567@ad.harbour.example"]


def test_a_spelling_the_person_rejected_leaves_also_known_as():
    """A1: Ody wrote that his Chinese name is 周泽凯, not 周泽楷; the page listed both."""
    page = "# Ody\n\n## Facts\n- Also known as: 周泽凯; 周泽楷 (corrected by Ody); ody@x.example\n"
    assert "- Also known as: 周泽凯\n" in facts.names_not_addresses("people/ody.md", page)
