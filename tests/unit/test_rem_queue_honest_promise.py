"""A queued page says where it really stands in the night's queue (#3420).

"此页已排入今晚队列" sat on 1,241 person pages while a night completed 3 to 10
investigations. 今晚 is said only inside the measured nightly pace.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from connectonion.rem.queue import nightly_throughput
from tests.unit.test_rem_reader import _run_reader_js

TEMPLATE = Path(__file__).parents[2] / "connectonion" / "rem" / "reader.html"
SYDNEY = timezone(timedelta(hours=11))


def _queued_line(language: str, place, pace) -> str:
    page = TEMPLATE.read_text()
    queued = page[page.index('function queuedLine(r) {'):page.index('\nfunction safeHref(')]
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    return _run_reader_js('UI.zh = ' + ui + '; uiLanguage = ' + json.dumps(language) + ';\n'
                          + 'const REM = {night_throughput: ' + json.dumps(pace) + '};\n' + queued
                          + '\nconsole.log(JSON.stringify(queuedLine({queue_place: ' + json.dumps(place) + '})));')


@pytest.mark.parametrize("language", ["en", "zh"])
def test_a_page_inside_the_nightly_pace_says_tonight(language):
    assert _queued_line(language, 3, 5) == ("此页已排入今晚队列" if language == "zh" else "Page queued for tonight")


@pytest.mark.parametrize("language", ["en", "zh"])
def test_a_page_deep_in_the_queue_says_its_place_and_an_estimate_never_tonight(language):
    line = _queued_line(language, 40, 5)
    assert "今晚" not in line and "tonight" not in line
    assert line == ("排队第 40 位 · 按最近每晚约 5 页，约 8 晚内写到" if language == "zh"
                    else "In the queue at #40 · at about 5 pages a night, within about 8 nights")


def test_no_pace_means_a_place_and_no_promise():
    assert _queued_line("zh", 40, None) == "排队第 40 位"


def test_a_page_with_no_place_promises_no_night():
    assert _queued_line("zh", None, 5) == "此页已排队，之后的某一晚会写"


def _run(at: datetime, outcome="completed", phase="investigate") -> dict:
    return {"started_at": at.isoformat(), "phase": phase, "outcome": outcome}


def test_throughput_is_the_median_of_nights_that_ran_counting_completed_investigations():
    base = datetime(2026, 11, 20, 1, 0, tzinfo=SYDNEY)
    logs = []
    for night, done in enumerate([3, 9, 5]):
        start = base + timedelta(days=night)
        logs += [_run(start + timedelta(minutes=10 * i)) for i in range(done)]
        logs += [_run(start, outcome="refused"), _run(start, phase="translate")]
    # 23:30 the evening before belongs to the same night as 01:00.
    logs.append(_run(base - timedelta(minutes=90)))
    assert nightly_throughput(logs, SYDNEY) == 5


def test_no_runs_measures_nothing():
    assert nightly_throughput([], SYDNEY) is None


def test_status_says_tonight_only_when_the_queue_fits_the_pace(tmp_path, monkeypatch):
    from connectonion.cli.commands import rem_status
    from connectonion.rem import queue
    monkeypatch.setattr(queue, "night_pace", lambda root, logs: 5)
    monkeypatch.setattr("connectonion.rem.service.run_logs", lambda root: [])
    assert rem_status._pace(tmp_path, 3) == " for tonight"
    assert rem_status._pace(tmp_path, 1241) == " · the night investigates about 5"
