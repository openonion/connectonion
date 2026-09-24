"""The order a category run spends its minutes in (#1656)."""

from datetime import date

from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook, state_path, write_json
from connectonion.wiki.queue import last_investigated, order


def test_most_mail_first_and_never_the_owner_or_what_may_be_the_owner(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    for record, name in (("people/me.md", "Me"), ("people/ody.md", "Ody"), ("people/dora.md", "Dora"),
                         ("people/second-gmail.md", "second"), ("people/noreply.md", "noreply"),
                         ("people/tamara.md", "Tamara")):
        notebook.stub_person(record, name, [])
    tamara = notebook.read("people/tamara.md").replace(
        "Investigation: mapped", "Investigation: investigated 2026-09-22 (outlook) · mapped")
    notebook.write("people/tamara.md", tamara)
    write_json(state_path(tmp_path, "map.json"), {
        "owner": {"record": "people/me.md"},
        "possible_own_addresses": [{"record": "people/second-gmail.md"}],
        "people": [{"record": "people/ody.md", "mails": 185, "classification": "unassessed"},
                   {"record": "people/dora.md", "mails": 40, "classification": "unassessed"},
                   {"record": "people/tamara.md", "mails": 90, "classification": "unassessed"},
                   {"record": "people/second-gmail.md", "mails": 106, "classification": "unassessed"},
                   {"record": "people/noreply.md", "mails": 300, "classification": "automated candidate"}]})
    rows = order(tmp_path, "people", today=date(2026, 9, 24))
    assert [row["path"] for row in rows] == ["people/ody.md", "people/dora.md", "people/tamara.md"]
    assert rows[-1]["recent"] and rows[-1]["last_investigated"] == "2026-09-22"   # this week's page waits


def test_the_status_line_is_read_for_the_last_investigation_only():
    assert last_investigated("Investigation: mapped 2026-09-01 · not investigated yet") is None
    assert last_investigated("Investigation: investigated 2026-09-10 (gmail) · investigated 2026-09-20 (outlook)") \
        == date(2026, 9, 20)
