"""An upgraded notebook shows its WeChat people right away, not after a night run (#3368).

Found on the owner's notebook: 1,200 WeChat pages made by an older `co rem map` carried no chat activity and no
onboarding record, because only the night wrote them. So the first day of the release showed every People row as
"—", no 微信 mark, no folds, and status said "never mapped". Fixtures always start with that data, which is why
every test passed. These tests start from the old state. Invented people only.
"""

from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import chat, onboard
from connectonion.rem.files import Notebook, read_json, state_path

SUBS = {"wechat": {"id": "wechat", "kind": "wechat", "enabled": True, "consented": True}}
ROWS = [
    {"address": "wxid_quinn", "name": "Quinn Harbour", "mails": 6, "sent": 3, "received": 3, "friend": True,
     "remark": True, "last": "2026-11-20T10:00:00+00:00", "last_mine": False, "n90": 6},
    {"address": "wxid_ines", "name": "Ines Vale", "mails": 0, "sent": 0, "received": 0, "friend": True, "remark": True},
    {"address": "wxid_theo", "name": "Theo Marsh", "mails": 0, "sent": 0, "received": 0, "friend": True, "remark": False},
]


def _old_map(root):
    """The rc14 state: pages for each WeChat contact, made by a map that recorded nothing else."""
    book = Notebook(root)
    for row in ROWS:
        book.stub_person(f"people/{row['address'][5:]}.md", row["name"], [row["address"]])
    return book


def _source(monkeypatch, rows=ROWS):
    monkeypatch.setattr("connectonion.rem.service.subscriptions", lambda root: SUBS)
    monkeypatch.setattr("connectonion.rem.chat.wechat_people", lambda *a, **k: [{**r, "kind": "wechat"} for r in rows])


def _pages(root):
    return sorted(p.relative_to(root).as_posix() for p in (root / "people").glob("*.md"))


def test_one_page_build_fills_activity_the_record_and_the_queue_for_pages_an_older_map_made(tmp_path, monkeypatch):
    _old_map(tmp_path)
    _source(monkeypatch)
    before = _pages(tmp_path)
    assert onboard.activity(tmp_path) == {} and onboard.summary(tmp_path, "wechat")["mapped_at"] == "earlier"
    from connectonion.rem.reader import snapshot
    data = snapshot(tmp_path, local=True)
    assert len(data["chat_activity"]) == 1                      # Quinn, the one with chats
    record, = data["chat_activity"]
    assert "Quinn" in Notebook(tmp_path).read(record)
    done = read_json(state_path(tmp_path, onboard.STATE), {})["wechat"]
    assert done["backfilled"] is True and done["mapped_at"]
    asked = read_json(state_path(tmp_path, onboard.ASKED), {})
    assert {entry["rank"] for entry in asked.values()} == {0, 1, 2}      # chats, named friend, the rest
    assert sorted(record for record, entry in asked.items() if entry["material"] is False) == sorted(
        r for r in before if "quinn" not in r)                         # friends with nothing to read rest
    assert _pages(tmp_path) == before                                   # a page build makes no pages


def test_the_backfill_runs_once(tmp_path, monkeypatch):
    _old_map(tmp_path)
    calls = []
    _source(monkeypatch)
    real = onboard.rows
    monkeypatch.setattr(onboard, "rows", lambda *a, **k: calls.append(1) or real(*a, **k))
    assert onboard.backfill(tmp_path) == ["wechat"]
    assert onboard.backfill(tmp_path) == [] and len(calls) == 1


def test_a_notebook_without_chat_pages_never_reads_wechat_on_a_page_build(tmp_path, monkeypatch):
    Notebook(tmp_path).stub_person("people/mara.md", "Mara Ostrowski", ["mara@fernhill.example"],
                                   email="mara@fernhill.example")
    monkeypatch.setattr("connectonion.rem.service.subscriptions", lambda root: SUBS)
    monkeypatch.setattr("connectonion.rem.chat.wechat_people", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    assert onboard.backfill(tmp_path) == []


def test_co_rem_map_leaves_the_same_state_the_night_does(tmp_path, monkeypatch):
    _old_map(tmp_path)
    _source(monkeypatch)
    result = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), "map", "people", "--source", "wechat"])
    assert result.exit_code == 0, result.output
    assert onboard.activity(tmp_path)                                    # activity written
    assert read_json(state_path(tmp_path, onboard.STATE), {})["wechat"]["mapped_at"]
    assert read_json(state_path(tmp_path, onboard.ASKED), {})            # the queue knows the pages


def test_status_counts_the_pages_a_source_already_holds(tmp_path, monkeypatch):
    _old_map(tmp_path)
    monkeypatch.setattr("connectonion.rem.service.subscriptions", lambda root: SUBS)
    done = onboard.summary(tmp_path, "wechat")
    assert (done["mapped_at"], done["pages"]) == ("earlier", 3)
    # A one-word alias on a mail page is not a WeChat id.
    Notebook(tmp_path).stub_person("people/mara.md", "Mara Ostrowski", ["Ostrowski", "mara@fernhill.example"],
                                   email="mara@fernhill.example")
    assert onboard.summary(tmp_path, "wechat")["pages"] == 3


def test_a_name_needs_a_letter_digit_or_cjk():
    for junk in (".", "...", "^ ^", "。", "ㅤ", "ㅤㅤ", "–", "~(^_^)~", "", "  "):
        assert not chat.usable_name(junk), repr(junk)
    for good in ("Quinn", "张梦耀", "R.S", "A1", "Ivara黄熙钰", "😀 Ody"):
        assert chat.usable_name(good), good


def test_a_junk_nickname_falls_back_to_the_remark_then_a_placeholder_never_the_raw_id():
    assert chat.wechat_title("wxid_abcd1234", "Quinn Harbour", "...") == "Quinn Harbour"
    assert chat.wechat_title("wxid_abcd1234", "", "Theo") == "Theo"
    title = chat.wechat_title("wxid_abcd1234", "", "^ ^")
    assert title.startswith("微信好友（无名字") and "wxid_abcd1234" not in title and "1234" in title
    assert chat.wechat_title("wxid_abcd1234", "", "") == ""            # no name at all: left out, as before


def test_a_page_titled_by_punctuation_is_retitled_on_the_next_map_keeping_its_handle(tmp_path, monkeypatch):
    book = Notebook(tmp_path)
    book.stub_person("people/dot.md", "^ ^", ["wxid_dot0042"])
    _source(monkeypatch, [{"address": "wxid_dot0042", "name": chat.wechat_title("wxid_dot0042", "", "^ ^"),
                           "mails": 0, "sent": 0, "received": 0, "friend": True, "remark": False}])
    out = onboard.onboard(tmp_path, "wechat", SUBS["wechat"], 30)["people"]
    assert out["retitled"] == ["people/dot.md"]
    page = book.read("people/dot.md")
    assert page.startswith("# 微信好友（无名字") and "wxid_dot0042" in page


def test_no_person_page_is_left_titled_without_a_letter_digit_or_cjk(tmp_path, monkeypatch):
    # The detector: after a map, every person title has something to read.
    book = Notebook(tmp_path)
    book.stub_person("people/dot.md", "。", ["wxid_dot0042"])
    _source(monkeypatch, [{"address": "wxid_dot0042", "name": chat.wechat_title("wxid_dot0042", "", "。"),
                           "mails": 0, "sent": 0, "received": 0, "friend": True, "remark": False}])
    onboard.onboard(tmp_path, "wechat", SUBS["wechat"], 30)
    assert all(chat.usable_name(person["title"]) for person in book.people())


def test_the_backfill_also_retitles_punctuation_titles_without_waiting_for_a_map(tmp_path, monkeypatch):
    # rc17 on the owner's notebook: the backfill fixed activity but left 25 "." / "^ ^" titles until the next map.
    book = Notebook(tmp_path)
    book.stub_person("people/caret.md", "^ ^", ["wxid_caret"])
    rows = [{"address": "wxid_caret", "name": "Wren Lake", "mails": 2, "sent": 1, "received": 1, "friend": True,
             "remark": True, "last": "2026-11-20T10:00:00+00:00", "last_mine": True, "n90": 2}]
    _source(monkeypatch, rows)
    assert onboard.backfill(tmp_path) == ["wechat"]
    assert book.read("people/caret.md").splitlines()[0] == "# Wren Lake"
    assert "wxid_caret" in book.read("people/caret.md")          # the handle is kept


def test_a_one_character_nickname_gives_way_to_the_remark(tmp_path, monkeypatch):
    # 33 one-character titles ("谢") on the owner's notebook: when the owner named the contact, use his name.
    book = Notebook(tmp_path)
    book.stub_person("people/xie.md", "谢", ["wxid_xie"])
    book.stub_person("people/solo.md", "林", ["wxid_solo"])
    rows = [{"address": "wxid_xie", "name": "谢明远", "mails": 1, "sent": 1, "received": 0, "friend": True,
             "remark": True},
            {"address": "wxid_solo", "name": "林", "mails": 1, "sent": 0, "received": 1, "friend": True,
             "remark": False}]
    _source(monkeypatch, rows)
    onboard.backfill(tmp_path)
    assert book.read("people/xie.md").splitlines()[0] == "# 谢明远"
    assert book.read("people/solo.md").splitlines()[0] == "# 林"     # no remark: the one character stays


def test_activity_keeps_the_earliest_chat_and_a_one_line_preview(tmp_path):
    """The person header reads these before any investigation (#3372): since when, and what was last said."""
    from connectonion.rem import onboard
    from connectonion.rem.chat import preview_line
    from connectonion.rem.files import read_json, state_path
    onboard.record_activity(tmp_path, [{"address": "wxid_wren", "last": "2026-11-20T09:00:00+00:00", "last_mine": False,
                                        "n90": 3, "sent": 1, "received": 2, "first": "2024-03-05T09:00:00+00:00",
                                        "preview": preview_line("See you\n at   the harbour [1] [personal]")}])
    entry = read_json(state_path(tmp_path, onboard.ACTIVITY), {})["wxid_wren"]
    assert entry["first"].startswith("2024-03-05")
    # One line, and no bracket the reader would take for a citation or a privacy mark.
    assert entry["preview"] == "See you at the harbour 1 personal"
    assert len(preview_line("字" * 200)) == 80 and preview_line("字" * 200).endswith("…")
