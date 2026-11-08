"""The reader is painted from one token sheet ("Fuse") and nothing else.

Every round of reader design used to add its own namespace (--r4-*, --ov-*,
--gx-*, the Projects --bg/--surface set) and its own literal sizes, until the
page carried thirty font sizes, seven weights and some four hundred colour
literals. A new page then picked whichever looked closest, so no two pages
agreed. This lint keeps the sheet the only place a size, weight, radius,
shadow or colour can be written: outside it, those properties may only name
a token (or inherit/0/none/transparent/currentColor).

The sheet sits between `/* fuse:tokens */` and `/* /fuse:tokens */` in the
first <style>: one light `:root`, its dark twin under the two theme selectors
the reader already used (`prefers-color-scheme` unless data-theme="light", and
data-theme="dark"), and a reduced-motion block that zeroes the durations.
Media-query breakpoints are exempt because CSS cannot read var() there.
"""

import re

from connectonion.rem.reader import TEMPLATE

START, END = '/* fuse:tokens */', '/* /fuse:tokens */'
KEYWORDS = {'inherit', 'initial', 'unset', '0', 'none', 'transparent', 'currentcolor'}
# Which token family each property may name.
FAMILY = {'font-size': r'--s-[\w-]+', 'font-weight': r'--w-[\w-]+',
          'radius': r'--radius|--round', 'box-shadow': r'--shadow'}
PROPS = re.compile(r'(?<![\w-])(font-size|font-weight|font|box-shadow|'
                   r'border(?:-(?:top|bottom|start|end)-(?:left|right|start|end))?-radius)\s*:\s*([^;{}"`]+)')
COLOUR = re.compile(r'#[0-9a-fA-F]{3,8}(?![\w-])|\b(?:rgba?|hsla?)\(')
# Namespaces earlier rounds added; each must stay gone, not come back beside the sheet.
RETIRED = re.compile(r'--(?:r4-|ov-|gx-|today-font\b|bg\b|surface\b)')


def _html():
    return TEMPLATE.read_text(encoding='utf-8')


def _strip_css_comments(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def _strip_js_comments(js):
    js = re.sub(r'/\*.*?\*/', '', js, flags=re.S)
    # A line comment starts at // not preceded by ':' (so "https://" survives).
    return re.sub(r'(?<![:\\"\'`])//[^\n]*', '', js)


def _parts():
    html = _html()
    styles = re.findall(r'<style[^>]*>(.*?)</style>', html, re.S)
    first = styles[0] if styles else ''
    sheet = first.split(START, 1)[1].split(END, 1)[0] if START in first and END in first else ''
    rest = [first.replace(sheet, '')] + styles[1:]
    css = _strip_css_comments('\n'.join(rest))
    scripts = re.findall(r'<script(?![^>]*application/json)[^>]*>(.*?)</script>', html, re.S)
    js = _strip_js_comments('\n'.join(s for s in scripts if s.strip() != '/*__D3__*/'))
    markup = re.sub(r'<(style|script)[^>]*>.*?</\1>', '', html, flags=re.S)
    inline = ' ; '.join(re.findall(r'style="([^"]*)"', markup))
    return sheet, css, js, inline


def _blocks(sheet):
    """The sheet's rule bodies keyed by selector (at-rule wrappers included)."""
    sheet = _strip_css_comments(sheet)
    out = {}
    for media, selector, body in re.findall(r'(@media[^{]*\{\s*)?([^{}@]+?)\s*\{([^{}]*)\}', sheet):
        out[(media.strip().rstrip('{').strip(), selector.strip())] = dict(
            (k, v.strip()) for k, v in re.findall(r'(--[\w-]+)\s*:\s*([^;]+)', body))
    return out


def _tokens():
    names = set()
    for props in _blocks(_parts()[0]).values():
        names |= set(props)
    return names


def _bad_value(prop, value):
    value = re.sub(r'\s*!important\s*$', '', value.strip())
    if value.lower() in KEYWORDS:
        return False
    if prop == 'font':
        # The shorthand carries a size and a weight, so both must be tokens; line-height may follow '/'.
        return not re.fullmatch(r'(?:italic\s+)?(?:var\(--w-[\w-]+\)\s+)?var\(--s-[\w-]+\)'
                                r'(?:\s*/\s*(?:[\d.]+(?:px)?|var\(--lh-[\w-]+\)))?\s+var\(--(?:font|mono)\)', value)
    family = FAMILY['radius' if prop.endswith('radius') else prop]
    return not re.fullmatch(rf'var\((?:{family})\)', value)


def _violations():
    sheet, css, js, inline = _parts()
    found = []
    for where, text in (('css', css), ('inline', inline), ('js', js)):
        for prop, value in PROPS.findall(text):
            if where == 'js' and not re.search(r'[\d#(]', value):
                continue  # a JS key that merely shares a CSS name, e.g. "font: font"
            if _bad_value(prop, value):
                found.append(f'{where}: {prop}: {value.strip()[:60]}')
        for hit in COLOUR.finditer(text):
            found.append(f'{where}: colour {text[hit.start():hit.start() + 24]!r}')
    # JS that paints without CSS: element.style, d3 .style/.attr, canvas fonts.
    for prop, value in re.findall(r'\.style\.(fontSize|fontWeight|borderRadius|boxShadow)\s*=\s*([^;\n]+)', js):
        found.append(f'js: style.{prop} = {value[:60]}')
    # A size the JS interpolates is still a size. The one allowed is the org chart's SVG labels,
    # which are in user units and derived from --s-meta (orgLabelPlan); any other is a new size.
    interpolated = re.findall(r'font-size:\s*\$\{(\w+)\}', js)
    if interpolated != ['fs'] or 'fs = v.phone ? meta * 21 / 12 : meta' not in js:
        found.append(f'js: interpolated font-size {interpolated}')
    for value in re.findall(r'ctx\.font\s*=\s*([^;\n]+)', js):
        if re.search(r'\d', value):
            found.append(f'js: ctx.font = {value[:60]}')
    tokens = _tokens()
    for name in re.findall(r'(--[\w-]+)\s*:', css + ' ; ' + inline):
        if name in tokens or RETIRED.match(name):
            found.append(f'css: {name} defined outside the sheet')
    return found


def test_the_reader_paints_only_from_the_token_sheet():
    found = _violations()
    assert not found, f'{len(found)} literals outside the Fuse sheet:\n' + '\n'.join(found[:80])


def test_the_sheet_has_four_sizes_two_weights_and_no_shadow():
    blocks = _blocks(_parts()[0])
    light = blocks.get(('', ':root'), {})
    assert sorted(n for n in light if n.startswith('--s-')) == ['--s-body', '--s-display', '--s-head', '--s-meta']
    assert sorted(n for n in light if n.startswith('--w-')) == ['--w-bold', '--w-regular']
    assert light['--radius'] == '0' and light['--shadow'] == 'none'
    for name in ('--paper', '--ink', '--grey', '--rule', '--green', '--on-green', '--red', '--pencil'):
        assert COLOUR.fullmatch(light[name]), name
    assert not RETIRED.search(' '.join(light))


def test_dark_is_the_same_names_under_the_existing_theme_selectors():
    blocks = _blocks(_parts()[0])
    light = blocks[('', ':root')]
    auto = blocks[('@media (prefers-color-scheme: dark)', ':root:not([data-theme="light"])')]
    forced = blocks[('', ':root[data-theme="dark"]')]
    assert auto == forced, 'the two dark selectors must agree'
    assert auto and set(auto) <= set(light), set(auto) - set(light)
    motion = blocks[('@media (prefers-reduced-motion: reduce)', ':root')]
    assert motion and all(n.startswith('--t-') and v == '0ms' for n, v in motion.items())
    assert {n for n in light if n.startswith('--t-')} == set(motion)


def test_every_var_the_reader_names_is_defined():
    """Deleting a namespace must not leave a var() that silently resolves to nothing."""
    sheet, css, js, inline = _parts()
    defined = _tokens() | set(re.findall(r'(--[\w-]+)\s*:', css + inline))
    defined |= set(re.findall(r'setProperty\(\s*["\'](--[\w-]+)', js))
    defined |= set(re.findall(r'["\'](--[\w-]+)["\']\s*:', js))
    defined |= set(re.findall(r'[`"\';](--[\w-]+):', js))  # a style string the JS builds: `--d:${...}s`
    used = set(re.findall(r'var\(\s*(--[\w-]+)', css + inline + js))
    used |= set(re.findall(r'(?:graphCss|token)\(\s*["\'](--[\w-]+)', js))
    assert not used - defined, sorted(used - defined)


def test_the_lint_catches_what_it_guards():
    """A lint that under-reads passes everything; prove each rule fires on a planted literal."""
    assert _bad_value('font-size', '13px') and _bad_value('font-weight', '600')
    assert _bad_value('border-radius', '6px') and _bad_value('box-shadow', '0 1px 2px var(--ink)')
    assert _bad_value('font-size', 'var(--w-bold)') and _bad_value('font', '700 12px var(--font)')
    assert not _bad_value('font', 'var(--w-bold) var(--s-meta)/1.4 var(--font)')
    assert not _bad_value('font-size', 'var(--s-meta) !important') and not _bad_value('border-radius', '0')
    assert not _bad_value('box-shadow', 'none') and not _bad_value('border-top-left-radius', 'var(--radius)')
    planted = '.x { color: #fff; background: rgba(0,0,0,.1); font-size: 13px }'
    assert len(COLOUR.findall(planted)) == 2 and PROPS.findall(planted) == [('font-size', '13px ')]
    assert _strip_js_comments('a = "https://x"; // see #2008') == 'a = "https://x"; '
