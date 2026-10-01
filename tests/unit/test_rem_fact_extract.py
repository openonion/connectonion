"""Facts read from the material with no model, and kept when the model drops them (#2068)."""

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


def test_the_signature_block_is_handed_over_for_role_and_company():
    rows = extract([mail("gmail:a1", "2026-08-04T01:00:00+00:00", SIGNED)], HANDLES)
    block = found(rows, "Signature")[0]["value"]
    assert "Head of Data Platform | Harbour Analytics" in block and "Thanks" not in block


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


def test_first_and_last_contact_come_from_the_dates_of_the_messages_either_way():
    rows = extract([mail("gmail:a1", "2026-08-04T01:00:00+00:00", "hi"),
                    mail("gmail:a2", "2026-09-10T01:00:00+00:00", "ok", role="user", speaker="Alex <a@r.example>")],
                   HANDLES)
    assert found(rows, "First contact")[0]["value"] == "2026-08-04"
    assert found(rows, "Last contact")[0]["value"] == "2026-09-10"
    assert found(rows, "Last contact")[0]["source"] == "gmail:a2"


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
    assert "- [2] gmail:a1 — 2026-08-04, high; read by co rem from the message" in kept
    assert {r["field"] for r in restored} == {"Phone"}           # no Links line: nothing to fill
    assert facts.keep_extracted("people/mia.md", kept, rows)[1] == []
    upgraded, restored = facts.keep_extracted("people/mia.md", facts.upgrade("people/mia.md", PAGE), rows)
    assert {r["field"] for r in restored} == {"Phone", "Links", "First contact"}
    assert "- First contact: 2026-08-04 [2]" in upgraded and "- Last contact: 2026-09-10 [1]" in upgraded


def test_a_phone_already_on_the_page_in_another_format_is_not_added_twice():
    page = PAGE.replace("- Phone: Unknown", "- Phone: +61 (2) 5550-0142 [1]; +61 400 555 019 (mobile) [1]")
    rows = [r for r in extract([mail("gmail:a1", "2026-08-04T01:00:00+00:00", SIGNED)], HANDLES)
            if r["field"] == "Phone"]
    assert facts.keep_extracted("people/mia.md", page, rows) == (page, [])


def test_a_date_the_model_corrected_is_not_overwritten():
    rows = [{"field": "Last contact", "value": "2026-09-01", "qualifier": "", "source": "gmail:z", "date": "2026-09-01"}]
    assert facts.keep_extracted("people/mia.md", PAGE, rows) == (PAGE, [])


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
    from connectonion.rem.config import prepare
    monkeypatch.setattr("connectonion.rem.runner.check_skill", lambda root, stage: None)
    root = tmp_path / "rem"
    prepare(root)
    notebook = inv.Notebook(root)
    notebook.stub_person("people/vern.md", "Vern Chan", ["vern"], email="vern.chan@unsw.edu.au")
    original = notebook.read("people/vern.md")
    seen = {}

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
    page = notebook.read("people/vern.md")
    assert "- Phone: +61 412 000 111 (mobile) [1]" in page        # same message, same number
    assert result["facts"]["after"]["filled"] > result["facts"]["before"]["filled"]
    assert result["facts"]["extracted"] >= 3                        # email, phone, first and last contact


def test_a_new_fact_without_a_citation_is_refused_but_a_mapped_address_is_not():
    original = PAGE
    items = [{"role": "page", "record": "people/mia.md"}, {"source": "gmail:a2"}]
    candidate = PAGE.replace("- Phone: Unknown", "- Phone: +61 2 5550 0142")
    errors = validate("people/mia.md", candidate, original, items)
    assert any("Fact without a citation: Phone" in e for e in errors)
    assert not any("Email" in e for e in errors if e.startswith("Fact without"))
