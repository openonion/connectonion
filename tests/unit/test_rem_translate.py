"""A page read in another language: made once by co ai, cached by the page's hash,
made again when the page changes, and never written over the page."""

import hashlib
import json

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import translate as tr
from connectonion.rem.config import prepare
from connectonion.rem.files import RemError

PAGE = "# Alice Chen\n\n## Facts\n- Role: founder [1]\n\n## Sources\n- [1] gmail:abc — intro mail\n"
CHINESE = "# Alice Chen\n\n## Facts\n- Role: 创始人 [1]\n\n## Sources\n- [1] gmail:abc — 介绍邮件\n"


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    prepare(tmp_path)
    (tmp_path / "people" / "alice-chen.md").write_text(PAGE)
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("", ""))
    return tmp_path


def model(answer, calls):
    def run(workspace, prompt, config, stage):
        calls.append({"page": (workspace / "page.md").read_text(), "prompt": prompt, "stage": stage})
        (workspace / "translation.md").write_text(answer)
        return {"outcome": "natural"}
    return run


def test_a_translation_is_made_once_and_then_read_from_the_cache(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    assert tr.translate(notebook, "people/alice-chen.md", "zh") == CHINESE
    assert tr.translate(notebook, "people/alice-chen.md", "zh") == CHINESE
    assert len(calls) == 1 and calls[0]["page"] == PAGE and "`zh`" in calls[0]["prompt"]
    assert "a quote stays in its original language" in calls[0]["prompt"]
    assert (notebook / "people" / "alice-chen.md").read_text() == PAGE
    saved = notebook / ".state" / "translations" / "zh" / "people" / "alice-chen.md"
    assert saved.read_text().startswith("<!-- co rem translation of people/alice-chen.md sha256:")
    assert tr.cached_languages(notebook, "people/alice-chen.md") == {"zh": CHINESE}


def test_a_changed_page_makes_its_translation_stale_and_it_is_made_again(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    tr.translate(notebook, "people/alice-chen.md", "zh")
    (notebook / "people" / "alice-chen.md").write_text(PAGE.replace("founder", "CEO"))
    assert tr.cached(notebook, "people/alice-chen.md", "zh") is None
    assert tr.cached_languages(notebook, "people/alice-chen.md") == {}
    tr.translate(notebook, "people/alice-chen.md", "zh")
    assert len(calls) == 2 and "CEO" in calls[1]["page"]


@pytest.mark.parametrize('old_version', [None, 1])
def test_an_old_prompt_cache_is_stale_and_regenerated(notebook, monkeypatch, old_version):
    from connectonion.rem.files import atomic_write
    if old_version is None:
        old_digest = hashlib.sha256(PAGE.encode('utf-8')).hexdigest()
    else:
        with monkeypatch.context() as old_prompt:
            old_prompt.setattr(tr, 'PROMPT_VERSION', old_version)
            old_digest = tr.digest(PAGE)
    atomic_write(tr.translation_path(notebook, 'people/alice-chen.md', 'zh'),
                 f'<!-- co rem translation of people/alice-chen.md sha256:{old_digest} -->\n' + CHINESE)
    assert tr.cached(notebook, 'people/alice-chen.md', 'zh') is None
    assert tr.cached_languages(notebook, 'people/alice-chen.md') == {}
    calls = []
    monkeypatch.setattr('connectonion.rem.runner.run_task', model(CHINESE, calls))
    assert tr.translate(notebook, 'people/alice-chen.md', 'zh') == CHINESE
    assert tr.cached(notebook, 'people/alice-chen.md', 'zh') == CHINESE
    assert len(calls) == 1


def test_a_translation_that_breaks_headings_or_sources_is_not_cached(notebook, monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE.replace("## Facts", "## 事实"), []))
    with pytest.raises(RemError, match="headings"):
        tr.translate(notebook, "people/alice-chen.md", "zh")
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE.replace(" [1]\n\n", "\n\n"), []))
    with pytest.raises(RemError, match="source ids"):
        tr.translate(notebook, "people/alice-chen.md", "zh")
    assert tr.cached(notebook, "people/alice-chen.md", "zh") is None


def test_a_translated_marker_is_refused_because_the_reader_would_misread_it(notebook, monkeypatch):
    """Codex turned `Nothing open as of 2026-09-29` into Chinese and the reader
    showed a closed conversation as an open thread (live check, 2026-10-15)."""
    page = PAGE + "\n## Open threads\nNothing open as of 2026-09-29; the role was filled [1].\n"
    (notebook / "people" / "alice-chen.md").write_text(page)
    translated = CHINESE + "\n## Open threads\n截至 2026-09-29，没有待处理事项 [1]。\n"
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(translated, []))
    with pytest.raises(RemError, match="Nothing open as of"):
        tr.translate(notebook, "people/alice-chen.md", "zh")
    kept = CHINESE + "\n## Open threads\nNothing open as of 2026-09-29；职位已招满 [1]。\n"
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(kept, []))
    assert tr.translate(notebook, "people/alice-chen.md", "zh") == kept


def test_the_investigation_stamp_is_never_sent_and_comes_back_as_written(notebook, monkeypatch):
    """Codex translated the stamp's label, and the reader lost the page's status."""
    stamp = "Investigation: mapped 2026-10-10 · investigated 2026-10-10 (outlook)"
    (notebook / "people" / "alice-chen.md").write_text(PAGE + "\n" + stamp + "\n")
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    assert tr.translate(notebook, "people/alice-chen.md", "zh") == CHINESE + "\n" + stamp + "\n"
    assert "Investigation:" not in calls[0]["page"]


def test_a_runner_that_cannot_run_is_named_before_any_model_call(notebook, monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("Codex is not signed in", "codex login"))
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a: pytest.fail("model called"))
    with pytest.raises(RemError, match="codex login"):
        tr.translate(notebook, "people/alice-chen.md", "zh")


def test_a_language_is_a_tag_not_a_path(notebook):
    for bad in ("../people", "zh/../../x", "", "中文"):
        with pytest.raises(RemError, match="language"):
            tr.translation_path(notebook, "people/alice-chen.md", bad)


def test_the_snapshot_carries_only_current_translations(notebook, monkeypatch):
    from connectonion.rem.reader import snapshot
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, []))
    tr.translate(notebook, "people/alice-chen.md", "zh")
    record = next(r for r in snapshot(notebook)["records"] if r["path"] == "people/alice-chen.md")
    assert record["translations"] == {"zh": CHINESE} and record["text"] == PAGE


def test_cli_translate_prints_the_translation(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook), "--json", "translate",
                                      "people/alice-chen.md", "--to", "zh"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"] == CHINESE
    bad = CliRunner().invoke(app, ["rem", "--root", str(notebook), "--json", "translate",
                                   "people/alice-chen.md", "--to", "../x"])
    assert bad.exit_code != 0 and "language" in bad.output
    assert len(calls) == 1


@pytest.mark.parametrize('quote', ['“Please send the signed draft”', '"Please send the signed draft"',
                                   '「Please send the signed draft」', '> Please send the signed draft'])
def test_translate_keeps_quoted_evidence_exactly(quote):
    original = '# Avery Lin\n\nA request arrived:\n' + quote + '\n'
    translated = '# Avery Lin\n\n收到请求：\n' + quote + '\n'
    assert tr.checked(original, translated) == translated
    for broken in (translated.replace('signed draft', '签名草稿'), translated.replace(quote, '')):
        with pytest.raises(RemError, match='quoted passage'):
            tr.checked(original, broken)


def test_translate_prompt_names_all_evidence_quote_forms():
    prompt = tr.prompt('zh')
    assert '“…”, "…", 「…」' in prompt
    assert '> blockquote lines) exactly as written, in its original language' in prompt
    assert 'translate only the surrounding prose' in prompt


def test_translate_prompt_addresses_the_notebook_owner_as_the_reader():
    prompt = tr.prompt('zh')
    assert "the reader's own work" in prompt
    assert '"the user", "the owner" and "you"' in prompt
    assert 'second person of the target language' in prompt
    assert 'Chinese: 你; never 用户' in prompt
    assert 'Keep every quoted passage' in prompt


def test_translate_preserves_repeated_quotes_and_ignores_short_labels():
    with pytest.raises(RemError, match='quoted passage'):
        tr.checked('“signed draft” and “signed draft”', '“signed draft”')
    assert tr.checked('A "yes" label', '一个“是”标签')


def test_translate_allows_a_quote_to_lose_its_trailing_comma_in_chinese_punctuation():
    original = '# Avery Lin\n\nShe opens with “Hi Mara, thanks,” and signs off.\n'
    translated = '# Avery Lin\n\n她以“Hi Mara, thanks”开头，然后署名。\n'
    assert tr.checked(original, translated) == translated


def test_translate_prompt_lists_each_quote_to_keep():
    assert '- Please send the signed draft' in tr.prompt('zh', ['Please send the signed draft'])
    assert 'must appear unchanged' not in tr.prompt('zh')



def test_translate_prompt_keeps_date_prefix_punctuation():
    assert 'keep the ASCII colon after a leading date like `2026-10-15:`' in tr.prompt('zh')


def test_cli_backfill_skips_current_cache_and_nonrecords_and_continues(notebook, monkeypatch):
    from connectonion.rem.files import atomic_write
    calls = []
    for category, name in [('people', 'bob'), ('people', 'carol'), ('orgs', 'company'),
                           ('projects', 'launch'), ('decisions', 'format'), ('principles', 'simple'),
                           ('logs', 'run'), ('notes', 'activity'), ('knowledge', 'topic'),
                           ('skills/catalog', 'index'), ('skills/catalog', 'mail')]:
        folder = notebook / category
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (name + '.md')).write_text('# ' + name + '\n\nA source finding.\n')
    atomic_write(tr.translation_path(notebook, 'people/alice-chen.md', 'zh'),
                 '<!-- co rem translation of people/alice-chen.md sha256:' + tr.digest(PAGE) + ' -->\n' + CHINESE)

    atomic_write(tr.translation_path(notebook, 'people/carol.md', 'zh'),
                 '<!-- co rem translation of people/carol.md sha256:' + tr.digest('# Old page') + ' -->\n旧缓存')

    def translate(root, record, language):
        assert root == notebook and language == 'zh'
        calls.append(record)
        if record == 'people/bob.md':
            raise RemError('fixture translation refused')
        return 'translated prose'

    monkeypatch.setattr(tr, 'translate', translate)
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook), 'translate', '--all', '--to', 'zh'])
    assert result.exit_code == 1, result.output
    assert 'people/alice-chen.md: cached' in result.output
    assert 'people/bob.md: failed: fixture translation refused' in result.output
    assert 'people/carol.md: translated' in result.output
    assert '6 translated, 1 cached, 1 failed' in result.output
    assert calls == ['people/bob.md', 'people/carol.md', 'orgs/company.md', 'projects/launch.md',
                     'skills/catalog/mail.md', 'decisions/format.md', 'principles/simple.md']
    assert (notebook / 'people/alice-chen.md').read_text() == PAGE


def test_cli_backfill_category_and_owner_language_default(notebook, monkeypatch):
    from connectonion.rem.config import set_config
    set_config(notebook, ['languages', 'en,zh-TW,ja'])
    (notebook / 'orgs/company.md').write_text('# Company\n')
    calls = []
    monkeypatch.setattr(tr, 'translate', lambda root, record, language: calls.append((root, record, language)))
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook), '--json', 'translate', '--all', '--category', 'people'])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)['data']
    assert data['language'] == 'zh-TW' and data['translated'] == 1 and data['failed'] == 0
    assert calls == [(notebook, 'people/alice-chen.md', 'zh-TW')]
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook), 'translate', 'Alice Chen'])
    assert result.exit_code == 0, result.output
    assert calls[-1] == (notebook, 'people/alice-chen.md', 'zh-TW')


@pytest.mark.parametrize('args', [[], ['--all', 'Alice Chen'], ['Alice Chen', '--category', 'people'],
                                  ['--all', '--category', 'logs']])
def test_cli_backfill_rejects_invalid_selection_before_translating(notebook, monkeypatch, args):
    monkeypatch.setattr(tr, 'translate', lambda *a: pytest.fail('translator called'))
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook), 'translate', *args, '--to', 'zh'])
    assert result.exit_code != 0


@pytest.mark.parametrize('label', ['personal', 'sensitive'])
@pytest.mark.parametrize('broken', ['drop', 'add', 'substitute', 'move'])
def test_translation_rejects_changed_or_moved_privacy_tags(label, broken):
    original = f'# Avery Lin\n\nPrivate dates [{label}] [1].\nPublic task [1].\n'
    translated = f'# Avery Lin\n\n私密日期[{label}] [1]。\n公开任务 [1]。\n'
    if broken == 'drop':
        translated = translated.replace(f'[{label}]', '')
    elif broken == 'add':
        translated = translated.replace('公开任务', f'公开任务 [{label}]')
    elif broken == 'substitute':
        translated = translated.replace(f'[{label}]', '[sensitive]' if label == 'personal' else '[personal]')
    else:
        translated = translated.replace(f'[{label}]', '').replace('公开任务', f'公开任务 [{label}]')
    with pytest.raises(RemError, match='privacy tags'):
        tr.checked(original, translated)


def test_translation_checks_each_privacy_label_per_line_and_accepts_fullwidth_brackets():
    original = '# Avery Lin\n\nDates [personal] [1]. Follow-up [personal].\nHealth [sensitive].\n'
    translated = '# Avery Lin\n\n日期［personal］［1］。后续联系[personal]。\n健康[sensitive]。\n'
    assert tr.checked(original, translated) == translated
    # Total counts alone would miss swapping the two labels between lines.
    with pytest.raises(RemError, match='privacy tags'):
        tr.checked(original, translated.replace('后续联系[personal]', '后续联系[sensitive]')
                   .replace('健康[sensitive]', '健康[personal]'))


def test_translation_with_lost_privacy_tag_is_never_cached(notebook, monkeypatch):
    page = PAGE.replace('founder', 'founder [personal]')
    (notebook / 'people/alice-chen.md').write_text(page)
    monkeypatch.setattr('connectonion.rem.runner.run_task', model(CHINESE, []))
    with pytest.raises(RemError, match='privacy tags'):
        tr.translate(notebook, 'people/alice-chen.md', 'zh')
    assert tr.cached(notebook, 'people/alice-chen.md', 'zh') is None
