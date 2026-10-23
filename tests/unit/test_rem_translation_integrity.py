"""A translated claim must still point at its original evidence."""
import re

import pytest

from connectonion.rem import translate as tr
from connectonion.rem.files import RemError, atomic_write
from test_rem_translate import CHINESE, PAGE, notebook


def document(first='gmail:fixture-a', second='outlook:fixture-b'):
    return ('# Synthetic\n\n## Facts\n- First claim [1]\n- Second claim [2]\n\n'
            f'## Sources\n- [1] {first} — first caption\n- [2] {second} — second caption\n')


@pytest.mark.parametrize('target,changed', [
    ('gmail:fixture-a','gmail:fixture-other'),
    ('codex:session:4','codex:session:5'),
    ('file:/fixture/a notes.md#sha256:'+'a'*64,'file:/fixture/a notes.md#sha256:'+'b'*64),
    ('file:/fixture/a.md@'+'a'*40,'file:/fixture/a.md@'+'b'*40),
    ('https://example.test/a?q=1#part','https://example.test/a?q=2#part'),
    ('https://example.test/a#one','https://example.test/a#two'),
])
def test_unchanged_number_cannot_change_routing_identity(target, changed):
    original = document(target)
    with pytest.raises(RemError, match='source target|source definition'):
        tr.checked(original, original.replace(target, changed))


def test_swapped_targets_cannot_keep_the_same_numbered_labels():
    original = document()
    translated = original.replace('gmail:fixture-a','TEMP').replace('outlook:fixture-b','gmail:fixture-a').replace('TEMP','outlook:fixture-b')
    with pytest.raises(RemError, match='source target|source definition'):
        tr.checked(original, translated)


def test_duplicate_definition_is_not_a_valid_translation_even_when_identical():
    original = document().replace('- [2] outlook:fixture-b', '- [1] gmail:fixture-a')
    with pytest.raises(RemError, match='source definition'):
        tr.checked(original, original)


def test_unknown_source_syntax_is_literal_not_a_guess_at_identity():
    original = document('Existing mapped page people/fixture.md')
    with pytest.raises(RemError, match='source target|source definition'):
        tr.checked(original, original.replace('Existing mapped page people/fixture.md','另一页 people/other.md'))


def test_a_reference_cannot_move_between_claim_lines_with_the_same_global_multiset():
    original = document()
    moved = original.replace('First claim [1]','First claim [2]').replace('Second claim [2]','Second claim [1]')
    with pytest.raises(RemError, match='citation.*line|line.*citation'):
        tr.checked(original, moved)


def test_translated_captions_and_full_width_citation_marks_keep_identity():
    original = document()
    translated = original.replace('First claim','第一个论述').replace('Second claim','第二个论述')
    translated = translated.replace('first caption','第一条说明').replace('second caption','第二条说明')
    translated = translated.replace('[1]','［1］').replace('[2]','［2］')
    assert tr.checked(original, translated) == translated


@pytest.mark.parametrize('wrong_header', [False, True])
def test_matching_digest_cannot_serve_wrong_routing_or_wrong_record_header(notebook, wrong_header):
    record = 'people/avery-lin.md'
    content = CHINESE if wrong_header else CHINESE.replace('gmail:abc','gmail:wrong')
    header_record = 'people/other.md' if wrong_header else record
    path = tr.translation_path(notebook, record, 'zh')
    saved = f'<!-- co rem translation of {header_record} sha256:{tr.digest(PAGE)} -->\n'+content
    atomic_write(path, saved)
    original = (notebook/record).read_bytes()
    assert tr.cached(notebook, record, 'zh') is None
    assert tr.cached_languages(notebook, record) == {}
    assert path.read_text() == saved and (notebook/record).read_bytes() == original


def test_valid_current_cache_remains_usable_without_prompt_version_bump(notebook):
    record = 'people/avery-lin.md'
    atomic_write(tr.translation_path(notebook, record, 'zh'),
        f'<!-- co rem translation of {record} sha256:{tr.digest(PAGE)} -->\n'+CHINESE)
    assert tr.PROMPT_VERSION == 2
    assert tr.cached(notebook, record, 'zh') == CHINESE


def test_target_validation_failure_keeps_existing_cache_bytes_and_original(notebook, monkeypatch):
    record = 'people/avery-lin.md'
    path = tr.translation_path(notebook, record, 'zh')
    atomic_write(path, 'retained cache fixture\n')
    def reply(workspace, *args):
        (workspace/'translation.md').write_text(CHINESE.replace('gmail:abc','gmail:wrong'))
        return {'outcome':'natural'}
    monkeypatch.setattr('connectonion.rem.runner.run_task', reply)
    with pytest.raises(RemError, match='source target|source definition'):
        tr.translate(notebook, record, 'zh')
    assert path.read_text() == 'retained cache fixture\n' and (notebook/record).read_text() == PAGE


def reader_evidence(original, translated, language='en', number='1', category='people'):
    import json
    from connectonion.rem.reader import TEMPLATE
    from test_rem_reader import _run_reader_js
    page = TEMPLATE.read_text()
    names = ['rawSection','listItems','sourceList','sourceCaption','sourceId','citationSource',
             'chipLabel','citationDay','sourceLabel','sourceIdentity','evidenceOriginal','openEvidence','sectionBody']
    functions = '\n'.join(m.group(0) for name in names
        if (m := re.search(r'function '+name+r'\(.*?\n\}',page,re.S)))
    zh = page[page.index('  zh: {')+len('  zh: '):page.index('\n};\nfunction t(')]
    script = 'UI.zh = '+zh+'; uiLanguage = '+json.dumps(language)+';\n'+functions+r'''
      const COMMENT = /<!--[\s\S]*?-->/g, UNKNOWN_TEXT = /^Unknown\s*—\s*(?:not investigated yet|not verified)/i;
      const r = {path:'people/fixture.md', category:CATEGORY, original:ORIGINAL, text:TRANSLATED};
      const REM = {source_context:{'gmail:fixture-a':{source:'gmail',sender:'Author A',excerpt:'EXCERPT_A',origin:'gmail:fixture-a'},
        'outlook:fixture-b':{source:'outlook',sender:'Author B',excerpt:'EXCERPT_B',origin:'outlook:fixture-b'}}};
      let CITES = {from:r.path,sources:{'1':'outlook:fixture-b — wrong cache'}}, evidenceTrigger;
      const byPath = () => null, sourceSender = context => context.sender, sourceChannel = text => text;
      const fmtTime = String, markedSpan = String, markdown = String, supportingSpan = () => null;
      const evidenceLine = () => ({text:'译文论述 [1] [2] [personal]',numbers:['1','2']});
      const el = (tag,attrs={},children=[]) => ({tag,...attrs,children, parentElement:{hidden:true},
        appendChild(x){this.children.push(x);}, replaceChildren(...xs){this.children=xs;},
        insertBefore(x,ref){this.children.splice(Math.max(0,this.children.indexOf(ref)),0,x);},
        firstChild:{classList:{add(){}}},
        querySelector(){return this.children.find(x => x.class==='evidence-claim');}, focus(){}});
      const panel = el('section'), evidencePanel = () => panel;
      const closeEvidence = () => {}, togglePrivate = () => {}, evidenceLayout = () => {}, scrollEvidenceSpan = () => {};
      const document = {body:{classList:{add(){}}}}, mailMessage = (context,quote) => ({message:context.origin,quote});
      const routes = sourceList(r).map(row => ({n:row.n,id:sourceId(row.text)}));
      const caption = typeof sourceCaption==='function' ? sourceCaption(r,sourceList(r)[0]||{n:'1',text:''}) : null;
      const label = chipLabel(r,NUMBER), citeChip = () => 'fixture chip';
      const sourceBody = sectionBody(r,{title:'Sources',text:rawSection(r,'Sources')});
      openEvidence(r,NUMBER,{});
      console.log(JSON.stringify({routes,caption,label,panel,sourceBody}));
    '''
    script = script.replace('ORIGINAL',json.dumps(original)).replace('TRANSLATED',json.dumps(translated)).replace('NUMBER',json.dumps(number)).replace('CATEGORY',json.dumps(category))
    return _run_reader_js(script)


@pytest.mark.parametrize('language',['en','zh'])
def test_translated_source_list_chip_selector_and_popup_use_the_canonical_mapping(language):
    original = document()
    translated = original.replace('gmail:fixture-a','TEMP').replace('outlook:fixture-b','gmail:fixture-a').replace('TEMP','outlook:fixture-b')
    result = reader_evidence(original,translated,language)
    assert result['routes'] == [{'n':'1','id':'gmail:fixture-a'},{'n':'2','id':'outlook:fixture-b'}]
    assert result['label'] == 'Author A, gmail'
    text = str(result['panel'])
    assert 'EXCERPT_A' in text and 'EXCERPT_B' not in text
    assert 'evidence-original private' in text
    assert result['caption'] == 'gmail:fixture-a — first caption'


def test_valid_translated_caption_is_presentation_only_not_a_new_target():
    original = document()
    translated = original.replace('first caption','第一条说明')
    result = reader_evidence(original,translated,'zh')
    assert result['caption'] == 'gmail:fixture-a — 第一条说明'
    assert result['routes'][0]['id'] == 'gmail:fixture-a'


@pytest.mark.parametrize('target',['https://example.test/a?q=*#part','file:/fixture/a*notes.md@'+'a'*64])
def test_canonical_target_symbols_are_not_stripped_as_prose_formatting(target):
    original = document(target)
    assert reader_evidence(original,original)['routes'][0]['id'] == target


def test_reader_does_not_choose_first_of_ambiguous_canonical_definitions():
    original = document().replace('- [2] outlook:fixture-b','- [1] outlook:fixture-b')
    result = reader_evidence(original,original)
    assert result['routes'] == [] and 'EXCERPT_A' not in str(result['panel']) and 'EXCERPT_B' not in str(result['panel'])


def test_ambiguous_canonical_sources_are_refused_before_buying_a_translation(notebook, monkeypatch):
    record = 'people/avery-lin.md'
    bad = PAGE.replace('- [1] gmail:abc — intro mail', '- [1] gmail:abc — intro mail\n- [1] outlook:other — duplicate')
    (notebook/record).write_text(bad)
    monkeypatch.setattr('connectonion.rem.runner.run_task',lambda *a,**k: pytest.fail('Ambiguous input must not launch a model'))
    with pytest.raises(RemError, match='source definition'):
        tr.translate(notebook,record,'zh')
    assert (notebook/record).read_text() == bad


@pytest.mark.parametrize('replacement',['','[sensitive]','[personal] [personal]'])
def test_translated_caption_cannot_drop_or_change_canonical_privacy_state(replacement):
    original = document().replace('first caption','first caption [personal]')
    translated = original.replace('first caption [personal]','公开说明 '+replacement)
    result = reader_evidence(original,translated,'zh')
    assert result['caption'] == 'gmail:fixture-a — first caption [personal]'


def test_valid_translated_private_caption_retains_its_label():
    original = document().replace('first caption','first caption [personal]')
    translated = original.replace('first caption','私有说明')
    assert reader_evidence(original,translated,'zh')['caption'] == 'gmail:fixture-a — 私有说明 [personal]'


def test_sources_caption_emits_the_existing_privacy_gate_for_labelled_text():
    original = document().replace('first caption','first caption [personal]')
    result = reader_evidence(original,original.replace('first caption','私有说明'),'zh')
    def nodes(value):
        if isinstance(value,dict):
            yield value
            for item in value.values():
                yield from nodes(item)
        elif isinstance(value,list):
            for item in value:
                yield from nodes(item)
    assert any('private' in n.get('class','').split() and '私有说明' in n.get('text','')
               for n in nodes(result['sourceBody']))


@pytest.mark.parametrize('change', ['route','membership','privacy'])
def test_reader_snapshot_excludes_invalid_matching_digest_cache_without_model_work(notebook, monkeypatch, change):
    from connectonion.rem.reader import snapshot
    record = 'people/avery-lin.md'
    original = PAGE.replace('- Role: founder [1]', '- Role: founder [1]\n- Contact detail [personal]')
    (notebook/record).write_text(original)
    translated = original.replace('founder','创始人')
    if change == 'route':
        translated = translated.replace('gmail:abc','gmail:wrong')
    elif change == 'membership':
        translated = translated.replace('创始人 [1]','创始人').replace('detail [personal]','detail [1] [personal]')
    else:
        translated = translated.replace('[personal]','[sensitive]')
    saved = f'<!-- co rem translation of {record} sha256:{tr.digest(original)} -->\n'+translated
    path = tr.translation_path(notebook,record,'zh')
    atomic_write(path,saved)
    monkeypatch.setattr('connectonion.rem.runner.run_task',lambda *a,**k: pytest.fail('Reading a cache must not call a model'))
    row = next(r for r in snapshot(notebook)['records'] if r['path']==record)
    assert 'zh' not in row.get('translations',{})
    assert row['text'] == original and path.read_text() == saved


@pytest.mark.parametrize('case',['unknown_duplicate','multiple_sections'])
def test_reader_rejects_ambiguity_even_when_a_definition_is_filtered_or_in_another_section(case):
    original = document()
    if case == 'unknown_duplicate':
        original = original.replace('- [1] gmail:', '- [1] Unknown — not verified\n- [1] gmail:')
    else:
        original += '\n## Sources\n- [1] outlook:fixture-b — another mapping\n'
    result = reader_evidence(original,original)
    assert not any(row['n']=='1' for row in result['routes'])
    assert 'EXCERPT_A' not in str(result['panel']) and 'EXCERPT_B' not in str(result['panel'])


def test_mixed_legacy_and_explicit_session_sources_cannot_rebind_a_number():
    original = '# Session\n\n## Sources\n- codex:session:4\n- [1] gmail:fixture-a — caption\n'
    with pytest.raises(RemError, match='source definition'):
        tr.checked(original,original)
    assert reader_evidence(original,original,category='sessions')['routes'] == []


def test_ordinary_legacy_session_sources_remain_usable():
    original = '# Session\n\n## Sources\n- codex:session:4\n- claude-code:session:8\n'
    assert tr.checked(original,original) == original
    assert reader_evidence(original,original,category='sessions')['routes'] == [
        {'n':'1','id':'codex:session:4'},{'n':'2','id':'claude-code:session:8'}]
