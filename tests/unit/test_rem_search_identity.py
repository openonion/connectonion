"""Search never treats record order as evidence of a person's identity."""
import json
import re

import pytest

from connectonion.rem.reader import TEMPLATE
from test_rem_reader import _run_reader_js


def search_result(query, selected="", *, hidden=True, unique=False):
    page = TEMPLATE.read_text()
    names = ["search", "listedRecords", "identityChoices", "identityDetails"]
    functions = "\n".join(match.group(0) for name in names
                          if (match := re.search(r"function " + name + r"\(.*?\n\}", page, re.S)))
    script = r'''
      const rows = [], ACTIVITY = new Set(['logs', 'sessions']);
      const document = {getElementById: () => ({appendChild: x => rows.push(x)}),
        documentElement: {classList: {contains: () => HIDDEN}}};
      const REM = {records: [
        {path:'people/river-a.md', title:'River Lane', category:'people', text:'## Facts\n- Company: North Studio\n- Email: hidden@example.test [personal]'},
        {path:'people/river-b.md', title:'River Lane', category:'people', text:'## Facts\n- Company: South Lab\n- Role: Engineer'},
        {path:'people/held.md', title:'River Lane', category:'people', needs_review:true, text:''},
        {path:'people/service.md', title:'River Lane', category:'people', service:true, text:''},
      ]};
      if (UNIQUE) REM.records.splice(1, 1);
      const el = (tag, attrs={}, children=[]) => ({tag, ...attrs, children,
        appendChild(x) {this.children.push(x);}});
      const href = r => '#r=' + encodeURIComponent(r.path), label = c => c;
      const recordFocus = r => ({querySelector: () => ({relatedFor: r.path})});
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
    result = search_result("related to River Lane")
    assert not any("relatedFor" in n for n in nodes(result))
    choices = [n for n in nodes(result) if n.get("href", "").startswith("#q=")]
    assert len(choices) == 2
    assert {n["href"].split("&related=")[1] for n in choices} == {
        "people%2Friver-a.md", "people%2Friver-b.md"}
    text = json.dumps(result)
    assert "North Studio" in text and "South Lab" in text
    assert "hidden@example.test" not in text
    assert "people/held.md" not in text and "people/service.md" not in text


@pytest.mark.parametrize("query", ["River Lane", "River"])
def test_ambiguous_name_never_promotes_first_person_as_best_match(query):
    result = search_result(query)
    assert not any("bestFor" in n for n in nodes(result))
    assert any(n.get("text") == "Choose a page" for n in nodes(result))


def test_unique_name_still_opens_connections_directly():
    assert any(n.get("relatedFor") == "people/river-a.md"
               for n in nodes(search_result("related to River Lane", unique=True)))


def test_explicit_selection_uses_exact_person_not_first_same_title():
    result = search_result("related to River Lane", "people/river-b.md")
    assert [n["relatedFor"] for n in nodes(result) if "relatedFor" in n] == ["people/river-b.md"]


@pytest.mark.parametrize("selected", ["people/held.md", "people/service.md", "people/deleted.md"])
def test_unavailable_explicit_choice_never_falls_back_to_same_name(selected):
    result = search_result("related to River Lane", selected)
    assert not any("relatedFor" in n for n in nodes(result))


def test_unique_name_retains_best_match_summary():
    assert [n["bestFor"] for n in nodes(search_result("River Lane", unique=True)) if "bestFor" in n] == ["people/river-a.md"]


def test_identity_details_use_original_visible_facts_without_poisoning_translation_cache():
    page = TEMPLATE.read_text()
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["identityDetails", "parseFacts", "rawSection", "plainLine", "plainValue", "knownValue"])
    result = _run_reader_js(functions + r'''
      const PARSED_FACTS = new Map(), COMMENT = /<!--[\s\S]*?-->/g, UNFILLED_LINE = /^not investigated$/;
      const youify = s => s;
      const document = {documentElement: {classList: {contains: () => true}}};
      const original = '# River Lane\n\n## Facts\n- Company: [North Studio](../orgs/north.md) [1]\n- Email: secret@example.test [personal]\n- Role: Private role [sensitive]\n- Status: Unknown';
      const translated = '# River Lane\n\n## Facts\n- Company: Wrong translated identity';
      const r = {path:'people/river.md', text:translated, original, translations:{zh:translated}, readLanguage:'zh'};
      const before = parseFacts(r).get('Company')[0].value;
      const choices = identityDetails(r);
      const after = parseFacts(r).get('Company')[0].value;
      console.log(JSON.stringify({before, choices, after, unchanged:r.text === translated}));
    ''')
    assert result == {"before":"Wrong translated identity", "choices":[["Company", "North Studio"]],
                      "after":"Wrong translated identity", "unchanged":True}


def test_related_choice_route_is_passed_to_actual_search_dispatch():
    page = TEMPLATE.read_text()
    route = re.search(r"function route\(.*?\n\}", page, re.S).group(0)
    result = _run_reader_js(route + r'''
      const location = {hash:'#q=related%20to%20River%20Lane&related=people%2Friver-b.md'};
      const navigationRecord = () => null;
      console.log(JSON.stringify(route()));
    ''')
    assert result["related"] == "people/river-b.md"
    assert "else if (query) search(query, related);" in page
