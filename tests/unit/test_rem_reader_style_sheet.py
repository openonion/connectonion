"""The reader is painted from one token sheet (N3 "Desk", D-123; it replaced "Fuse") and nothing else.

Every round of reader design used to add its own namespace (--r4-*, --ov-*,
--gx-*, the Projects --bg/--surface set) and its own literal sizes, until the
page carried thirty font sizes, seven weights and some four hundred colour
literals. A new page then picked whichever looked closest, so no two pages
agreed. This lint keeps the sheet the only place a size, weight, radius,
shadow, colour or duration can be written.

The sheet sits between `/* fuse:tokens */` and `/* /fuse:tokens */` in the
first <style>: one light `:root`, its dark twin under the two theme selectors
the reader already used (`prefers-color-scheme` unless data-theme="light", and
data-theme="dark"), and a reduced-motion block that zeroes the durations.
Everything else in the document is scanned, case-insensitively: <style>,
style attributes (quoted or not), SVG and legacy HTML attributes, url() data,
the script and the strings it builds. Media-query breakpoints are exempt
because CSS cannot read var() there.

Out of scope, on purpose: a value that only exists at run time (a named colour
held in a JS variable and then assigned, a size computed into a variable),
currentColor, CSS escapes inside identifiers, user-agent defaults such as <h1>
or <strong>, and properties that scale or tint without naming a size or a
colour (zoom, transform, opacity, blend modes, hue-rotate). Those need review,
not a regex.
"""

import re

from connectonion.rem.reader import TEMPLATE

START, END = '/* fuse:tokens */', '/* /fuse:tokens */'
KEYWORDS = {'inherit', 'initial', 'unset', '0', 'none', 'transparent', 'currentcolor'}
# Which token family each property may name; a property missing here takes keywords only.
FAMILY = {'font-size': r'--s-[\w-]+', 'font-weight': r'--w-[\w-]+', 'radius': r'--radius|--round|--r-[\w-]+',
          'box-shadow': r'--e[\w-]*'}
RADIUS = r'border(?:-(?:top|bottom|left|right|start|end)(?:-(?:left|right|start|end))?)?-radius'
PROPS = re.compile(rf'(?<![\w-])(font-size|font-weight|font|box-shadow|text-shadow|font-variation-settings|'
                   rf'filter|backdrop-filter|clip-path|shape-outside|{RADIUS})\s*:\s*([^;{{}}"\'`]+)')
COLOUR = re.compile(r'#[0-9a-fA-F]{3,8}(?![\w-])|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(|%23[0-9a-fA-F]{3,8}', re.I)
NAMED = set('''aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown
burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod
darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon
darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey
dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray green greenyellow grey
honeydew hotpink indianred indigo ivory khaki lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral
lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue
lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine
mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise
mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered
orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum powderblue purple
rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue
slategray slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow
yellowgreen canvas canvastext linktext visitedtext activetext buttonface buttontext highlight highlighttext graytext
mark marktext field fieldtext accentcolor accentcolortext'''.split())
COLOUR_PROPS = (r'color|background(?:-color)?|border(?:-[a-z]+)*|outline(?:-color)?|fill|stroke|stop-color|'
                r'flood-color|lighting-color|text-decoration(?:-color)?|caret-color|accent-color|column-rule(?:-color)?|'
                r'text-emphasis-color|--[\w-]+')
MOTION = re.compile(r'(?<![\w-])(transition|transition-duration|transition-timing-function|transition-delay|animation|'
                    r'animation-duration|animation-timing-function|animation-delay)\s*:\s*([^;{}"\'`]+)')
# Declarations whose words are names, not colours, so the named-colour check skips them.
NOT_PAINT = {'content', 'font-family', 'font', 'animation', 'animation-name', 'transition', 'transition-property',
             'will-change', 'grid-template-areas', 'grid-area', 'counter-reset', 'counter-increment', 'list-style',
             'list-style-type', 'quotes', 'cursor', 'text-transform', 'syntax', 'mask', '-webkit-mask', 'mask-image',
             '-webkit-mask-image'}
# A layout var's value: a length or a plain number, nothing that could carry a colour, a duration or a weight.
LAYOUT_VALUE = re.compile(r'-?[\d.]*(?:px|%|em|rem|vw|vh|ch)?')
# Custom properties the reader may set outside the sheet: layout measures and per-element stagger counts
# (--d, multiplied by --t-stagger), never a colour, size, weight, radius, shadow or duration.
LAYOUT_VARS = {'--cols', '--name', '--note', '--d', '--depth', '--from', '--sheet-top',
               '--evidence-top-height', '--evidence-find-height'}
DESIGN_CAMEL = r'fontSize|fontWeight|font|borderRadius|boxShadow|textShadow|fontVariationSettings|filter'
COLOUR_CAMEL = r'color|background|backgroundColor|borderColor|outlineColor|fill|stroke'
# Namespaces earlier rounds added; each must stay gone, not come back beside the sheet.
RETIRED = re.compile(r'--(?:r4-|ov-|gx-|today-font\b|bg\b|surface\b)')


def _html():
    return TEMPLATE.read_text(encoding='utf-8')


def _strip_css_comments(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def _strip_js_comments(js):
    js = re.sub(r'/\*.*?\*/', '', js, flags=re.S)
    # A line comment starts at // not preceded by ':' (so "https://" survives) or a quote or escape.
    return re.sub(r'(?<![:\\"\'`])//[^\n]*', '', js)


def _parts(html=None):
    """(sheet, css, js, markup, inline): every place a style can be written, comments removed."""
    html = _html() if html is None else html
    html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    # Tags in any case, closers with anything before '>' (as browsers accept): the lint must not be bypassed by <STYLE>.
    styles = re.findall(r'<style[^>]*>(.*?)</style\b[^>]*>', html, re.S | re.I)
    first = styles[0] if styles else ''
    sheet = first.split(START, 1)[1].split(END, 1)[0] if START in first and END in first else ''
    css = _strip_css_comments('\n'.join([first.replace(sheet, '')] + styles[1:]))
    scripts = re.findall(r'<script(?![^>]*application/json)[^>]*>(.*?)</script\b[^>]*>', html, re.S | re.I)
    js = _strip_js_comments('\n'.join(s for s in scripts if s.strip() != '/*__D3__*/'))
    markup = re.sub(r'<(style|script)[^>]*>.*?</\1\b[^>]*>', '', html, flags=re.S | re.I)
    inline = ' ; '.join(a or b or c for a, b, c in re.findall(
        r'\bstyle\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>"\']+))', markup, re.I))
    return sheet, css, js, markup, inline


def _blocks(sheet):
    """The sheet's rule bodies keyed by (at-rule, selector)."""
    sheet = _strip_css_comments(sheet)
    out = {}
    for media, selector, body in re.findall(r'(@media[^{]*\{\s*)?([^{}@]+?)\s*\{([^{}]*)\}', sheet):
        out[(media.strip().rstrip('{').strip(), selector.strip())] = dict(
            (k, v.strip()) for k, v in re.findall(r'(--[\w-]+)\s*:\s*([^;]+)', body))
    return out


def _tokens(html=None):
    names = set()
    for props in _blocks(_parts(html)[0]).values():
        names |= set(props)
    return names


def _bad_value(prop, value):
    value = re.sub(r'\s*!important\s*$', '', value.strip())
    if value.lower() in KEYWORDS or (prop == 'font-variation-settings' and value == 'normal'):
        return False
    if prop == 'font':
        # The shorthand carries a size and a weight, so both must be tokens; line-height may follow '/'.
        return not re.fullmatch(r'(?:italic\s+)?(?:var\(--w-[\w-]+\)\s+)?var\(--s-[\w-]+\)'
                                r'(?:\s*/\s*(?:[\d.]+(?:px)?|var\(--lh-[\w-]+\)))?\s+var\(--(?:font|mono)\)', value)
    if prop in ('filter', 'backdrop-filter'):
        return 'drop-shadow' in value
    if prop in ('clip-path', 'shape-outside'):
        return bool(re.search(r'\bround\b', value))
    family = FAMILY.get('radius' if prop.endswith('radius') else prop)
    return not (family and re.fullmatch(rf'var\((?:{family})\)', value))


def _literal(value):
    """A JS argument that is a written-out value rather than a name the code computed."""
    value = value.strip()
    if re.fullmatch(r'-?[\d.]+', value):
        return True
    return bool(re.match(r'["\'`]', value)) and not re.fullmatch(
        r'(["\'`])(?:var\(--[\w-]+\)|none|transparent|currentColor|inherit)\1', value)


def _named(value):
    value = re.sub(r'var\([^)]*\)|url\([^)]*\)', '', value)
    return sorted(set(re.findall(r'[a-z]+', value.lower())) & NAMED)


def _resolve_interpolation(js):
    """Replace each ${...} (braces balanced) with 1, so a built string reads as the value it will hold."""
    out, i = [], 0
    while (start := js.find('${', i)) >= 0:
        depth, j = 1, start + 2
        while j < len(js) and depth:
            depth += {'{': 1, '}': -1}.get(js[j], 0)
            j += 1
        out.append(js[i:start] + '1')
        i = j
    return ''.join(out) + js[i:]


def _violations(html=None):
    sheet, css, js, markup, inline = _parts(html)
    css, inline = css.lower(), inline.lower()  # CSS is case-insensitive: FONT-SIZE is font-size
    tokens = _tokens(html)
    found = []
    declared = css + ' ; ' + inline + ' ; ' + js
    layout = '|'.join(re.escape(v) for v in sorted(LAYOUT_VARS))
    for where, text in (('css', css + ' ; ' + inline), ('js', js)):
        for prop, value in PROPS.findall(text):
            if where == 'js' and ((prop == 'font' and not re.search(r'[\d#(]', value)) or value.startswith('$')):
                continue  # a JS key that shares a CSS name ("font: font"), or a size interpolated below
            if _bad_value(prop, value):
                found.append(f'{prop}: {value.strip()[:60]}')
    # Axes such as "wght" are quoted, which the declaration pattern stops at; any setting but normal is a weight.
    for value in re.findall(r'font-variation-settings\s*:\s*([^;{}]+)', declared):
        if value.strip() != 'normal':
            found.append(f'font-variation-settings: {value[:40]}')
    for where, text in (('css', css), ('inline', inline), ('js', js), ('markup', markup)):
        for hit in COLOUR.finditer(text):
            found.append(f'{where}: colour {text[hit.start():hit.start() + 24]!r}')
        for args in re.findall(r'color-mix\(([^;{}]*?)\)\s*[;}"\'`]', text):
            if re.sub(r'var\(--[\w-]+\)|\bin\s+(?:srgb|oklab)\b|[\d.]+%|transparent|currentcolor|[\s,]', '', args, flags=re.I):
                found.append(f'{where}: color-mix({args[:40]})')
    for prop, value in re.findall(rf'(?<![\w-])({COLOUR_PROPS})\s*:\s*([^;{{}}"\'`]+)', js):
        if _named(value):
            found.append(f'named colour {prop}: {value.strip()[:40]}')
    # In CSS every declaration is checked (gradients, @property initial-value, -webkit-text-*, scrollbar-color).
    bodies = ' ; '.join(re.findall(r'\{([^{}]*)\}', css)) + ' ; ' + inline
    for prop, value in re.findall(r'(?<![\w-])(-?[a-z][\w-]*)\s*:\s*([^;{}"\'`]+)', bodies):
        if prop not in NOT_PAINT and _named(value):
            found.append(f'named colour {prop}: {value.strip()[:40]}')
        if (re.fullmatch(COLOUR_PROPS, prop) or 'shadow' in prop) and re.search(rf'var\(\s*(?:{layout})\b', value):
            found.append(f'layout var painting {prop}: {value.strip()[:40]}')
    # Paint inside url(): a data: SVG cannot read var(), so only none/currentColor may appear there.
    for body in re.findall(r'url\(([^)]*)\)', (css + ' ; ' + inline + ' ; ' + js).lower()):
        for value in re.findall(r'(?:fill|stroke|stop-color|flood-color|color)\s*=\s*\\?[\'"]?([^\'"\s/>\\]+)', body):
            if value not in ('none', 'currentcolor', 'transparent'):
                found.append(f'url() paint {value[:20]}')
    # Legacy HTML and SVG presentation attributes size, round and shade without CSS.
    attributes = (markup + ' ; ' + js).lower()
    for hit in re.findall(r'<link\b[^>]*stylesheet|<font\b|\bbgcolor\s*=|fedropshadow|\b(?:font-size|font-weight|rx|ry)\s*=\s*\\?["\']?(?!0\b)[\w.$]', attributes):
        found.append(f'attribute {hit[:30]}')
    for prop, value in re.findall(r'["\']?\b(font-size|font-weight|rx|ry)["\']?\s*:\s*([^,}\n;]+)', js):
        value = value.strip().strip('"\'')
        if value != '0' and not value.startswith(('var(', '$')) and re.search(r'\d', value):
            found.append(f'js svg {prop}: {value[:30]}')
    # SVG paint written as an attribute, in markup or in a string the script builds.
    for prop, value in re.findall(r'\b(fill|stroke|stop-color|color)\s*=\s*\\?["\']([^"\'\\]*)', markup + js):
        if not re.fullmatch(r'var\(--[\w-]+\)|none|currentColor|transparent|url\(#[\w-]+\)|\$\{[^}]*\}|', value):
            found.append(f'attribute {prop}="{value[:30]}"')
    for prop, value in re.findall(r'\b(fill|stroke)\s*:\s*(["\'][^"\']*["\'])', js):
        if _literal(value):
            found.append(f'js {prop}: {value[:30]}')
    # Script APIs that paint without CSS.
    for prop, value in re.findall(rf'\.style\.({DESIGN_CAMEL}|{COLOUR_CAMEL})\s*=\s*([^;\n]+)', js):
        if re.fullmatch(DESIGN_CAMEL, prop) or _literal(value):
            found.append(f'js: style.{prop} = {value[:50]}')
    for prop, value in re.findall(r'\.style\[\s*["\'`]([\w-]+)["\'`]\s*\]\s*=\s*([^;\n]+)', js):
        if re.fullmatch(rf'{DESIGN_CAMEL}|font-size|font-weight|border-radius|box-shadow', prop) or _literal(value):
            found.append(f'js: style[{prop}] = {value[:50]}')
    for value in re.findall(r'\.style\.cssText\s*=\s*([^;\n]+)', js):
        found.append(f'js: style.cssText = {value[:50]}')  # a whole declaration list the lint cannot read
    for prop, value in re.findall(r'\.setAttribute\(\s*["\'`]([\w-]+)["\'`]\s*,\s*([^)]*)\)', js):
        if re.fullmatch(r'fill|stroke|color|stop-color|flood-color|font-size|font-weight|rx|ry|bgcolor', prop.lower()) and _literal(value):
            found.append(f'js: setAttribute({prop}, {value[:40]})')
    for name, value in re.findall(r'setProperty\(\s*["\'`]([\w-]+)["\'`]\s*,\s*([^)]*)\)', js):
        pieces = [m.group(1) for m in re.finditer(r'["\'`]([^"\'`]*)["\'`]', value) if value[:m.start()].rstrip()[-1:] != '(']
        if name not in LAYOUT_VARS or any(not LAYOUT_VALUE.fullmatch(p.strip()) for p in pieces):
            found.append(f'js: setProperty({name}, {value[:40]})')
    # Motion from the script: these bypass the sheet's --t-* exactly as a literal in CSS would.
    for prop, value in re.findall(r'\.style\.(transition\w*|animation\w*)\s*=\s*([^;\n]+)', js):
        found.append(f'js: style.{prop} = {value[:40]}')
    for options in re.findall(r'\.animate\(\s*\[[^\]]*\]\s*,\s*([^)]*)\)', js):
        if re.search(r'duration\s*:\s*[\d.]|easing\s*:|\d', options):
            found.append(f'js: animate({options[:40]})')
    for prop, value in re.findall(r'ctx\.(shadowBlur|shadowOffsetX|shadowOffsetY)\s*=\s*([^;\n]+)', js):
        if value.strip() != '0':
            found.append(f'js: ctx.{prop} = {value[:30]}')
    for prop, value in re.findall(r'\.(?:style|attr)\(\s*["\']([\w-]+)["\']\s*,\s*([^)]*)\)', js):
        if re.fullmatch(r'font-size|font-weight|fill|stroke|stop-color|color|background|rx|ry|filter', prop) and _literal(value):
            found.append(f'js: .style/.attr({prop}, {value[:40]})')
    for body in re.findall(r'Object\.assign\(\s*[\w.$]+\.style\s*,\s*\{([^}]*)\}', js):
        if re.search(rf'\b(?:{DESIGN_CAMEL}|{COLOUR_CAMEL})\s*:', body):
            found.append(f'js: Object.assign(style, {{{body[:40]}}})')
    for prop, value in re.findall(r'ctx\.(font|fillStyle|strokeStyle|shadowColor)\s*=\s*([^;\n]+)', js):
        if (prop == 'font' and re.search(r'\d', value)) or (prop != 'font' and _literal(value)):
            found.append(f'js: ctx.{prop} = {value[:50]}')
    # A style string that stops at the colon and concatenates the value: 'font-size:' + n + 'px'.
    for prop in re.findall(r'(font-size|font-weight|border-radius|box-shadow)\s*:\s*["\'`]\s*\+', js):
        found.append(f'js: concatenated {prop}')
    # A size the JS interpolates is still a size. The one allowed is the org chart's SVG labels,
    # which are in user units and derived from --s-meta (orgLabelPlan); any other is a new size.
    interpolated = re.findall(r'font-size:\s*\$\{(\w+)\}', js)
    if interpolated != ['fs'] or 'fs = v.phone ? meta * 21 / 12 : meta' not in js:
        found.append(f'js: interpolated font-size {interpolated}')
    # Motion: a written duration or easing ignores reduced motion; the sheet's --t-* do not.
    for prop, value in MOTION.findall(declared):
        # A layout var times a --t-* token stays zero under reduced motion; a layout var alone is a duration.
        value = re.sub(rf'calc\(\s*var\(\s*(?:{layout})\s*(?:,\s*[\d.]+\s*)?\)\s*\*\s*var\(--t-[\w-]+\)\s*\)', '', value)
        if re.search(rf'var\(\s*(?:{layout})\b', value):
            found.append(f'motion {prop} from a layout var: {value.strip()[:50]}')
        rest = re.sub(r'var\([^()]*(?:\([^()]*\)[^()]*)?\)', '', value)
        if re.search(r'(?<![\w.-])(?!0m?s\b)[\d.]+m?s\b|\bease(?:-in|-out|-in-out)?\b|\blinear\b|cubic-bezier|steps\(', rest):
            found.append(f'motion {prop}: {value.strip()[:50]}')
    # Custom properties: only the sheet defines design values; layout measures are listed by name.
    for name, value in re.findall(r'(?<![\w-])(--[\w-]+)\s*:\s*([^;}"\'`]*)', css + ' ; ' + inline + ' ; ' + _resolve_interpolation(js)):
        if name not in LAYOUT_VARS:
            found.append(f'{name} defined outside the sheet')
        elif not LAYOUT_VALUE.fullmatch(value.strip()):
            found.append(f'{name}: {value.strip()[:30]} is not a length or a number')
    return found


def test_the_reader_paints_only_from_the_token_sheet():
    found = _violations()
    assert not found, f'{len(found)} literals outside the Fuse sheet:\n' + '\n'.join(found[:80])


def test_the_sheet_has_five_sizes_two_weights_and_three_elevations():
    """N3 (D-123): 44 / 24 / 15 / 13 / 11, regular and semibold, e1 resting, e2 the one focus card, e3 menus and sheets."""
    blocks = _blocks(_parts()[0])
    light = blocks.get(('', ':root'), {})
    sizes = {n: light[n] for n in light if n.startswith('--s-')}
    assert sizes == {'--s-display': '44px', '--s-head': '24px', '--s-body': '15px', '--s-ui': '13px', '--s-meta': '11px'}
    assert {n: light[n] for n in light if n.startswith('--w-')} == {'--w-regular': '400', '--w-bold': '600'}
    assert {'--e1', '--e2', '--e3'} <= set(light) and not any('shadow' in n for n in light)
    assert {'--r-card', '--r-inner', '--r-pill', '--radius'} <= set(light)
    for name in ('--paper', '--raised', '--ink', '--grey', '--rule', '--well', '--green', '--on-green', '--red', '--pencil'):
        assert COLOUR.match(light[name]), name
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


def test_every_token_is_used_and_every_var_is_defined():
    """A token nothing reads is a decision nobody made; a var() nothing defines silently paints nothing."""
    sheet, css, js, markup, inline = _parts()
    used = set(re.findall(r'var\(\s*(--[\w-]+)', css + inline + js))
    used |= set(re.findall(r'["\'`](--[\w-]+)["\'`]', js))  # graphCss("--x") and the canvas's GRAPH_TONE
    tokens = _tokens()
    assert not tokens - used, f'tokens nothing uses: {sorted(tokens - used)}'
    assert not used - tokens - LAYOUT_VARS, f'var() with no definition: {sorted(used - tokens - LAYOUT_VARS)}'


PLANTS = {
    'custom property outside the sheet': ('</style>', '.zz{--mine:13px} .zz{font-size:calc(var(--mine))}</style>'),
    'named colour in a custom property': ('</style>', '.zz{--mine:red;color:var(--mine)}</style>'),
    'named colour': ('</style>', '.zz{color:red;background:white}</style>'),
    'color-mix of named colours': ('</style>', '.zz{background:color-mix(in srgb, tomato 20%, white)}</style>'),
    'oklch': ('</style>', '.zz{color:oklch(60% .2 30)}</style>'),
    'hwb': ('</style>', '.zz{color:hwb(10 10% 10%)}</style>'),
    'svg fill in markup': ('<main id="main"', '<svg fill="#ff0000" stroke="#00ff00"></svg><main id="main"'),
    'url-encoded hex': ('</style>', ".zz{background:url(\"data:image/svg+xml,%3Csvg fill='%23ff0000'/%3E\")}</style>"),
    'setProperty font-size': ('</script>', "el.style.setProperty('font-size','13px');</script>"),
    'd3 style and attr': ('</script>', "sel.style('font-size','13px').attr('fill','tomato');</script>"),
    'Object.assign style': ('</script>', "Object.assign(el.style,{fontSize:'13px',fontWeight:600});</script>"),
    'style.color named': ('</script>', "el.style.color='crimson';</script>"),
    'single-quoted style attribute': ('<main id="main"', "<div style='font-size:13px;font-weight:600'></div><main id=\"main\""),
    'em font-size': ('</style>', '.zz{font-size:1.2em}</style>'),
    'font shorthand with keywords': ('</style>', '.zz{font:bold 1.2rem system-ui}</style>'),
    'font keyword size': ('</style>', '.zz{font-size:larger}</style>'),
    'font: caption': ('</style>', '.zz{font:caption}</style>'),
    'font-variation weight': ('</style>', '.zz{font-variation-settings:"wght" 600}</style>'),
    'logical radius': ('</style>', '.zz{border-start-start-radius:6px}</style>'),
    'side radius': ('</style>', '.zz{border-top-radius:6px}</style>'),
    'outline named colour': ('</style>', '.zz{outline:2px solid blue}</style>'),
    'filter drop-shadow': ('</style>', '.zz{filter:drop-shadow(0 2px 4px var(--ink))}</style>'),
    'text-shadow': ('</style>', '.zz{text-shadow:0 1px 2px var(--ink)}</style>'),
    'box-shadow': ('</style>', '.zz{box-shadow:0 1px 2px var(--ink)}</style>'),
    'clip-path round': ('</style>', '.zz{clip-path:inset(0 round 8px)}</style>'),
    'template literal size': ('</script>', "x.innerHTML=`<b style=\"font-size:${sz}px\">`;</script>"),
    'innerHTML fill attribute': ('</script>', "x.innerHTML='<circle fill=\"tomato\"/>';</script>"),
    'attr font-weight': ('</script>', "g.attr('font-weight', 600);</script>"),
    'hex after a line comment': ('</script>', "const u='a'; // x\nconst c='#f00';</script>"),
    'token redefined in another style': ('</style>', '@media (max-width:600px){:root{--s-body:15px}}</style>'),
    'upper-case STYLE element': ('<main id="main"', '<STYLE>.zz{color:red}</STYLE ><main id="main"'),
    'upper-case SCRIPT element': ('<main id="main"', "<SCRIPT>el.style.color='crimson';</SCRIPT><main id=\"main\""),
    'token set from JS': ('</script>', "document.documentElement.style.setProperty('--s-body','13px');</script>"),
    'canvas fillStyle': ('</script>', "ctx.fillStyle = 'tomato';</script>"),
    'literal transition': ('</style>', '.zz{transition:opacity 120ms ease-out}</style>'),
    'literal animation': ('</style>', '.zz{animation:spin 1s linear infinite}</style>'),
    'animation-delay literal': ('</style>', '.zz{animation-delay:300ms}</style>'),
    'transition-delay literal': ('</style>', '.zz{transition-delay:400ms}</style>'),
    'style.transition': ('</script>', "el.style.transition='opacity 300ms ease';</script>"),
    'Web Animations duration': ('</script>', "el.animate([{opacity:0},{opacity:1}],{duration:400});</script>"),
    'layout var as a duration': ('</style>', '.zz{--d:900ms;transition:opacity var(--d)}</style>'),
    'layout var colour from JS': ('</script>', "el.style.setProperty('--d','tomato');</script>"),
    'layout var as a border colour or width': ('</style>', '.zz{--name:9px;border:var(--name) solid var(--ink)}</style>'),
    'named colour in a data url': ('</style>', ".zz{background:url(\"data:image/svg+xml,<svg><rect fill='tomato'/></svg>\")}</style>"),
    'named colour unquoted in a data url': ('</style>', '.zz{background-image:url(data:image/svg+xml;utf8,<svg><rect fill=red /></svg>)}</style>'),
    '@property initial-value': ('</style>', '@property --zz{syntax:"<color>";inherits:false;initial-value:tomato}</style>'),
    'named colours in a gradient': ('</style>', '.zz{background-image:linear-gradient(tomato, gold)}</style>'),
    '-webkit-text-fill-color': ('</style>', '.zz{-webkit-text-fill-color:tomato}</style>'),
    '-webkit-text-stroke': ('</style>', '.zz{-webkit-text-stroke:1px tomato}</style>'),
    'scrollbar-color': ('</style>', '.zz{scrollbar-color:tomato gold}</style>'),
    'setAttribute fill': ('</script>', "el.setAttribute('fill','tomato');</script>"),
    'svg font-size attribute': ('<main id="main"', '<svg><text font-size="30" font-weight="900">x</text></svg><main id="main"'),
    'svg rx attribute': ('<main id="main"', '<svg><rect rx="8"/></svg><main id="main"'),
    'svgEl font-size and rx': ('</script>', "svgEl('text',{'font-size':30}); svgEl('rect',{rx:8});</script>"),
    'feDropShadow': ('<main id="main"', '<svg><filter id="f"><feDropShadow dx="1" stdDeviation="2"/></filter></svg><main id="main"'),
    'upper-case property': ('</style>', '.zz{FONT-SIZE:30px;COLOR:TOMATO}</style>'),
    'upper-case STYLE attribute': ('<main id="main"', '<div STYLE="font-size:30px"></div><main id="main"'),
    'unquoted style attribute': ('<main id="main"', '<div style=font-size:30px></div><main id="main"'),
    '<font size>': ('<main id="main"', '<font size="7">x</font><main id="main"'),
    'bgcolor': ('<main id="main"', '<table bgcolor="red"></table><main id="main"'),
    "style['fontSize']": ('</script>', "el.style['fontSize']='30px';</script>"),
    'style.cssText': ('</script>', "el.style.cssText='font-size:'+n+'px';</script>"),
    'canvas shadowBlur': ('</script>', 'ctx.shadowBlur = 8;</script>'),
    'shape-outside round': ('</style>', '.zz{shape-outside:inset(0 round 8px)}</style>'),
    '<link> stylesheet': ('<main id="main"', '<link rel="stylesheet" href="data:text/css,.zz{font-size:30px}"><main id="main"'),
    'concatenated size in a style string': ('</script>', "el('b',{style:'font-size:'+n+'px'});</script>"),
}


def test_the_lint_catches_what_it_guards():
    """A lint that under-reads passes everything; prove each rule fires on a planted literal."""
    html = _html()
    base = len(_violations(html))
    missed = [name for name, (anchor, planted) in PLANTS.items()
              if anchor not in html or len(_violations(html.replace(anchor, planted, 1))) <= base]
    assert not missed, missed
    assert not _bad_value('font-size', 'var(--s-meta) !important') and not _bad_value('border-radius', '0')
    assert not _bad_value('font', 'var(--w-bold) var(--s-meta)/1.4 var(--font)')
    assert _strip_js_comments('a = "https://x"; // see #2008') == 'a = "https://x"; '
