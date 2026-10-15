"""The owner's languages come from the owner's own words: mail they sent, without
the thread they quote, and session messages they typed, never a program's prompt."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import languages
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import RemError, read_json, write_json

OWNER = ["aaron@openonion.ai"]
NOW = datetime.now(timezone.utc)


def mail(root, rows):
    """rem.db messages with archived bodies, as the index holds them."""
    db = sqlite3.connect(root / ".state" / "rem.db")
    db.execute("create table messages (id text primary key, source text, thread text, sender text, recipients text,"
               " time text, subject text, body_path text, body_line integer)")
    for n, (sender, body) in enumerate(rows):
        path = f"mail/messages/gmail/{n:04d}.json"
        (root / ".state" / path).parent.mkdir(parents=True, exist_ok=True)
        (root / ".state" / path).write_text(json.dumps({"body": body}))
        db.execute("insert into messages values (?, 'gmail', 't', ?, '[]', '', '', ?, null)", (f"gmail:{n}", sender, path))
    db.commit()
    db.close()


def transcript(home, rows):
    """A Claude Code session file: what the user typed (cli) and what a program sent (sdk)."""
    folder = home / "projects" / "-work"
    folder.mkdir(parents=True)
    lines = []
    for n, (entrypoint, text) in enumerate(rows):
        lines.append(json.dumps({"type": "user", "sessionId": "s1", "cwd": "/work", "entrypoint": entrypoint,
                                 "timestamp": (NOW - timedelta(minutes=len(rows) - n)).isoformat(),
                                 "uuid": f"u{n}", "message": {"role": "user", "content": text}}))
    (folder / "s1.jsonl").write_text("\n".join(lines) + "\n")
    return {"id": "claude-code", "kind": "claude-code", "root": str(home / "projects"), "enabled": True,
            "consented": True, "since": (NOW - timedelta(days=5)).isoformat(), "project": None}


@pytest.fixture
def notebook(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    (root / "people" / "aaron.md").write_text("# Aaron\n\n## Facts\n- Language: Unknown\n")
    write_json(root / ".state" / "map.json", {"owner": {"record": "people/aaron.md", "addresses": OWNER}})
    return root


def test_mixed_chinese_and_english_owner_is_detected_from_own_words_only(notebook, tmp_path):
    mail(notebook, [
        ("aaron@openonion.ai", "From: Aaron <aaron@openonion.ai>\nTo: dora@x.com\n\n你好，明天下午我们再聊一下这个合同的细节吧。"),
        ("Aaron@OpenOnion.ai", "Hi Dora, the contract looks good, let's sign it next week.\n\n"
                               "On Mon, 12 Oct 2026, Dora wrote:\n> 我们这边已经准备好了所有的文件和材料"),
        ("aaron@openonion.ai", "收到，谢谢你帮忙安排这次会议和后续的事情。"),
        ("dora@x.com", "今天天气很好我们去公园散步吧然后吃晚饭怎么样"),   # someone else's words
        ("dora@x.com", "这是别人的邮件不是你写的内容所以不应该算进去"),
    ])
    subscription = transcript(tmp_path / "claude", [
        ("cli", "帮我把这个页面的语言切换功能做完，然后跑一下测试"),
        ("cli", "please fix the failing test in the reader and push nothing"),
        ("sdk-cli", "Ты агент. Запланируй ровно одну статью на неделю и опубликуй её сейчас же"),
        ("sdk-py", "Ты агент. Проверь почту и ответь на все письма автоматически пожалуйста"),
        ("sdk-py", "Ты агент. Ещё одно автоматическое задание без участия пользователя вообще"),
    ])
    from connectonion.rem.investigate import _session_window
    _session_window(subscription, "sessions", None, notebook)

    found = languages.detect(notebook, OWNER)
    assert found["messages"] == 5 and "ru" not in found["shares"]
    assert found["languages"] == ["zh", "en"] and found["shares"] == {"zh": 0.6, "en": 0.4}


def test_quoted_thread_and_headers_are_not_the_owners_words():
    body = ("From: Aaron <a@x.com>\nSubject: Re: plan\n\nSounds good.\n\n"
            "在 2026年10月12日，Dora 写道：\n> 我们下周见面讨论吧")
    assert languages.own_words(body).strip() == "Sounds good."
    assert languages.language_of("ok") is None                       # too short to vote
    assert languages.language_of("今日はいい天気ですね、散歩に行きましょう") == "ja"   # kana outrank shared Han


def test_refresh_keeps_detection_on_the_map_and_fills_an_empty_language_fact(notebook):
    mail(notebook, [("aaron@openonion.ai", "我们明天再讨论一下这个项目的进展吧")] * 3
         + [("aaron@openonion.ai", "Let's discuss the project progress tomorrow then")])
    assert languages.refresh(notebook)["languages"] == ["zh", "en"]
    assert read_json(notebook / ".state" / "map.json", {})["owner"]["languages"]["shares"] == {"zh": 0.75, "en": 0.25}
    assert "- Language: 中文, English (detected from your own mail and sessions)" in \
        (notebook / "people" / "aaron.md").read_text()


def test_a_language_fact_already_written_is_left_alone(notebook):
    (notebook / "people" / "aaron.md").write_text("# Aaron\n\n## Facts\n- Language: English and Chinese [2]\n")
    mail(notebook, [("aaron@openonion.ai", "我们明天再讨论一下这个项目的进展吧")])
    languages.refresh(notebook)
    assert "- Language: English and Chinese [2]" in (notebook / "people" / "aaron.md").read_text()


def test_the_owner_can_set_languages_and_unset_falls_back_to_detected(notebook):
    mail(notebook, [("aaron@openonion.ai", "我们明天再讨论一下这个项目的进展吧")])
    languages.refresh(notebook)
    assert languages.owner_languages(notebook)["languages"] == ["zh"]
    assert languages.owner_languages(notebook)["from"].startswith("detected")
    set_config(notebook, ["languages", "zh,en,ja"])
    assert read_config(notebook)["languages"] == ["zh", "en", "ja"]
    chosen = languages.owner_languages(notebook)
    assert chosen["languages"] == ["zh", "en", "ja"] and chosen["from"].startswith("set")
    with pytest.raises(RemError, match="languages"):
        set_config(notebook, ["languages", "zh,../x"])
    set_config(notebook, ["languages", ""])
    assert languages.owner_languages(notebook)["languages"] == ["zh"]


def test_config_shows_your_languages_and_where_they_came_from(notebook):
    set_config(notebook, ["languages", "zh,en"])
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook), "--json", "config"])
    assert result.exit_code == 0, result.output
    shown = json.loads(result.output)["data"]["your languages"]
    assert shown["languages"] == ["zh", "en"] and shown["from"].startswith("set")


def test_the_snapshot_gives_the_menu_your_languages_the_page_language_and_theirs(notebook):
    from connectonion.rem.reader import snapshot
    (notebook / "people" / "dora.md").write_text(
        "# Dora\n\n## Facts\n- Language: Japanese and English [1]\n\n## Who they are\nDora runs the Tokyo office.\n")
    (notebook / "people" / "li.md").write_text("# 李雷\n\n## Facts\n- Language: Chinese\n\n## Who they are\n李雷是公司的创始人，负责产品和融资。\n")
    set_config(notebook, ["languages", "zh,en"])
    data = snapshot(notebook)
    rows = {r["path"]: r for r in data["records"]}
    assert data["your_languages"] == ["zh", "en"]
    assert rows["people/dora.md"]["written_in"] == "en" and rows["people/dora.md"]["speaks"] == ["ja", "en"]
    assert rows["people/li.md"]["written_in"] == "zh" and rows["people/li.md"]["speaks"] == ["zh"]


def test_the_reader_offers_your_languages_first_then_theirs_then_other():
    from connectonion.rem.reader import TEMPLATE
    page = TEMPLATE.read_text(encoding="utf-8")
    bar = page[page.index("function languageBar"):page.index("async function readIn")]
    assert bar.index("yours.map") < bar.index("theirs.map") < bar.index('"Other…"')
    assert "tag !== r.written_in" in bar
