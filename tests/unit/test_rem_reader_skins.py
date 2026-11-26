"""Regression contract for the Cold Porcelain, Obsidian, Lucid Viridian & Rose-Pink design system
and pluggable [data-skin] architecture (#3470)."""

import re

from connectonion.rem.reader import TEMPLATE


ORIGINAL_BRAND_MARK = (
    '<svg class="mark" viewBox="0 0 34 34" aria-hidden="true">'
    '<path class="f" d="M10.5 1h13a9.5 9.5 0 0 1 9.5 9.5v13a9.5 9.5 0 0 1-9.5 9.5h-13A9.5 9.5 0 0 1 1 23.5v-13A9.5 9.5 0 0 1 10.5 1z"/>'
    '<path class="sp" stroke-width="2.6" transform="translate(0 .6)" d="M6.16 15.25A4.8 4.8 0 0 0 14.64 15.25M19.36 15.25A4.8 4.8 0 0 0 27.84 15.25"/>'
    '</svg>'
)


def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(hex_a: str, hex_b: str) -> float:
    low, high = sorted((_luminance(hex_a), _luminance(hex_b)))
    return (high + 0.05) / (low + 0.05)


def test_brand_logo_svg_remains_exact_and_unchanged():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert ORIGINAL_BRAND_MARK in html


def test_default_porcelain_viridian_palette_enforces_cold_porcelain_and_anti_muddy_rules():
    html = TEMPLATE.read_text(encoding="utf-8")
    sheet = html.split("/* fuse:tokens */", 1)[1].split("/* /fuse:tokens */", 1)[0]
    root_match = re.search(r":root \{(.*?)\n  \}", sheet, re.S)
    assert root_match is not None
    root = root_match.group(1)
    colors = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6});", root))

    # 1. Cold Porcelain B >= R law (zero warm cream or yellow tint on canvas/well/rule)
    for surface in ("--canvas", "--paper", "--well", "--rule"):
        assert surface in colors, f"Missing {surface}"
        h = colors[surface]
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        assert b >= r and g >= r, f"{surface}={h} violates Cold Porcelain B>=G>=R rule"

    # 2. Pure unmuddied Obsidian night slab + Lucid Viridian signal + Rose-Pink quiet lever
    for required in ("--night", "--night-ink", "--night-sub", "--night-rule", "--viridian", "--viridian-bright", "--viridian-wash", "--rose-bright"):
        assert required in colors, f"Missing semantic token {required}"

    # Anti-muddy ban: dark surfaces (--night, dark --paper/--raised/--well) must never mix purple/red dominance (R > G and B > G)
    night = colors["--night"]
    nr, ng, nb = int(night[1:3], 16), int(night[3:5], 16), int(night[5:7], 16)
    assert not (nr > ng and nb > ng), f"--night={night} mixes purple/plum into dark surface"

    # WCAG AA contrast on Obsidian night card
    assert _contrast(colors["--night"], colors["--night-ink"]) >= 12.0
    assert _contrast(colors["--night"], colors["--night-sub"]) >= 4.5
    assert _contrast(colors["--night"], colors["--viridian-bright"]) >= 7.0
    assert _contrast(colors["--night"], colors["--rose-bright"]) >= 4.5


def test_pluggable_skins_and_settings_skin_switcher_are_wired():
    html = TEMPLATE.read_text(encoding="utf-8")
    sheet = html.split("/* fuse:tokens */", 1)[1].split("/* /fuse:tokens */", 1)[0]
    for skin in ("klein", "onion", "classic"):
        assert f':root[data-skin="{skin}"]' in sheet, f"Missing built-in skin {skin}"
    assert 'function setSkin(' in html
    assert 'readerStorage("co-rem-skin"' in html
    assert 'class: "skin-switch' in html


def test_night_card_renders_on_obsidian_with_viridian_curve_and_rose_dawn():
    html = TEMPLATE.read_text(encoding="utf-8")
    css = html.split("/* /fuse:tokens */", 1)[1].split("</head>", 1)[0]
    night_card = re.search(r"\.night-card\s*\{([^}]+)\}", css)
    assert night_card and "background: var(--night)" in night_card.group(1)
    rem_stroke = re.search(r"\.hypno \.rem\s*\{([^}]+)\}", css)
    assert rem_stroke and "stroke: var(--viridian-bright)" in rem_stroke.group(1)
    dawn = re.search(r"\.night-card \.hypno \.dawn\s*\{([^}]+)\}", css)
    assert dawn and "background: var(--rose-bright)" in dawn.group(1)
