"""Search never treats record order as evidence of a person's identity."""
import json
import re

import pytest

from connectonion.rem.reader import TEMPLATE
from test_rem_reader import _run_reader_js


def search_result(query, selected="", *, hidden=True, unique=False, no_details=False,
                  first_title='Aster Vale', second_title='Aster Vale', second_alias='', extra_titles=()):
    page = TEMPLATE.read_text()
    names = ["search", "listedRecords", "identityChoices", "identityDetails", "nameMatches", "recordedNames"]
    functions = "\n".join(match.group(0) for name in names
                          if (match := re.search(r"function " + name + r"\(.*?\n\}", page, re.S)))
    script = r'''
      const rows = [], ACTIVITY = new Set(['logs', 'sessions']);
      const document = {getElementById: () => ({appendChild: x => rows.push(x)}),
        documentElement: {classList: {contains: () => HIDDEN}}};
      const REM = {records: [
        {path:'people/aster-a.md', title:'Aster Vale', category:'people', text:'## Facts\n- Company: North Studio\n- Email: hidden@example.com [personal]'},
        {path:'people/aster-b.md', title:'Aster Vale', category:'people', text:'## Facts\n- Company: South Lab\n- Role: Engineer'},
        {path:'people/held.md', title:'Aster Vale', category:'people', needs_review:true, text:''},
        {path:'people/service.md', title:'Aster Vale', category:'people', service:true, text:''},
      ]};
      REM.records[0].title = FIRST_TITLE;
      REM.records[1].title = SECOND_TITLE;
      REM.records[1].text += '\n- Also known as: ' + SECOND_ALIAS;
      REM.records.push(...EXTRA_TITLES.map((title, i) => ({path:'people/extra-' + i + '.md', title, category:'people', text:''})));
      if (UNIQUE) REM.records.splice(1, 1);
      if (NO_DETAILS) REM.records.forEach(r => {r.text = "";});
      const el = (tag, attrs={}, children=[]) => ({tag, ...attrs, children,
        appendChild(x) {this.children.push(x);}});
      const href = r => '#r=' + encodeURIComponent(r.path), label = c => c;
      const connectedContext = r => ({relatedFor: r.path});
      const emptyState = text => ({text}), skillReport = () => false;
      const splitTrailers = text => ({body:text}), COMMENT = /<!--.*?-->/g;
      const FACT_LABELS = {people:1}, bestMatch = r => ({bestFor:r.path});
      const highlight = s => s, statusPill = () => null, known = () => ({});
      const shortDate = () => '', summaryLine = s => s;
      // The parser contract is also checked below using its actual implementation.
      const parseFacts = r => new Map([...r.text.matchAll(/^- (\w+): (.*)$/gm)].map(m => [m[1], [{value:m[2]}]]));
      const plainValue = s => s, knownValue = s => !!s && s !== 'Unknown';
      search(QUERY, SELECTED);
      console.log(JSON.stringify(rows));
    '''
    script = script.replace("HIDDEN", json.dumps(hidden)).replace("UNIQUE", json.dumps(unique))
    script = script.replace("NO_DETAILS", json.dumps(no_details))
    script = script.replace("FIRST_TITLE", json.dumps(first_title)).replace("SECOND_TITLE", json.dumps(second_title))
    script = script.replace("SECOND_ALIAS", json.dumps(second_alias))
    script = script.replace("EXTRA_TITLES", json.dumps(extra_titles))
    script = script.replace("QUERY", json.dumps(query)).replace("SELECTED", json.dumps(selected))
    return _run_reader_js(functions + script)


def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.get("children", []):
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def test_related_name_requires_identity_choice_before_showing_connections():
    result = search_result("related to Aster Vale")
    assert not any("relatedFor" in n for n in nodes(result))
    choices = [n for n in nodes(result) if n.get("href", "").startswith("#q=")]
    assert len(choices) == 2
    assert {n["href"].split("&related=")[1] for n in choices} == {
        "people%2Faster-a.md", "people%2Faster-b.md"}
    text = json.dumps(result)
    assert "North Studio" in text and "South Lab" in text
    assert "hidden@example.com" not in text
    assert "people/held.md" not in text and "people/service.md" not in text


@pytest.mark.parametrize("query", ["Aster Vale", "Aster"])
def test_ambiguous_name_never_promotes_first_person_as_best_match(query):
    result = search_result(query)
    assert not any("bestFor" in n for n in nodes(result))
    assert any(n.get("text") == "Choose a page" for n in nodes(result))


def test_unique_name_still_opens_connections_directly():
    assert any(n.get("relatedFor") == "people/aster-a.md"
               for n in nodes(search_result("related to Aster Vale", unique=True)))


def test_explicit_selection_uses_exact_person_not_first_same_title():
    result = search_result("related to Aster Vale", "people/aster-b.md")
    assert [n["relatedFor"] for n in nodes(result) if "relatedFor" in n] == ["people/aster-b.md"]


@pytest.mark.parametrize("selected", ["people/held.md", "people/service.md", "people/deleted.md"])
def test_unavailable_explicit_choice_never_falls_back_to_same_name(selected):
    result = search_result("related to Aster Vale", selected)
    assert not any("relatedFor" in n for n in nodes(result))


def test_unique_name_retains_best_match_summary():
    assert [n["bestFor"] for n in nodes(search_result("Aster Vale", unique=True)) if "bestFor" in n] == ["people/aster-a.md"]


@pytest.mark.parametrize('query', ['Aster', 'aStEr', 'related to Aster'])
def test_identity_picker_excludes_longer_first_names(query):
    result = search_result(query, first_title='Aster',
                           extra_titles=('Asteron North', 'Asterley Reed'))
    picker = next(n for n in result if any(c.get('text') == 'Choose a page'
                                          for c in n.get('children', [])))
    choices = [n['text'] for n in nodes(picker) if n.get('aria-describedby')]
    assert choices == ['Aster', 'Aster Vale']
    if not query.startswith('related to '):
        hits = [n.get('html') for n in nodes(result) if n.get('href', '').startswith('#r=')]
        assert 'Asteron North' in hits and 'Asterley Reed' in hits


@pytest.mark.parametrize('query', ['Aster', 'aStEr'])
def test_unique_whole_first_name_keeps_best_match_and_substring_hits(query):
    result = search_result(query, second_title='Asteron North',
                           extra_titles=('Asterley Reed',))
    assert [n['bestFor'] for n in nodes(result) if 'bestFor' in n] == ['people/aster-a.md']
    hits = [n.get('html') for n in nodes(result) if n.get('href', '').startswith('#r=')]
    assert set(hits) == {'Aster Vale', 'Asteron North', 'Asterley Reed'}


def test_unique_whole_alias_keeps_best_match():
    result = search_result('aStEr', first_title='Asteron North', second_title='Nova Reed', second_alias='Aster')
    assert [n['bestFor'] for n in nodes(result) if 'bestFor' in n] == ['people/aster-b.md']


def test_identity_details_use_original_visible_facts_without_poisoning_translation_cache():
    page = TEMPLATE.read_text()
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["identityDetails", "parseFacts", "topLevelParts", "rawSection", "plainLine", "plainValue", "knownValue"])
    result = _run_reader_js(functions + r'''
      const PARSED_FACTS = new Map(), COMMENT = /<!--[\s\S]*?-->/g, UNFILLED_LINE = /^not investigated$/;
      const youify = s => s;
      const document = {documentElement: {classList: {contains: () => true}}};
      const original = '# Aster Vale\n\n## Facts\n- Company: [North Studio](../orgs/north.md) (former) [1]\n- Role: Engineer (2019)\n- Email: secret@example.com [personal]\n- Phone: Private phone [sensitive]\n- Status: Unknown';
      const translated = '# Aster Vale\n\n## Facts\n- Company: Wrong translated identity';
      const r = {path:'people/aster.md', text:translated, original, translations:{zh:translated}, readLanguage:'zh'};
      const before = parseFacts(r).get('Company')[0].value;
      const choices = identityDetails(r);
      const after = parseFacts(r).get('Company')[0].value;
      console.log(JSON.stringify({before, choices, after, unchanged:r.text === translated}));
    ''')
    assert result == {"before":"Wrong translated identity", "choices":[["Company", "North Studio (former)"], ["Role", "Engineer (2019)"]],
                      "after":"Wrong translated identity", "unchanged":True}


def test_related_choice_route_is_passed_to_actual_search_dispatch():
    page = TEMPLATE.read_text()
    route = re.search(r"function route\(.*?\n\}", page, re.S).group(0)
    result = _run_reader_js(route + r'''
      const location = {hash:'#q=related%20to%20Aster%20Lane&related=people%2Faster-b.md'};
      const navigationRecord = () => null;
      console.log(JSON.stringify(route()));
    ''')
    assert result["related"] == "people/aster-b.md"
    assert "else if (query) search(query, related);" in page


def test_candidates_without_visible_facts_are_explicit_and_descriptions_resolve():
    result = search_result("related to Aster Vale", no_details=True)
    flat = list(nodes(result))
    links = [n for n in flat if n.get("href", "").startswith("#q=")]
    assert len(links) == 2
    for link in links:
        descriptions = [n for n in flat if n.get("id") == link["aria-describedby"]]
        assert len(descriptions) == 1
        assert descriptions[0]["text"] == "No visible identifying details. Open the page to check its sources."


def morning_result(tmp_path, people, prefix):
    # Ranking moved to Python; exercise that authority and its real JS projection.
    from datetime import date
    from connectonion.rem.config import prepare
    from connectonion.rem.today import queue
    prepare(tmp_path)
    records = [{**person, 'text': '# ' + person['title'] + '\n' + person.get('text', '')
                + '\n## Open threads\n- ' + prefix + '\n'} for person in people]
    rows = queue(tmp_path, records=records, as_of=date(2026, 11, 8))
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['morningEntries', 'todayEntries'])
    return _run_reader_js(functions + 'const REM = ' + json.dumps({'today_queue': rows}) + ';'
        + 'const records = ' + json.dumps(records) + ';' + r"""
      const doneKey = entry => entry.r.path + '\n' + entry.t.text, isDone = () => false;
      const entries = records.map(r => ({r, t:{dir:'mine', text:PREFIX}}));
      console.log(JSON.stringify(morningEntries(entries).map(entry => entry.r.path)));
    """.replace('PREFIX', json.dumps(prefix)))


@pytest.mark.parametrize('prefix, expected', [
    ('You owe Aster: review it', ['people/a.md', 'people/b.md']),
    ('You owe Aster Vale: review it', ['people/a.md', 'people/b.md']),
    ('You owe Aster North: review it', ['people/a.md']),
])
def test_morning_cards_do_not_assign_an_ambiguous_counterpart(tmp_path, prefix, expected):
    people = [{'path': 'people/a.md', 'title': 'Aster North'},
              {'path': 'people/b.md', 'title': 'Aster Vale'}]
    if 'Aster Vale' in prefix:
        people[0]['title'] = 'Aster Vale'
    assert morning_result(tmp_path, people, prefix) == expected


def test_unique_full_name_beats_partial_title_matches():
    result = search_result('Aster Vale', second_title='Aster Vale North')
    assert [n['bestFor'] for n in nodes(result) if 'bestFor' in n] == ['people/aster-a.md']


@pytest.mark.parametrize('query', ['Aster', 'related to Aster'])
def test_a_single_word_title_does_not_disambiguate_other_people(query):
    result = search_result(query, first_title='Aster')
    assert not any('bestFor' in n or 'relatedFor' in n for n in nodes(result))
    assert any(n.get('text') == 'Choose a page' for n in nodes(result))


@pytest.mark.parametrize('query', ['Aster Vale', 'related to Aster Vale'])
def test_a_name_qualifier_does_not_make_the_unqualified_name_unique(query):
    result = search_result(query, second_title='Aster Vale (work)')
    assert not any('bestFor' in n or 'relatedFor' in n for n in nodes(result))
    assert any(n.get('text') == 'Choose a page' for n in nodes(result))


@pytest.mark.parametrize('query', ['Aster Vale', 'related to Aster Vale'])
def test_existing_alias_collision_blocks_title_selection(query):
    result = search_result(query, second_title='Nova Reed', second_alias='Aster Vale')
    assert not any('bestFor' in n or 'relatedFor' in n for n in nodes(result))
    assert any(n.get('text') == 'Choose a page' for n in nodes(result))


@pytest.mark.parametrize('query', ['Aster Vale', 'related to Aster Vale'])
def test_a_parenthetical_name_also_blocks_title_selection(query):
    result = search_result(query, second_title='Nova Reed (Aster Vale)')
    assert not any('bestFor' in n or 'relatedFor' in n for n in nodes(result))
    assert any(n.get('text') == 'Choose a page' for n in nodes(result))


def test_a_single_word_title_does_not_disambiguate_morning_cards(tmp_path):
    people = [{'path': 'people/a.md', 'title': 'Aster'},
              {'path': 'people/b.md', 'title': 'Aster Vale'}]
    assert morning_result(tmp_path, people, 'You owe Aster: review it') == ['people/a.md', 'people/b.md']


def test_morning_counterpart_must_count_existing_aliases(tmp_path):
    people = [{'path': 'people/a.md', 'title': 'Aster Vale'},
              {'path': 'people/b.md', 'title': 'Nova Reed', 'text': '## Facts\n- Also known as: Aster Vale'}]
    assert morning_result(tmp_path, people, 'You owe Aster Vale: review it') == ['people/a.md', 'people/b.md']


def test_morning_does_not_add_alias_only_resolution(tmp_path):
    people = [{'path': 'people/a.md', 'title': 'Nova Reed', 'text': '## Facts\n- Also known as: Aster Vale'},
              {'path': 'people/b.md', 'title': 'Sol Reed'}]
    assert morning_result(tmp_path, people, 'You owe Aster Vale: review it') == ['people/a.md', 'people/b.md']
