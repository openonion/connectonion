"""Agenda shows the weather for its days (owner, 2026-11-17: «Why isn't the weather for these days shown on the calendar?»).

The night's calendar step asks Open-Meteo for the week's daily forecast and saves it to .state/weather.json; the
reader shows that file and never calls anyone. Every forecast here is invented and `weather.get_json`, the one
function that talks to Open-Meteo, is replaced: no test reaches it.
"""
from datetime import datetime, timezone

import pytest

from connectonion.rem import weather
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import RemError, read_json, state_path

NIGHT = datetime(2026, 10, 1, 6, 10, tzinfo=timezone.utc)
PLACE = {"results": [{"name": "Sydney", "latitude": -33.86785, "longitude": 151.20732, "country_code": "AU", "timezone": "Australia/Sydney"}]}
DAILY = {"daily": {"time": ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"], "weather_code": [0, 80, 95, 45],
                   "temperature_2m_max": [22.4, 19.6, 17.2, None], "temperature_2m_min": [13.8, 12.1, 11.5, None],
                   "precipitation_probability_max": [5, 70, 90, None]}}


@pytest.fixture
def meteo(monkeypatch, tmp_path):
    """Open-Meteo, answering from `answers`; every request it was sent is in `asked`."""
    asked, answers = [], {weather.PLACES: PLACE, weather.FORECAST: DAILY}

    def get_json(url, params):
        asked.append((url, params))
        if isinstance(answers[url], Exception):
            raise answers[url]
        return answers[url]

    monkeypatch.setattr(weather, "get_json", get_json)
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.timezone", "Australia/Sydney"])
    return asked, answers


def _saved(root):
    return read_json(state_path(root, "weather.json"), None)


def test_the_night_saves_each_days_condition_in_a_word_with_its_high_low_and_chance_of_rain(tmp_path, meteo):
    result = weather.save(tmp_path, NIGHT, read_config(tmp_path))
    assert result == {"days": 3, "error": None}
    saved = _saved(tmp_path)
    assert saved["days"] == [{"date": "2026-10-01", "condition": "clear", "high": 22, "low": 14, "rain": 5},
                             {"date": "2026-10-02", "condition": "showers", "high": 20, "low": 12, "rain": 70},
                             {"date": "2026-10-03", "condition": "storm", "high": 17, "low": 12, "rain": 90}], "a day with no forecast is left out"
    assert saved["source"] == "Open-Meteo" and saved["place"]["name"] == "Sydney" and saved["unit"] == "C"
    assert saved["saved_at"] == saved["read_at"] == "2026-10-01T06:10:00+00:00"
    shown = weather.read(tmp_path)
    assert shown["place"] == "Sydney" and shown["source"] == "Open-Meteo" and shown["error"] is None and len(shown["days"]) == 3


def test_only_a_city_leaves_the_computer_its_name_once_then_its_rounded_coordinates(tmp_path, meteo):
    asked, _ = meteo
    weather.save(tmp_path, NIGHT, read_config(tmp_path))
    weather.save(tmp_path, NIGHT, read_config(tmp_path))
    places = [params for url, params in asked if url == weather.PLACES]
    assert places == [{"name": "Sydney", "count": 1, "language": "en", "format": "json"}], "the timezone's city, asked once and kept"
    forecasts = [params for url, params in asked if url == weather.FORECAST]
    assert len(forecasts) == 2 and forecasts[0] == {
        "latitude": -33.87, "longitude": 151.21, "daily": weather.DAILY, "timezone": "Australia/Sydney",
        "forecast_days": 7, "temperature_unit": "celsius"}


def test_weather_place_names_another_city_and_off_asks_nobody(tmp_path, meteo):
    asked, answers = meteo
    answers[weather.PLACES] = {"results": [{"name": "Portland", "latitude": 45.52345, "longitude": -122.67621, "country_code": "US"}]}
    set_config(tmp_path, ["weather.place", "Portland"])
    weather.save(tmp_path, NIGHT, read_config(tmp_path))
    assert asked[0][1]["name"] == "Portland" and asked[1][1]["temperature_unit"] == "fahrenheit", "units follow the place"
    assert _saved(tmp_path)["unit"] == "F"
    asked.clear()
    set_config(tmp_path, ["weather.place", "off"])
    assert weather.save(tmp_path, NIGHT, read_config(tmp_path)) == {"days": 0, "off": True}
    assert asked == [] and weather.read(tmp_path) is None
    with pytest.raises(RemError):
        set_config(tmp_path, ["weather.units", "kelvin"])


def test_a_notebook_with_no_city_in_its_timezone_asks_nobody(tmp_path, meteo):
    asked, _ = meteo
    set_config(tmp_path, ["schedule.timezone", "UTC"])
    assert weather.place_name(read_config(tmp_path)) == ""
    assert weather.save(tmp_path, NIGHT, read_config(tmp_path)) == {"days": 0, "off": True} and asked == []
    assert weather.place_name({"schedule": {"timezone": "America/Argentina/Buenos_Aires"}}) == "Buenos Aires"


def test_a_failed_read_keeps_the_earlier_forecast_and_says_when_and_why(tmp_path, meteo):
    _, answers = meteo
    weather.save(tmp_path, NIGHT, read_config(tmp_path))
    answers[weather.FORECAST] = TimeoutError("timed out")
    later = datetime(2026, 10, 2, 6, 10, tzinfo=timezone.utc)
    result = weather.save(tmp_path, later, read_config(tmp_path))
    assert result["days"] == 3 and result["error"] == {"reason": "timeout", "at": "2026-10-02T06:10:00+00:00"}
    shown = weather.read(tmp_path)
    assert shown["error"]["reason"] == "timed out" and shown["read_at"] == "2026-10-01T06:10:00+00:00" and len(shown["days"]) == 3
    # A city Open-Meteo does not know is the owner's setting to correct, said in words; not a fault in REM.
    answers[weather.PLACES] = {"generationtime_ms": 0.4}
    set_config(tmp_path, ["weather.place", "Qwghlm"])
    result = weather.save(tmp_path, later, read_config(tmp_path))
    assert result == {"days": 0, "error": {"reason": "not_found", "at": "2026-10-02T06:10:00+00:00"}}, "Sydney's forecast is not Qwghlm's"


def test_the_calendar_step_of_the_night_saves_the_forecast_and_a_fault_in_rem_never_stops_it(tmp_path, monkeypatch, meteo):
    from connectonion.rem import calendar, schedule
    from connectonion.rem.reader import snapshot
    from connectonion.rem.service import run_logs
    _, answers = meteo
    monkeypatch.setattr(calendar, "available", lambda kind: False)
    result = schedule.calendar_round(tmp_path)
    assert result["weather"] == {"days": 3, "error": None}
    assert [day["condition"] for day in snapshot(tmp_path, local=True)["weather"]["days"]] == ["clear", "showers", "storm"]
    assert snapshot(tmp_path)["weather"] is None, "a shared page carries no forecast: it is for his place"
    answers[weather.FORECAST] = {"daily": {"time": ["2026-10-01"]}}  # an answer in a shape REM did not expect
    result = schedule.calendar_round(tmp_path)
    assert result["weather"]["error"]["error"] == "KeyError" and "traceback" not in result["weather"]
    assert "day_plan" in result and "todos" in result, "the rest of the step still ran"
    logged = [run for run in run_logs(tmp_path) if run.get("phase") == "weather"]
    assert len(logged) == 1 and logged[0]["outcome"] == "failed" and "Traceback" in logged[0]["error"]
    assert weather.read(tmp_path)["error"]["reason"] == "a fault in REM" and len(weather.read(tmp_path)["days"]) == 3
