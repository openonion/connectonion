"""The reader has one written visual system (docs/cli/rem-visual-system.md, #3096) and this holds it.

The owner, on Projects: «I don't think the designer ever fixed a colour palette and the type. The
timeline and the list use different type. Why is the type so small? The table looks like a mess.»
The token sheet already kept literals out (test_rem_reader_style_sheet.py), so nothing was off the
sheet, and the page was still unreadable: three declarations in five set the 11px caption size,
tables among them, and thirty-seven different line-heights were written out by hand.

So this test counts the two things a token lint cannot see, by place:

- caption: a declaration at `--s-meta` (11px), under the 13px minimum for anything a person reads;
- leading: a line-height written out instead of one of the five `--lh-*` steps.

A place that has been brought onto the system is at zero and must stay there. The others carry a
counted allowance that may only go down: a later task lowers the number in the same change that
fixes the place. Families and sizes outside the scale are at zero everywhere and stay there.
"""

import re
from collections import Counter
from pathlib import Path

from connectonion.rem.reader import TEMPLATE

DOC = Path(__file__).resolve().parents[2] / 'docs' / 'cli' / 'rem-visual-system.md'
FAMILIES = {'var(--font)', 'var(--mono)', 'inherit'}
# The scale, smallest first. --s-meta is the caption step: axis ticks and badges, never a sentence or a cell.
SCALE = {'--s-meta': '11px', '--s-ui': '13px', '--s-body': '15px', '--s-lead': '17px', '--s-title': '20px',
         '--s-head': '24px', '--s-display': '44px'}
LEADING = {'--lh-tight': '1.05', '--lh-head': '1.25', '--lh-ui': '1.4', '--lh-body': '1.55', '--lh-read': '1.7'}
# First match wins; a rule is filed under the first selector class that names a place.
PLACES = (('projects', r'\.pd\b|\.pd-|\.pa\b|\.pa-|\.project-|\.projects-view|\.record-focus\.projects'),
          ('people', r'\.r4-people|\.people-|\.rhythm|\.person-|\.contact-|\.rh-'),
          ('organisations', r'\.ov\b|\.ov-|\.org-'),
          ('knowledge', r'\.gx\b|\.gx-|\.topic-'),
          ('agenda', r'\.ag\b|\.ag-|\.agenda|\.cal-'),
          ('sessions', r'\.session'),
          ('today', r'\.today|\.q[a-z]+\b|\.night-|\.deal\b|\.morning|\.n3-'),
          ('record', r'\.focus-|\.deep-|\.note\b|\.factlist|\.fact-|\.relation|\.evidence|\.memory-|\.cite\b'))
# What is left to burn down, by place. Projects is done (#3096) and stays at zero. Lower a number in the
# change that fixes its place; never raise one.
CAPTION_ALLOWED = {'projects': 0, 'people': 18, 'organisations': 58, 'knowledge': 28, 'agenda': 10, 'sessions': 37,
                   'today': 25, 'record': 42, 'shared': 203}
LEADING_ALLOWED = {'projects': 0, 'people': 10, 'organisations': 37, 'knowledge': 25, 'agenda': 8, 'sessions': 39,
                   'today': 43, 'record': 34, 'shared': 151}


def _rules(html=None):
    """(selector, body) for every CSS rule outside the token sheet, comments removed."""
    html = TEMPLATE.read_text(encoding='utf-8') if html is None else html
    css = '\n'.join(re.findall(r'<style[^>]*>(.*?)</style\b[^>]*>', html, re.S | re.I))
    css = re.sub(r'/\* fuse:tokens \*/.*?/\* /fuse:tokens \*/', '', css, flags=re.S)
    return re.findall(r'([^{}@;]+?)\s*\{([^{}]*)\}', re.sub(r'/\*.*?\*/', '', css, flags=re.S))


def _place(selector):
    return next((name for name, pattern in PLACES if re.search(pattern, selector)), 'shared')


def _declarations(body):
    return [(prop, value.strip()) for prop, value in
            re.findall(r'(?<![\w-])(font-family|font-size|font|line-height)\s*:\s*([^;]+)', body)]


def _leading(prop, value):
    """The line-height a declaration writes, or '' when it names none."""
    if prop == 'line-height':
        return value
    found = re.search(r'/\s*([^\s]+)', value) if prop == 'font' else None
    return found.group(1) if found else ''


def inventory(html=None):
    """Counts by place: families off the stacks, sizes off the scale, captions, and written-out leading."""
    out = {key: Counter() for key in ('family', 'size', 'caption', 'leading')}
    for selector, body in _rules(html):
        place = _place(selector)
        for prop, value in _declarations(body):
            value = re.sub(r'\s*!important$', '', value)
            if prop == 'font-family' and value not in FAMILIES:
                out['family'][place] += 1
            if prop == 'font' and value != 'inherit' and not re.search(r'var\(--(?:font|mono)\)$', value):
                out['family'][place] += 1
            sizes = re.findall(r'var\((--s-[\w-]+)\)', value) if prop in ('font', 'font-size') else []
            if prop == 'font-size' and not sizes and value not in ('0', 'inherit'):
                out['size'][place] += 1
            out['size'][place] += sum(1 for name in sizes if name not in SCALE)
            out['caption'][place] += sizes.count('--s-meta')
            leading = _leading(prop, value)
            if leading and not re.fullmatch(r'var\(--lh-[\w-]+\)|inherit|normal', leading):
                out['leading'][place] += 1
    return out


def _sheet():
    html = TEMPLATE.read_text(encoding='utf-8')
    sheet = html.split('/* fuse:tokens */', 1)[1].split('/* /fuse:tokens */', 1)[0]
    return dict(re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', sheet.split('}', 1)[0]))


def test_the_sheet_holds_the_written_scale_and_the_document_names_every_step():
    light, words = _sheet(), DOC.read_text(encoding='utf-8')
    assert {name: light[name] for name in light if name.startswith('--s-')} == SCALE
    assert {name: light[name] for name in light if name.startswith('--lh-')} == LEADING
    for name in [*SCALE, *LEADING, '--font', '--mono', '--ink', '--grey', '--pencil', '--rule', '--well', '--paper',
                 '--green', '--red', *(f'--heat-{n}' for n in range(5))]:
        assert name in light, name
        assert f'`{name}`' in words, f'{name} is in the sheet and not in the written system'


def test_no_place_sets_its_own_family_or_a_size_off_the_scale():
    found = inventory()
    assert not sum(found['family'].values()), dict(found['family'])
    assert not sum(found['size'].values()), dict(found['size'])


def test_caption_size_and_written_out_leading_only_go_down_and_projects_has_none():
    found = inventory()
    assert CAPTION_ALLOWED['projects'] == LEADING_ALLOWED['projects'] == 0
    for kind, allowed in (('caption', CAPTION_ALLOWED), ('leading', LEADING_ALLOWED)):
        over = {place: (n, allowed.get(place, 0)) for place, n in found[kind].items() if n > allowed.get(place, 0)}
        assert not over, f'{kind} (found, allowed) went up: {over}. Use the scale; see docs/cli/rem-visual-system.md'


def test_the_count_catches_what_it_guards():
    plant = lambda css: inventory(TEMPLATE.read_text(encoding='utf-8').replace('</style>', css + '</style>', 1))
    base = inventory()
    assert plant('.pd-x{font-family:Georgia}')['family']['projects'] == base['family']['projects'] + 1
    assert plant('.pd-x{font:var(--s-body)/1.5 Georgia}')['family']['projects'] == base['family']['projects'] + 1
    assert plant('.pd-x{font-size:var(--s-tiny)}')['size']['projects'] == base['size']['projects'] + 1
    assert plant('.pd-x{font:var(--s-meta)/var(--lh-ui) var(--font)}')['caption']['projects'] == base['caption']['projects'] + 1
    assert plant('.pd-x{line-height:1.5}')['leading']['projects'] == base['leading']['projects'] + 1
    assert plant('.zz-x{font:var(--s-body)/18px var(--font)}')['leading']['shared'] == base['leading']['shared'] + 1
