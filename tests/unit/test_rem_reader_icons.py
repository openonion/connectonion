"""The reader's pictures come from two published sets, never from a hand (owner, 2026-11-17).

The owner looked at a person's page and said the GitHub, phone and email pictures "are not very accurate":
a phone number was drawn as a smartphone, LinkedIn was an outline traced by hand, and a GitHub handle was a
speech bubble. Interface icons are now Lucide 0.468.0 and service marks are Simple Icons 16.34.0, both copied
from the published files and named in connectonion/_licenses/rem-reader-icons.txt. These tests keep the map
whole (no caller names a missing key), on its 24 grid, and keep words beside every contact picture.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from connectonion.rem.reader import TEMPLATE

NOTICE = Path(TEMPLATE).parent.parent / '_licenses' / 'rem-reader-icons.txt'
# The shapes the owner called inaccurate: the smartphone that stood for a phone number, the traced LinkedIn
# outline, the rounded envelope, the two arcs that stood for a quotation, and the triangle for a project.
HAND_DRAWN = ['M8.5 2.5h7A2.5 2.5 0 0 1 18 5v14', 'M16 8a6 6 0 0 1 6 6v7h-4', 'M5 4.5h14a2.5 2.5 0 0 1 2.5 2.5v10',
              'M7 17c-2 0-3-1.6-3-3.5', 'M12 4.5 20.5 19h-17z']


def _page():
    return TEMPLATE.read_text()


def _js(script):
    node = shutil.which('node')
    if not node:
        pytest.skip("Node is not installed; it runs the reader's JavaScript")
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _drawn():
    """ICONS and icon() as the page declares them, over a stand-in el()."""
    page = _page()
    return ('const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: (children || []).filter(Boolean)});\n'
            + page[page.index('const ICONS = {'):page.index('// 更多 lists the categories')])


def _icons():
    return _js(_drawn() + '\nconsole.log(JSON.stringify(ICONS));')


def _function(name):
    return re.search(r'(?:const ' + name + r' = \[.*?\n\];|function ' + name + r'\(.*?\n\})', _page(), re.S)[0]


def _referenced():
    page = _page()
    names = set(re.findall(r'\b(?:icon|widgetHead|copyRound)\("([\w-]+)"', page))
    names |= set(re.findall(r'\["[\w-]+", "([\w-]+)", (?:t|label)\(', page))          # the rail's and More's rows
    names |= set(re.findall(r'\btab\("[\w-]+", "([\w-]+)"', page))                     # the phone tab bar
    names |= set(re.findall(r':\s*"([\w-]+)"', re.search(r'const CATEGORY_ICON = \{(.*?)\};', page, re.S)[1]))
    names |= set(re.findall(r'CATEGORY_ICON\[c\] \|\| "([\w-]+)"', page))
    names |= set(_js(_function('HANDLE_MARKS') + '\nconsole.log(JSON.stringify(HANDLE_MARKS.map(m => m[1]).concat("at")));'))
    return names


def test_every_icon_a_caller_names_is_in_the_map():
    icons, named = _icons(), _referenced()
    assert {'mail', 'phone', 'sun', 'calendar', 'book', 'doc', 'brand-github', 'at'} <= named  # the search itself still finds callers
    assert not sorted(named - set(icons)), 'a caller names a picture the map does not hold'


def _endpoints(d):
    """Every point a path's segments end on, absolute. Control points may leave the box; a drawn end may not."""
    width = {'m': 2, 'l': 2, 'h': 1, 'v': 1, 'c': 6, 's': 4, 'q': 4, 't': 2, 'a': 7, 'z': 0}
    number, flag, gap = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'), re.compile(r'[01]'), re.compile(r'[\s,]*')
    points, x, y, start, at, command = [], 0.0, 0.0, (0.0, 0.0), 0, None
    at = gap.match(d, at).end()
    while at < len(d):
        if d[at].lower() in width:
            command, at = d[at], gap.match(d, at + 1).end()
            if command in 'Zz':
                x, y = start
                continue
        assert command and command not in 'Zz', 'not path data at ' + str(at) + ': ' + d[:60]
        args = []
        for n in range(width[command.lower()]):  # an arc's two flags are one digit each and may touch what follows
            found = (flag if command in 'Aa' and n in (3, 4) else number).match(d, at)
            assert found, 'not path data at ' + str(at) + ': ' + d[:60]
            args.append(float(found[0]))
            at = gap.match(d, found.end()).end()
        relative = command.islower()
        if command in 'Hh':
            x = x + args[0] if relative else args[0]
        elif command in 'Vv':
            y = y + args[0] if relative else args[0]
        else:
            x, y = (x + args[-2], y + args[-1]) if relative else (args[-2], args[-1])
        if command in 'Mm':
            start, command = (x, y), 'l' if relative else 'L'
        points.append((x, y))
    return points


def _points(body):
    points = []
    for tag, attrs in re.findall(r'<(\w+)((?:\s+[\w-]+="[^"]*")*)\s*/>', body):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        if tag == 'path':
            assert set(a) == {'d'}, a
            points += _endpoints(a['d'])
        elif tag == 'circle':
            assert set(a) == {'cx', 'cy', 'r'}, a
            cx, cy, r = float(a['cx']), float(a['cy']), float(a['r'])
            points += [(cx - r, cy - r), (cx + r, cy + r)]
        elif tag == 'line':
            assert set(a) == {'x1', 'x2', 'y1', 'y2'}, a
            points += [(float(a['x1']), float(a['y1'])), (float(a['x2']), float(a['y2']))]
        else:
            assert tag in ('polyline', 'polygon') and set(a) == {'points'}, (tag, a)
            numbers = [float(n) for n in a['points'].replace(',', ' ').split()]
            points += list(zip(numbers[::2], numbers[1::2]))
    return points


def test_every_picture_is_plain_shapes_on_a_24_grid():
    """No paint, no radius attribute, no transform of its own: the sheet's .ic owns how a picture is drawn."""
    for name, body in _icons().items():
        assert re.sub(r'<(?:path|circle|line|polyline|polygon)(?:\s+[\w-]+="[^"]*")*\s*/>', '', body) == '', name
        points = _points(body)
        assert points, name
        assert all(0 <= x <= 24 and 0 <= y <= 24 for x, y in points), (name, [p for p in points if not (0 <= p[0] <= 24 and 0 <= p[1] <= 24)])


def test_the_hand_drawn_shapes_are_gone_and_a_phone_number_is_a_handset():
    page, icons = _page(), _icons()
    assert not [shape for shape in HAND_DRAWN if shape in page]
    assert 'linkedin' not in icons  # Simple Icons publishes no LinkedIn mark; the reader does not draw one
    assert icons['phone'].startswith('<path d="M22 16.92v3a2 2 0 0 1-2.18 2')   # Lucide 0.468.0 phone, the handset
    assert icons['mail'].endswith('<path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>')  # Lucide 0.468.0 mail's flap
    assert icons['project'] == icons['folder']  # a project is the rail's Projects picture, not a triangle


def test_a_service_mark_is_one_filled_shape_in_the_pages_ink():
    icons = _icons()
    brands = sorted(name for name in icons if name.startswith('brand-'))
    assert brands == ['brand-discord', 'brand-github', 'brand-telegram', 'brand-wechat', 'brand-whatsapp', 'brand-x']
    assert all(re.fullmatch(r'<path d="[^"]+"/>', icons[name]) for name in brands)  # the published mark, one path, unpainted
    drawn = _js(_drawn() + '\nconsole.log(JSON.stringify(["mail", "brand-github"].map(name => icon(name))));')
    outline, mark = drawn
    assert outline['aria-hidden'] == mark['aria-hidden'] == 'true'  # the word beside it is what is read
    assert '<svg class="ic" viewBox="0 0 24 24">' in outline['html']
    assert '<svg class="ic solid" viewBox="-2 -2 28 28">' in mark['html']  # the mark at 24/28 of the box, beside 2px-inset outlines
    assert icons['brand-github'] in mark['html']
    rule = re.search(r'\.ic\.solid \{([^}]*)\}', _page())[1]
    assert 'fill: currentColor' in rule and 'stroke: none' in rule  # the page's ink, never a brand colour


@pytest.mark.parametrize('value, qualifier, picture, word', [
    ('mara-o', 'GitHub', 'brand-github', 'GitHub'),
    ('https://github.com/mara-o', '', 'brand-github', 'GitHub'),
    ('@mara', 'X', 'brand-x', 'X'),
    ('https://x.com/mara', '', 'brand-x', 'X'),
    ('@mara', 'Twitter', 'brand-x', 'X'),
    ('mara_o', 'WeChat', 'brand-wechat', 'WeChat'),
    ('mara_o', '微信', 'brand-wechat', 'WeChat'),
    ('+64 21 555 0142', 'WhatsApp', 'brand-whatsapp', 'WhatsApp'),
    ('t.me/mara', '', 'brand-telegram', 'Telegram'),
    ('mara#1234', 'Discord', 'brand-discord', 'Discord'),
    ('linkedin.com/in/mara', '', 'at', 'LinkedIn'),   # no published mark: a neutral @ and the name in words
    ('U02ABC', 'Slack', 'at', 'Slack'),
    ('mara', 'Teams', 'at', 'Microsoft Teams'),
    ('mara-o', '', 'at', None),                        # an unnamed handle is a handle
    ('maxine', '', 'at', None),                        # "x" inside a name is not X
    ('alex', 'box', 'at', None),
])
def test_a_handle_carries_its_services_mark_or_an_at_with_the_services_name(value, qualifier, picture, word):
    mark = _js(_function('HANDLE_MARKS') + '\n' + _function('handleMark')
               + '\nconsole.log(JSON.stringify(handleMark(' + json.dumps({'value': value, 'qualifier': qualifier}) + ')));')
    assert mark == [picture, word]


def test_a_contact_button_says_its_kind_in_words_beside_the_value():
    """Owner: state is said in words, never by a mark alone. The hover and focus tip names the kind too."""
    buttons = _js(_drawn() + """
      const t = words => words, hasPrivacy = () => false, navigator = {};
      """ + _function('copyRound') + """
      console.log(JSON.stringify([copyRound("mail", "Email", "a@fernhill.example", "a@fernhill.example · b@mailbox.example"),
        copyRound("phone", "Phone", "+64 21 555 0142"), copyRound("brand-github", "GitHub", "mara-o")]));""")
    assert [button['aria-label'] for button in buttons] == ['Email · a@fernhill.example', 'Phone · +64 21 555 0142', 'GitHub · mara-o']
    tips = [next(child for child in button['children'] if child.get('class') == 'tip')['text'] for button in buttons]
    assert tips == ['Email · a@fernhill.example · b@mailbox.example', 'Phone · +64 21 555 0142', 'GitHub · mara-o']
    assert all(button['children'][0]['aria-hidden'] == 'true' for button in buttons)


def test_the_notice_names_every_picture_and_both_licences():
    notice = NOTICE.read_text()
    assert 'Lucide 0.468.0 (ISC)' in notice and 'Simple Icons 16.34.0 (CC0 1.0 Universal)' in notice
    assert 'Permission to use, copy, modify, and/or distribute this software' in notice
    listed = set(re.findall(r'^   ([\w-]+) -> [\w-]+$', notice, re.M))
    assert listed == set(_icons())
    assert 'rem-reader-icons.txt' in (Path(TEMPLATE).parents[2] / 'docs' / 'cli' / 'rem.md').read_text()
