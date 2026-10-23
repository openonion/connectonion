"""Accepted partial work stays visible without claiming complete source coverage."""
import json
import re

import pytest

from connectonion.rem.reader import TEMPLATE
from test_rem_reader import _run_reader_js


def partial_reader(*, language="en", mixed=False):
    page = TEMPLATE.read_text()
    names = ["lastPass", "firstBuild", "runTime", "runEnd", "sameClaim", "sourceName", "runSegments",
             "hypnogram", "runMarkers", "nightBand", "morningBrief", "failureSummary", "runItem", "shellArg"]
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0) for name in names)
    constants = "\n".join(re.search(r"^const " + name + r" = .*$", page, re.M).group(0)
                          for name in ["HOUR", "FAILED", "STAMP"])
    zh = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    setup = "UI.zh = " + zh + "; uiLanguage = " + json.dumps(language) + ";"
    result = _run_reader_js(setup + constants + functions + r'''
      const record = {path:'projects/current.md', title:'Current project', text:'# Current project'};
      const run = {id:'run_partial', started_at:'2026-10-23T07:00:00Z', finished_at:'2026-10-23T07:02:00Z',
        outcome:'partial', phase:'sync', items:12, changed:[record.path], sources:['gmail','codex'],
        error:'Failed to authenticate PRIVATE_PAYLOAD', source_failures:[{source:'gmail', error:'PRIVATE_PAYLOAD'}]};
      const REM = {as_of:'2026-10-23T08:00:00Z', records:[record], owner:'people/owner.md', logs:[
        run, {started_at:'2026-10-20T07:00:00Z', outcome:'completed', changed:[]}]};
      if (MIXED) REM.logs.push({started_at:'2026-10-23T07:04:00Z', outcome:'failed', error:'TimeoutError'});
      const byPath = path => REM.records.find(r => r.path === path), listedRecords = () => REM.records;
      const byActivity = () => 0, known = () => ({status:'Investigated'}), esc = s => String(s);
      const num = String, fmtTime = s => s, label = s => s, href = r => '#r=' + r.path;
      const sectionHead = text => ({text}), nightlyUpdatesOff = () => false;
      const el = (tag, attrs={}, children=[]) => ({tag, ...attrs, children,
        appendChild(x) {this.children.push(x);}, append(...xs) {this.children.push(...xs);},
        insertAdjacentHTML(_, html) {this.children.push({html});}});
      const listWords = xs => xs.join(', '), runTrace = () => null, unwritten = () => [];
      const pageLink = path => ({href:'#r=' + path}), remCommand = s => 'co rem ' + s;
      const commandChip = command => ({command});
      const pass = lastPass();
      console.log(JSON.stringify({attention:pass.failed.map(r => r.outcome),
        changed:pass.changed.map(r => r.path), brief:morningBrief(), band:nightBand(), item:runItem(run),
        segments:runSegments([run], 2 * HOUR)}));
    '''.replace("MIXED", json.dumps(mixed)))
    return result


def test_partial_run_remains_an_attention_state_with_accepted_changes():
    result = partial_reader()
    assert result["attention"] == ["partial"]
    assert result["changed"] == ["projects/current.md"]
    assert result["segments"][0]["failed"] == 1


def test_morning_partial_never_claims_no_change_or_model_auth_failure():
    result = partial_reader()
    brief = json.dumps(result["brief"])
    assert "partially completed" in brief and "Some selected sources could not be read" in brief
    assert "Nothing about your people or projects changed" not in brief
    assert "Model access was refused" not in brief and "PRIVATE_PAYLOAD" not in brief
    assert "#view=activity" in brief


def test_night_band_marks_partial_attention_without_all_clear():
    result = partial_reader()
    text = json.dumps(result["band"])
    assert "need attention" in text
    assert "Nothing stopped early" not in text
    assert "projects/current.md" in text


def test_activity_partial_has_warning_and_log_action():
    result = partial_reader()
    assert result["item"]["class"] == "failed-run"
    text = json.dumps(result["item"])
    assert 'pill warn' in text and "Some selected sources could not be read" in text
    assert "co rem logs 'run_partial'" in text and "PRIVATE_PAYLOAD" not in text


def test_partial_and_failure_are_counted_separately():
    brief = json.dumps(partial_reader(mixed=True)["brief"])
    assert "1 run failed" in brief and "1 run partially completed" in brief
    assert "2 runs failed" not in brief and "A request timed out" in brief


def test_partial_attention_copy_is_translated():
    result = partial_reader(language="zh")
    assert "部分已选来源无法读取" in json.dumps(result, ensure_ascii=False)
    assert "partially completed" not in json.dumps(result, ensure_ascii=False)
