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
    from connectonion.rem.store_build import SCHEMA, SCHEMA_VERSION

    db = sqlite3.connect(root / ".state" / "rem.db")
    db.executescript(SCHEMA)
    db.execute("insert into meta (key, value) values ('schema_version', ?)", (SCHEMA_VERSION,))
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
        ("aaron@openonion.ai", "From: Aaron <aaron@openonion.ai>\nTo: briar@x.com\n\n你好，明天下午我们再聊一下这个合同的细节吧。"),
        ("Aaron@OpenOnion.ai", "Hi Briar, the contract looks good, let's sign it next week.\n\n"
                               "On Mon, 12 Oct 2026, Briar wrote:\n> 我们这边已经准备好了所有的文件和材料"),
        ("aaron@openonion.ai", "收到，谢谢你帮忙安排这次会议和后续的事情。"),
        ("briar@x.com", "今天天气很好我们去公园散步吧然后吃晚饭怎么样"),   # someone else's words
        ("briar@x.com", "这是别人的邮件不是你写的内容所以不应该算进去"),
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
            "在 2026年10月12日，Briar 写道：\n> 我们下周见面讨论吧")
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
    (notebook / "people" / "briar.md").write_text(
        "# Briar\n\n## Facts\n- Language: Japanese and English [1]\n\n## Who they are\nBriar runs the Tokyo office.\n")
    (notebook / "people" / "li.md").write_text("# 李雷\n\n## Facts\n- Language: Chinese\n\n## Who they are\n李雷是公司的创始人，负责产品和融资。\n")
    set_config(notebook, ["languages", "zh,en"])
    data = snapshot(notebook)
    rows = {r["path"]: r for r in data["records"]}
    assert data["your_languages"] == ["zh", "en"]
    assert rows["people/briar.md"]["written_in"] == "en" and rows["people/briar.md"]["speaks"] == ["ja", "en"]
    assert rows["people/li.md"]["written_in"] == "zh" and rows["people/li.md"]["speaks"] == ["zh"]


def test_the_reader_offers_your_languages_first_then_theirs_then_other():
    from connectonion.rem.reader import TEMPLATE
    page = TEMPLATE.read_text(encoding="utf-8")
    bar = page[page.index("function languageBar"):page.index("async function readIn")]
    assert bar.index("yours.map") < bar.index("theirs.map") < bar.index('"Other…"')
    assert "tag !== r.written_in" in bar


def test_existing_notebook_detects_owner_languages_without_writing(tmp_path, monkeypatch):
    from connectonion.rem.reader import snapshot

    root = tmp_path / "rem"
    prepare(root)
    owner = root / "people" / "avery-lin.md"
    owner.write_text("# Avery Lin\n\n## Facts\n- Language: Unknown\n")
    path = root / ".state" / "map.json"
    write_json(path, {"owner": {"record": "people/avery-lin.md", "addresses": ["avery@example.com"]}})
    mail(root, [("avery@example.com", "Please send the revised pilot proposal tomorrow.")] * 3
         + [("AVERY@example.com", "我们明天再讨论一下这个项目的进展吧"),
            ("mara@example.com", "今日はいい天気ですね、散歩に行きましょう")])
    original = {file: file.read_bytes() for file in root.rglob("*") if file.is_file()}
    detected = languages.owner_languages(root)
    assert detected == {"languages": ["en", "zh"], "detected": ["en", "zh"], "shares": {"en": 0.75, "zh": 0.25},
                        "from": "detected from your own mail and sessions", "english_terms": []}
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    assert snapshot(root)["your_languages"] == ["en", "zh"]
    assert {file: file.read_bytes() for file in root.rglob("*") if file.is_file()} == original
    set_config(root, ["languages", "ja,en"])
    monkeypatch.setattr(languages, "detect", lambda *args: pytest.fail("Configured languages must come first"))
    assert languages.owner_languages(root)["languages"] == ["ja", "en"]


def test_saved_empty_detection_is_not_repeated(tmp_path, monkeypatch):
    prepare(tmp_path)
    write_json(tmp_path / ".state" / "map.json", {"owner": {"languages": {"languages": [], "shares": {}}}})
    monkeypatch.setattr(languages, "detect", lambda *args: pytest.fail("Saved detection should be reused"))
    assert languages.owner_languages(tmp_path)["languages"] == []


@pytest.fixture
def glossary_notebook(tmp_path):
    prepare(tmp_path)
    (tmp_path / 'people/avery.md').write_text('# Avery\n\n## Facts\n- Language: Unknown\n')
    write_json(tmp_path / '.state/map.json', {'owner': {'record': 'people/avery.md',
                                                      'addresses': ['avery@example.com']}})
    return tmp_path


def test_english_terms_count_distinct_chinese_owner_messages_only(glossary_notebook):
    from connectonion.rem.investigate import SESSION_WINDOW_VERSION

    root = glossary_notebook
    mail(root, [
        ('AVERY@example.com', '请帮我检查这个capstone的PR，然后查看repo和agent。Mira提到了secretword。'),
        ('avery@example.com', '我们明天再看一下capstone的pr和repo，Mira也提到了secretword。'),
        ('avery@example.com', '这次只发一次invoice invoice invoice，等待后续确认。'),
        ('avery@example.com', '这次只发一次invoice invoice invoice，等待后续确认。'),
        ('avery@example.com', 'Please review this draft and deploy the release with the SDK.'),
        ('avery@example.com', 'Please review this draft again and deploy the new release with the SDK.'),
        ('mira@example.com', '我们需要review这份draft然后deploy这次release，检查SDK和invoice。'),
        ('mira@example.com', '我们明天review这份draft然后deploy这次release，再检查SDK和invoice。'),
        ('avery@example.com', '收到，谢谢，我们明天见面再聊吧。\nOn Tuesday, Mira wrote:\n> review draft SDK invoice'),
        ('avery@example.com', '好的，谢谢，我们下午见面再谈吧。\n在 昨天下午，Mira 写道：\n> review draft SDK invoice'),
        ('avery@example.com', '请检查preview和skillset，还有agentic和my_repo以及api2，稍后再聊。'),
        ('avery@example.com', '我们明天再检查preview和skillset，还有agentic和my_repo以及api2。'),
    ])
    write_json(root / '.state/session-windows/typed.json', {'version': SESSION_WINDOW_VERSION, 'items': [
        {'role': 'user', 'source': 'session:1', 'text': '请把这个agent的demo再给我演示一下，我们下午讨论。'},
        {'role': 'user', 'source': 'session:2', 'text': '我们明天再看demo的效果，讨论一下后续的安排。'},
        {'role': 'assistant', 'text': '请检查review draft SDK invoice，我们之后再讨论。'},
    ]})
    assert languages.english_terms(root, ['avery@example.com']) == ['agent', 'capstone', 'demo', 'pr', 'repo']


def test_glossary_refresh_is_saved_and_reused_with_configured_languages(glossary_notebook, monkeypatch):
    root = glossary_notebook
    mail(root, [('avery@example.com', '我们今天先看capstone项目，然后讨论下一步。'),
                ('avery@example.com', '我们明天再看capstone项目，然后决定后续安排。')])
    assert languages.refresh(root)['english_terms'] == ['capstone']
    assert read_json(root / '.state/map.json', {})['owner']['languages']['english_terms'] == ['capstone']
    monkeypatch.setattr(languages, 'english_terms', lambda *args: pytest.fail('Saved glossary should be reused'))
    assert languages.owner_languages(root)['english_terms'] == ['capstone']
    set_config(root, ['languages', 'en,zh'])
    assert languages.owner_languages(root)['english_terms'] == ['capstone']


@pytest.mark.parametrize('saved_languages', [None, {'languages': ['zh'], 'shares': {'zh': 1}}])
def test_glossary_fallback_reads_old_maps_without_writing(glossary_notebook, saved_languages):
    root = glossary_notebook
    path = root / '.state/map.json'
    report = read_json(path, {})
    if saved_languages is not None:
        report['owner']['languages'] = saved_languages
        write_json(path, report)
    mail(root, [('avery@example.com', '我们今天先看PR，然后再讨论这个项目的细节。'),
                ('avery@example.com', '我们明天再看pr，然后决定这个项目的后续安排。')])
    original = path.read_bytes()
    assert languages.owner_languages(root)['english_terms'] == ['pr']
    assert path.read_bytes() == original


def test_empty_saved_glossary_is_not_recomputed(glossary_notebook, monkeypatch):
    root = glossary_notebook
    languages.refresh(root)
    monkeypatch.setattr(languages, 'english_terms', lambda *args: pytest.fail('Saved empty glossary should be reused'))
    assert languages.owner_languages(root)['english_terms'] == []
