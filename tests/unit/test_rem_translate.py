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

PAGE = "# Avery Lin\n\n## Facts\n- Role: founder [1]\n\n## Sources\n- [1] gmail:abc — intro mail\n"
CHINESE = "# Avery Lin\n\n## Facts\n- Role: 创始人 [1]\n\n## Sources\n- [1] gmail:abc — intro mail\n"


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    prepare(tmp_path)
    (tmp_path / "people" / "avery-lin.md").write_text(PAGE)
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("", ""))
    return tmp_path


def model(answer, calls):
    def run(workspace, prompt, config, stage):
        calls.append({"page": (workspace / "page.md").read_text(), "prompt": prompt, "stage": stage})
        (workspace / "translation.md").write_text(answer.partition('## Sources')[0].rstrip() + '\n')
        return {"outcome": "natural"}
    return run


def test_a_translation_is_made_once_and_then_read_from_the_cache(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    assert tr.translate(notebook, "people/avery-lin.md", "zh") == CHINESE
    assert tr.translate(notebook, "people/avery-lin.md", "zh") == CHINESE
    assert len(calls) == 1 and calls[0]["page"] == PAGE.partition('## Sources')[0].rstrip() + '\n'
    assert "`zh`" in calls[0]["prompt"]
    assert "a quote stays in its original language" in calls[0]["prompt"]
    assert (notebook / "people" / "avery-lin.md").read_text() == PAGE
    saved = notebook / ".state" / "translations" / "zh" / "people" / "avery-lin.md"
    assert saved.read_text().startswith("<!-- co rem translation of people/avery-lin.md sha256:")
    assert tr.cached_languages(notebook, "people/avery-lin.md") == {"zh": CHINESE}


def test_a_changed_page_makes_its_translation_stale_and_it_is_made_again(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    tr.translate(notebook, "people/avery-lin.md", "zh")
    (notebook / "people" / "avery-lin.md").write_text(PAGE.replace("founder", "CEO"))
    assert tr.cached(notebook, "people/avery-lin.md", "zh") is None
    assert tr.cached_languages(notebook, "people/avery-lin.md") == {}
    tr.translate(notebook, "people/avery-lin.md", "zh")
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
    atomic_write(tr.translation_path(notebook, 'people/avery-lin.md', 'zh'),
                 f'<!-- co rem translation of people/avery-lin.md sha256:{old_digest} -->\n' + CHINESE)
    assert tr.cached(notebook, 'people/avery-lin.md', 'zh') is None
    assert tr.cached_languages(notebook, 'people/avery-lin.md') == {}
    calls = []
    monkeypatch.setattr('connectonion.rem.runner.run_task', model(CHINESE, calls))
    assert tr.translate(notebook, 'people/avery-lin.md', 'zh') == CHINESE
    assert tr.cached(notebook, 'people/avery-lin.md', 'zh') == CHINESE
    assert len(calls) == 1


def test_a_translation_that_breaks_headings_or_sources_is_not_cached(notebook, monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE.replace("## Facts", "## 事实"), []))
    with pytest.raises(RemError, match="headings"):
        tr.translate(notebook, "people/avery-lin.md", "zh")
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE.replace(" [1]\n\n", "\n\n"), []))
    with pytest.raises(RemError, match="source ids"):
        tr.translate(notebook, "people/avery-lin.md", "zh")
    assert tr.cached(notebook, "people/avery-lin.md", "zh") is None


def test_a_translated_marker_is_refused_because_the_reader_would_misread_it(notebook, monkeypatch):
    """Codex turned `Nothing open as of 2026-09-29` into Chinese and the reader
    showed a closed conversation as an open thread (live check, 2026-10-15)."""
    thread = "## Open threads\nNothing open as of 2026-09-29; the role was filled [1].\n\n"
    page = PAGE.replace('## Sources', thread + '## Sources')
    (notebook / "people" / "avery-lin.md").write_text(page)
    translated = CHINESE.replace('## Sources', '## Open threads\n截至 2026-09-29，没有待处理事项 [1]。\n\n## Sources')
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(translated, []))
    with pytest.raises(RemError, match="Nothing open as of"):
        tr.translate(notebook, "people/avery-lin.md", "zh")
    kept = CHINESE.replace('## Sources', '## Open threads\nNothing open as of 2026-09-29；职位已招满 [1]。\n\n## Sources')
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(kept, []))
    assert tr.translate(notebook, "people/avery-lin.md", "zh") == kept


def test_the_investigation_stamp_is_never_sent_and_comes_back_as_written(notebook, monkeypatch):
    """Codex translated the stamp's label, and the reader lost the page's status."""
    stamp = "Investigation: mapped 2026-10-10 · investigated 2026-10-10 (outlook)"
    (notebook / "people" / "avery-lin.md").write_text(PAGE + "\n" + stamp + "\n")
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    assert tr.translate(notebook, "people/avery-lin.md", "zh") == CHINESE + "\n" + stamp + "\n"
    assert "Investigation:" not in calls[0]["page"]


@pytest.mark.parametrize('with_stamp', [False, True])
def test_sources_and_everything_after_them_are_restored_byte_identical(notebook, monkeypatch, with_stamp):
    prose = '# Avery Lin\n\n## Facts\nA draft [12] [W3].\n'
    sources = ('## Sources\n- [12] 2026-10-20 — "Mara Ostrowski draft"  \n'
               '- [W3] https://example.com/draft — Northgate University\n\n'
               '## Source details\nKeep this label.\n\n')
    stamp = 'Investigation: mapped 2026-10-20 · investigated 2026-10-21\n' if with_stamp else ''
    (notebook / 'people/avery-lin.md').write_text(prose + '\n' + sources + stamp)
    calls = []
    translated = prose.replace('A draft', '一份草稿')
    monkeypatch.setattr('connectonion.rem.runner.run_task', model(translated, calls))
    result = tr.translate(notebook, 'people/avery-lin.md', 'zh')
    assert result == translated + '\n' + sources + stamp
    assert result[result.index('## Sources'):].encode() == (sources + stamp).encode()
    assert calls[0]['page'] == prose
    assert '## Sources' not in calls[0]['page'] and 'Investigation:' not in calls[0]['page']
    assert 'Mara Ostrowski draft' not in calls[0]['prompt']
    assert tr.cached(notebook, 'people/avery-lin.md', 'zh') == result


@pytest.mark.parametrize('fixed', [True, False])
def test_translation_repairs_citation_counts_once_in_the_same_workspace(notebook, monkeypatch, fixed):
    from connectonion.rem.service import run_logs
    prose = '# Avery Lin\n\nA draft [12] [12] [W3].\n'
    (notebook / 'people/avery-lin.md').write_text(prose)
    translated = prose.replace('A draft', '一份草稿')
    broken = translated.replace('[12] [12]', '[12] [3]')
    calls = []

    def run(workspace, prompt, config, stage):
        calls.append((workspace, prompt))
        if len(calls) == 2:
            assert (workspace / 'translation.md').read_text() == broken
        answer = translated if fixed and len(calls) == 2 else broken
        (workspace / 'translation.md').write_text(answer)
        return {'outcome': 'natural', 'usage': {'input_tokens': 100, 'output_tokens': 20}}

    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    if fixed:
        assert tr.translate(notebook, 'people/avery-lin.md', 'zh') == translated
        assert tr.cached(notebook, 'people/avery-lin.md', 'zh') == translated
    else:
        with pytest.raises(RemError, match=r'missing \[12\].*extra \[3\]'):
            tr.translate(notebook, 'people/avery-lin.md', 'zh')
        assert tr.cached(notebook, 'people/avery-lin.md', 'zh') is None
    assert len(calls) == 2 and calls[0][0] == calls[1][0]
    assert calls[1][1].startswith(calls[0][1] + '\n\n')
    assert 'missing [12] (1 time(s)); extra [3] (1 time(s))' in calls[1][1]
    assert 'on the same line' in calls[1][1] and 'Fix translation.md in place' in calls[1][1]
    [log] = run_logs(notebook)
    assert log['runner_attempts'] == 2
    assert log['usage'] == {'input_tokens': 200, 'output_tokens': 40}
    assert log['outcome'] == ('completed' if fixed else 'failed')
    assert not list((notebook / '.state/tasks').iterdir())


def test_citation_errors_name_repeated_and_web_ids():
    with pytest.raises(RemError, match=r'missing \[12\] \(2 time.*missing \[W3\].*extra \[3\]'):
        tr.checked('Draft [12] [12] [W3].\n', '草稿 [3]。\n')


def test_missing_translation_is_not_retried(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr('connectonion.rem.runner.run_task', lambda *args: calls.append(args) or {})
    with pytest.raises(RemError, match='without writing a translation'):
        tr.translate(notebook, 'people/avery-lin.md', 'zh')
    assert len(calls) == 1


def test_failed_repair_runner_preserves_usage_from_both_attempts(notebook, monkeypatch):
    from connectonion.rem.runner import RunFailed
    from connectonion.rem.service import run_logs
    calls = []

    def run(workspace, *args):
        calls.append(workspace)
        if len(calls) == 2:
            raise RunFailed('fixture runner failure', {'input_tokens': 50})
        (workspace / 'translation.md').write_text('# Avery Lin\n\n## Facts\n草稿。\n')
        return {'usage': {'input_tokens': 100, 'output_tokens': 20}}

    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    with pytest.raises(RemError, match='fixture runner failure'):
        tr.translate(notebook, 'people/avery-lin.md', 'zh')
    [log] = run_logs(notebook)
    assert log['runner_attempts'] == 2
    assert log['usage'] == {'input_tokens': 150, 'output_tokens': 20}


def test_a_runner_that_cannot_run_is_named_before_any_model_call(notebook, monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("Codex is not signed in", "codex login"))
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a: pytest.fail("model called"))
    with pytest.raises(RemError, match="codex login"):
        tr.translate(notebook, "people/avery-lin.md", "zh")


def test_a_language_is_a_tag_not_a_path(notebook):
    for bad in ("../people", "zh/../../x", "", "中文"):
        with pytest.raises(RemError, match="language"):
            tr.translation_path(notebook, "people/avery-lin.md", bad)


def test_the_snapshot_carries_only_current_translations(notebook, monkeypatch):
    from connectonion.rem.reader import snapshot
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, []))
    tr.translate(notebook, "people/avery-lin.md", "zh")
    record = next(r for r in snapshot(notebook)["records"] if r["path"] == "people/avery-lin.md")
    assert record["translations"] == {"zh": CHINESE} and record["text"] == PAGE


def test_cli_translate_prints_the_translation(notebook, monkeypatch):
    calls = []
    monkeypatch.setattr("connectonion.rem.runner.run_task", model(CHINESE, calls))
    result = CliRunner().invoke(app, ["rem", "--root", str(notebook), "--json", "translate",
                                      "people/avery-lin.md", "--to", "zh"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"] == CHINESE
    bad = CliRunner().invoke(app, ["rem", "--root", str(notebook), "--json", "translate",
                                   "people/avery-lin.md", "--to", "../x"])
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


def test_translate_prompt_adds_only_the_derived_glossary():
    assert 'Keep these terms in English, as the owner writes them: capstone, pr, repo.' in \
        tr.prompt('zh', terms=['capstone', 'pr', 'repo'])
    assert 'Keep these terms in English' not in tr.prompt('zh')
    assert 'capstone' not in tr.prompt('zh')
    assert 'Names stay as written' in tr.prompt('zh')


def test_translation_prompt_preserves_currency_numbers_and_identifiers():
    prompt = tr.prompt('zh')
    assert 'Keep every amount, number and currency symbol exactly as written' in prompt
    assert '`$50,000`, `A$1,200`, `¥300`' in prompt
    assert "never convert or name a currency the original doesn't name" in prompt
    assert 'including lowercase project names' in prompt
    assert 'email addresses, URLs, file paths, issue/PR numbers (#2345)' in prompt
    assert 'version numbers and code spans unchanged' in prompt


def test_translation_prompt_lists_title_and_link_names_once(notebook, monkeypatch):
    page = ('# handoff\n\nAvery Lin uses [handoff](https://example.com/handoff) with '
            '[Mara Ostrowski](../people/mara-ostrowski.md), [Theo Park][theo] and '
            '[Northgate University](https://example.com).\n\n[theo]: https://example.com/theo\n')
    (notebook / 'people/avery-lin.md').write_text(page)
    calls = []
    monkeypatch.setattr('connectonion.rem.runner.run_task', model(page, calls))
    tr.translate(notebook, 'people/avery-lin.md', 'zh')
    assert ('Keep these names exactly as written:\n- handoff\n- Mara Ostrowski\n- Theo Park\n'
            '- Northgate University\n') in calls[0]['prompt']
    assert calls[0]['prompt'].count('\n- handoff\n') == 1
    assert tr.page_names('# handoff\n' + '[Mia Chen](https://example.com)\n' * 50) == ['handoff', 'Mia Chen']
    assert len(tr.page_names('# handoff\n' + '\n'.join(f'[tool-{n}](https://example.com)' for n in range(50)))) == 40


@pytest.mark.parametrize('language', ['zh', 'zh-TW', 'en', 'ja'])
def test_translate_passes_owner_glossary_only_for_chinese(notebook, monkeypatch, language):
    calls = []
    monkeypatch.setattr('connectonion.rem.languages.owner_languages', lambda root: {'english_terms': ['capstone', 'pr']})
    monkeypatch.setattr('connectonion.rem.runner.run_task', model(CHINESE, calls))
    tr.translate(notebook, 'people/avery-lin.md', language)
    assert ('as the owner writes them: capstone, pr.' in calls[0]['prompt']) == language.startswith('zh')



def test_translate_prompt_keeps_date_prefix_punctuation():
    assert 'keep the ASCII colon after a leading date like `2026-10-15:`' in tr.prompt('zh')


def test_cli_backfill_skips_current_cache_and_nonrecords_and_continues(notebook, monkeypatch):
    from connectonion.rem.files import atomic_write
    calls = []
    for category, name in [('people', 'mara-ostrowski'), ('people', 'theo-park'), ('orgs', 'company'),
                           ('projects', 'launch'), ('decisions', 'format'), ('principles', 'simple'),
                           ('logs', 'run'), ('notes', 'activity'), ('knowledge', 'topic'),
                           ('skills/catalog', 'index'), ('skills/catalog', 'mail')]:
        folder = notebook / category
        folder.mkdir(parents=True, exist_ok=True)
        (folder / (name + '.md')).write_text('# ' + name + '\n\nA source finding.\n')
    atomic_write(tr.translation_path(notebook, 'people/avery-lin.md', 'zh'),
                 '<!-- co rem translation of people/avery-lin.md sha256:' + tr.digest(PAGE) + ' -->\n' + CHINESE)

    atomic_write(tr.translation_path(notebook, 'people/theo-park.md', 'zh'),
                 '<!-- co rem translation of people/theo-park.md sha256:' + tr.digest('# Old page') + ' -->\n旧缓存')

    def translate(root, record, language):
        assert root == notebook and language == 'zh'
        calls.append(record)
        if record == 'people/mara-ostrowski.md':
            raise RemError('fixture translation refused')
        return 'translated prose'

    monkeypatch.setattr(tr, 'translate', translate)
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook), 'translate', '--all', '--to', 'zh'])
    assert result.exit_code == 1, result.output
    assert 'people/avery-lin.md: cached' in result.output
    assert 'people/mara-ostrowski.md: failed: fixture translation refused' in result.output
    assert 'people/theo-park.md: translated' in result.output
    assert '6 translated, 1 cached, 1 failed' in result.output
    assert sorted(calls) == sorted(['people/mara-ostrowski.md', 'people/theo-park.md', 'orgs/company.md', 'projects/launch.md',
                                    'skills/catalog/mail.md', 'decisions/format.md', 'principles/simple.md'])
    assert (notebook / 'people/avery-lin.md').read_text() == PAGE


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
    assert calls == [(notebook, 'people/avery-lin.md', 'zh-TW')]
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook), 'translate', 'Avery Lin'])
    assert result.exit_code == 0, result.output
    assert calls[-1] == (notebook, 'people/avery-lin.md', 'zh-TW')


@pytest.mark.parametrize('args', [[], ['--all', 'Avery Lin'], ['Avery Lin', '--category', 'people'],
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
    (notebook / 'people/avery-lin.md').write_text(page)
    monkeypatch.setattr('connectonion.rem.runner.run_task', model(CHINESE, []))
    with pytest.raises(RemError, match='privacy tags'):
        tr.translate(notebook, 'people/avery-lin.md', 'zh')
    assert tr.cached(notebook, 'people/avery-lin.md', 'zh') is None


def test_translate_pages_runs_in_parallel_and_keeps_input_order(notebook):
    from threading import Barrier
    from connectonion.rem.runner import RunFailed
    records = ['people/avery-lin.md', 'people/mara-ostrowski.md', 'people/theo-park.md']
    for record in records:
        (notebook / record).write_text('# Invented page\n')
    barrier = Barrier(3)
    calls, said = [], []

    def translate_one(root, record, language):
        calls.append(record)
        barrier.wait(timeout=5)
        if record == records[1]:
            raise RunFailed('fixture translation refused', {'input_tokens': 12})

    result = tr.translate_pages(notebook, 'zh', records, said.append, workers=3, translate_one=translate_one)
    assert sorted(calls) == sorted(records)
    assert result == {'language': 'zh', 'pages': [
        {'page': records[0], 'outcome': 'translated'},
        {'page': records[1], 'outcome': 'failed', 'error': 'fixture translation refused'},
        {'page': records[2], 'outcome': 'translated'}], 'translated': 2, 'cached': 0, 'failed': 1}
    assert [line.split(':')[0] for line in said] == records


def test_translate_pages_skips_current_cache_and_handles_empty_input(notebook, monkeypatch):
    record = 'people/avery-lin.md'
    (notebook / record).write_text('# Avery Lin\n')
    monkeypatch.setattr(tr, 'cached', lambda *args: '# Avery Lin\n')
    report = tr.translate_pages(notebook, 'zh', [record], translate_one=lambda *args: pytest.fail('cache missed'))
    assert report['cached'] == 1 and report['translated'] == report['failed'] == 0
    assert tr.translate_pages(notebook, 'zh', [])['pages'] == []


@pytest.mark.parametrize('failure', ['none', 'runner', 'validation'])
def test_each_model_translation_logs_usage_even_on_failure(notebook, monkeypatch, failure):
    from connectonion.rem.runner import RunFailed
    from connectonion.rem.service import run_logs, usage_report
    record = 'people/avery-lin.md'
    (notebook / record).write_text('# Avery Lin\n\n## Facts\nA draft.\n')
    usage = {'input_tokens': 80000, 'output_tokens': 50, 'cached_input_tokens': 70000}

    def run(workspace, prompt, config, stage):
        if failure == 'runner':
            raise RunFailed('fixture model refused', usage)
        (workspace / 'translation.md').write_text('# Avery Lin\n\n## Facts\n草稿。\n' if failure == 'none' else '# Changed\n')
        return {'outcome': 'natural', 'usage': usage}

    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    if failure == 'none':
        tr.translate(notebook, record, 'zh')
        tr.translate(notebook, record, 'zh')  # A cache hit spends nothing and adds no model run.
    else:
        with pytest.raises(RemError):
            tr.translate(notebook, record, 'zh')
    [log] = run_logs(notebook)
    assert log['phase'] == 'translate' and log['record'] == record and log['language'] == 'zh'
    assert log['outcome'] == ('completed' if failure == 'none' else 'failed')
    from connectonion.rem.config import read_config
    attempts = 2 if failure == 'validation' else 1
    expected_usage = {key: value * attempts for key, value in usage.items()}
    assert log['runner_attempts'] == attempts
    assert log['usage'] == expected_usage and log['harness'] == read_config(notebook)['runner'] and log['model']
    assert log['finished_at'] >= log['started_at'] and log['seconds'] >= 0
    assert usage_report(notebook)['by_stage']['translate'] == expected_usage
    assert not list((notebook / '.state/tasks').iterdir())


@pytest.mark.parametrize('repair', [False, True])
def test_daily_summary_and_per_page_usage_are_not_counted_twice(notebook, monkeypatch, repair):
    from connectonion.rem.config import read_config, set_config
    from connectonion.rem.daily import _translate_changed
    from connectonion.rem.service import run_logs, usage_report
    record = 'people/avery-lin.md'
    (notebook / record).write_text('# Avery Lin\n\nA draft [12].\n')
    set_config(notebook, ['languages', 'en,zh', 'limits.translations_per_day', '1'])
    calls = []

    def run(workspace, *args):
        calls.append(workspace)
        answer = '# Avery Lin\n\n草稿 [12]。\n'
        (workspace / 'translation.md').write_text(answer.replace(' [12]', '') if repair and len(calls) == 1 else answer)
        return {'outcome': 'natural', 'usage': {'input_tokens': 80000}}

    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    maintenance = {}
    _translate_changed(notebook, read_config(notebook), maintenance, [record], None, lambda text: None)
    assert maintenance['translations']['pages'] == [{'page': record, 'outcome': 'translated'}]
    logs = run_logs(notebook)
    assert {log['phase'] for log in logs} == {'translate', 'daily-translation'}
    attempts = 2 if repair else 1
    assert usage_report(notebook)['total']['input_tokens'] == 80000 * attempts
    assert sum(log.get('runner_attempts', 0) for log in logs) == attempts
    # The daily limit counts pages even though runner calls live in per-page logs.
    (notebook / record).write_text('# Avery Lin\n\nA revised draft [12].\n')
    _translate_changed(notebook, read_config(notebook), {}, [record], None, lambda text: None)
    assert len(calls) == attempts


def test_daily_rechecks_runner_budget_after_a_translation_repair(notebook, monkeypatch):
    from connectonion.rem.config import read_config, set_config
    from connectonion.rem.daily import _translate_changed
    records = ['people/avery-lin.md', 'people/mara-ostrowski.md']
    for record in records:
        (notebook / record).write_text('# Avery Lin\n\nA draft [12].\n')
    set_config(notebook, ['languages', 'en,zh', 'limits.translations_per_day', '2', 'limits.runner_calls_per_day', '2'])
    calls = []

    def run(workspace, *args):
        calls.append(workspace)
        answer = '# Avery Lin\n\n草稿 [12]。\n'
        (workspace / 'translation.md').write_text(answer.replace(' [12]', '') if len(calls) == 1 else answer)
        return {'usage': {'input_tokens': 100}}

    monkeypatch.setattr('connectonion.rem.runner.run_task', run)
    maintenance = {}
    _translate_changed(notebook, read_config(notebook), maintenance, records, None, lambda text: None)
    assert maintenance['translations']['pages'] == [{'page': records[0], 'outcome': 'translated'}]
    assert len(calls) == 2
    assert tr.cached(notebook, records[1], 'zh') is None


def test_issue_numbers_at_line_start_are_prose_not_headings():
    original = '# Theo Park\n\n## History\n- Fixed in #1037 [1].\n'
    assert tr.checked(original, '# Theo Park\n\n## History\n#1037 中修复 [1]。\n') .startswith('# Theo Park')
