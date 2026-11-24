"""The forecast for the days on the owner's calendar, saved by the night for Agenda.

Owner, 2026-11-17: «Why isn't the weather for these days shown on the calendar?»
The step of the night that saves `.state/calendar.json` asks Open-Meteo for the
next week's daily forecast and saves it to `.state/weather.json`; the reader
shows that file and never calls anyone. A read that fails keeps the forecast
saved before, with when and why, and never stops the night (calendar.py's
shape): a provider's failure is one word, a fault in REM carries its
exception's name here and its traceback to `co rem logs`.

What leaves this computer, once a night: a city's name to Open-Meteo's
geocoding (the first time, then its answer is kept) and that city's
coordinates, rounded to two decimals, to its forecast. Never an address, a
calendar entry or anything from the notebook. The city is `weather.place`
(`co rem config set weather.place Sydney`), else the city of the notebook's
timezone; `weather.place off` asks nobody.

Open-Meteo needs no key and no account. Its free API is for non-commercial use
and its data is CC BY 4.0, so the page names it as the source
(open-meteo.com/en/terms, read 2026-11-17).

`get_json` is the one place that talks to Open-Meteo; tests replace it.
"""

import traceback

from .files import read_json, state_path, write_json

SOURCE = 'Open-Meteo'
PLACES = 'https://geocoding-api.open-meteo.com/v1/search'
FORECAST = 'https://api.open-meteo.com/v1/forecast'
DAYS = 7  # a forecast past a week says little; the API's own default
DAILY = 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max'
# WMO weather interpretation codes (WW) as Open-Meteo lists them (open-meteo.com/en/docs, read 2026-11-17),
# folded into the eight conditions the page has a word and a picture for. Drizzle and freezing rain are rain.
CONDITIONS = {'clear': (0, 1), 'partly cloudy': (2,), 'cloudy': (3,), 'fog': (45, 48),
              'rain': (51, 53, 55, 56, 57, 61, 63, 65, 66, 67), 'showers': (80, 81, 82),
              'snow': (71, 73, 75, 77, 85, 86), 'storm': (95, 96, 97, 99)}
# Units follow the place: the countries that read a forecast in Fahrenheit; everywhere else Celsius.
FAHRENHEIT = {'US', 'BS', 'BZ', 'KY', 'LR', 'PW', 'FM', 'MH'}


class PlaceNotFound(Exception):
    """Open-Meteo knows no city of that name: the owner's setting to correct, not a fault in REM."""


def condition(code) -> str:
    return next((word for word, codes in CONDITIONS.items() if code in codes), 'cloudy')


def place_name(config: dict) -> str:
    """The city to ask about: weather.place, else the notebook timezone's city; '' when off or unknown."""
    asked = str(config.get('weather', {}).get('place', '')).strip()
    if asked.casefold() == 'off':
        return ''
    zone = config.get('schedule', {}).get('timezone', '')
    return asked or (zone.rsplit('/', 1)[-1].replace('_', ' ') if '/' in zone else '')


def get_json(url: str, params: dict) -> dict:
    import httpx
    response = httpx.get(url, params=params, timeout=20)
    if response.status_code >= 400:
        error = OSError(f'{SOURCE} answered HTTP {response.status_code}')
        error.status = response.status_code  # fetch_stalls reads the provider's failure from here
        raise error
    return response.json()


def locate(name: str, kept: dict) -> dict:
    """The city's coordinates, asked once and kept; rounded, so what is sent each night is a city, not a street."""
    if kept.get('asked') == name and 'latitude' in kept:
        return kept
    found = get_json(PLACES, {'name': name, 'count': 1, 'language': 'en', 'format': 'json'}).get('results') or []
    if not found:
        raise PlaceNotFound(name)
    return {'asked': name, 'name': found[0]['name'], 'latitude': round(found[0]['latitude'], 2),
            'longitude': round(found[0]['longitude'], 2), 'country_code': found[0].get('country_code', '')}


def forecast(place: dict, zone: str) -> tuple[list[dict], str]:
    """Each day's condition word, high, low and chance of rain, and the unit they are in."""
    unit = 'F' if place['country_code'] in FAHRENHEIT else 'C'
    daily = get_json(FORECAST, {'latitude': place['latitude'], 'longitude': place['longitude'], 'daily': DAILY,
                                'timezone': zone or 'auto', 'forecast_days': DAYS,
                                'temperature_unit': 'fahrenheit' if unit == 'F' else 'celsius'})['daily']
    rows = zip(daily['time'], daily['weather_code'], daily['temperature_2m_max'], daily['temperature_2m_min'],
               daily['precipitation_probability_max'])
    return [{'date': day, 'condition': condition(code), 'high': round(high), 'low': round(low), 'rain': rain}
            for day, code, high, low, rain in rows if high is not None and low is not None], unit


def save(root, moment, config: dict) -> dict:
    """Read the week's forecast into .state/weather.json; `night` calls this."""
    from .calendar import BUG, _reason
    path, stamp, name = state_path(root, 'weather.json'), moment.isoformat(timespec='seconds'), place_name(config)
    if not name:
        write_json(path, {'saved_at': stamp, 'off': True, 'days': []})
        return {'days': 0, 'off': True}
    saved = read_json(path, {})
    kept = saved if saved.get('place', {}).get('asked') == name else {}  # another city's forecast is not this one's
    state = {'saved_at': stamp, 'source': SOURCE, 'place': kept.get('place', {'asked': name, 'name': name}),
             'unit': kept.get('unit', 'C'), 'read_at': kept.get('read_at', ''), 'days': kept.get('days', []), 'error': None}
    fault = {}
    try:
        place = locate(name, state['place'])
        days, unit = forecast(place, config.get('schedule', {}).get('timezone', ''))
        state.update(place=place, unit=unit, days=days, read_at=stamp)
    except Exception as error:  # noqa: BLE001 - no forecast may stop the night; a fault in REM is named, not hidden
        reason = 'not_found' if isinstance(error, PlaceNotFound) else _reason(error)
        state['error'] = {'reason': reason or BUG, 'at': stamp, **({} if reason else {'error': type(error).__name__})}
        fault = {} if reason else {'traceback': traceback.format_exc()}
    write_json(path, state)
    return {'days': len(state['days']), 'error': state['error'], **fault}


def night(root, moment) -> dict:
    """The night's weather step. A fault in REM is a failed run with its traceback in `co rem logs`, out of the
    round's result; nothing here stops the rest of the night."""
    from .config import read_config
    from .daily import _reserve
    try:
        result = save(root, moment, read_config(root))
    except Exception as error:  # noqa: BLE001 - same background isolation as the calendar snapshot
        result = {'days': 0, 'error': {'reason': 'bug', 'at': moment.isoformat(), 'error': type(error).__name__},
                  'traceback': traceback.format_exc()}
    if 'traceback' in result:
        record, path = _reserve(root, 'weather', 0, {})
        record.update(outcome='failed', error='weather: ' + result.pop('traceback'), finished_at=moment.isoformat())
        write_json(path, record)
    return result


def read(root) -> dict | None:
    """What Agenda shows; None when no night has saved a forecast or weather is off."""
    from .fetch_stalls import PHRASES
    saved = read_json(state_path(root, 'weather.json'), None)
    if saved is None or saved.get('off'):
        return None
    error = saved.get('error')
    return {'place': saved['place'].get('name', ''), 'source': saved['source'], 'unit': saved['unit'],
            'read_at': saved.get('read_at', ''), 'days': saved.get('days', []),
            'error': error and {'at': error['at'], 'reason': PHRASES.get(error['reason'], 'a fault in REM'),
                                'error': error.get('error', '')}}
