"""One token sheet for states and motion (#3359 T1, after Rare UI's craft; no code taken from it).

Hover, pressed, overlay and tint colours are tokens of ink or paper at an alpha, written once in the sheet, so
no rule invents its own color-mix() and dark mode follows by itself. Motion uses two springs sampled once into
CSS linear(): a snappy one with a small overshoot for presses and pops, a soft one with none for things that
rise. The names in-flight work already reads (--ink, --rule, --well, --e1..3, --spring, --scrim) stay defined.
"""
import re

from tests.unit.test_rem_reader_style_sheet import _blocks, _parts


def _light():
    return _blocks(_parts()[0])[('', ':root')]


def _curve(value):
    assert value.startswith('linear(') and value.endswith(')'), value
    return [float(p) for p in value[len('linear('):-1].split(',')]


def test_no_rule_mixes_its_own_colour():
    """Outside the sheet, a state colour is a token: color-mix() lives only in the sheet."""
    sheet, css, js, markup, inline = _parts()
    found = [m.group(0) for m in re.finditer(r'color-mix\([^;]{0,60}', css + inline + js)]
    assert not found, f'{len(found)} color-mix() outside the sheet: {found[:5]}'


def test_state_tokens_are_ink_or_paper_at_an_alpha():
    light = _light()
    for name, percent in (('--fill-hover', 4), ('--fill-press', 7)):
        assert light[name] == f'color-mix(in srgb, var(--ink) {percent}%, transparent)', name
    assert 'var(--ink)' in light['--overlay'] and 'var(--paper)' in light['--veil']


def test_the_two_springs_are_sampled_curves():
    light = _light()
    snappy, soft = _curve(light['--spring']), _curve(light['--spring-soft'])
    for points in (snappy, soft):
        assert points[0] == 0 and points[-1] == 1 and len(points) >= 12
    assert 1.0 < max(snappy) <= 1.2, 'a press may overshoot a little, never bounce'
    assert max(soft) <= 1.0, 'a rise settles without overshoot'


def test_the_names_in_flight_work_reads_stay_defined():
    light = _light()
    for name in ('--ink', '--rule', '--well', '--e1', '--e2', '--e3', '--spring', '--scrim', '--green', '--paper'):
        assert name in light, name
