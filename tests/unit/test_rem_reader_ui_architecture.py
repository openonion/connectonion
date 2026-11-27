"""Architecture and boundary invariants for the modular REM Reader (`connectonion/rem/reader_ui/`).

Source files live in domain-cohesive `.html`, `.css`, and `.js` modules under
`connectonion/rem/reader_ui/` and assemble in memory via `reader_template.py`
into a single-file HTML document for both `/rem` live views and offline
`file://` snapshots — with zero Node/bundler build step.
"""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

import pytest

from connectonion.rem import reader as rem_reader

REPO_ROOT = Path(__file__).resolve().parents[2]
REM_DIR = REPO_ROOT / "connectonion" / "rem"
UI_DIR = REM_DIR / "reader_ui"
FORBIDDEN_STEMS = {"utils", "util", "helpers", "helper", "common", "misc", "shared"}
MAX_PART_LINES = 2200


def test_monolith_is_gone_and_reader_ui_manifest_is_exact():
    from connectonion.rem import reader_template

    assert not (REM_DIR / "reader.html").exists(), (
        "connectonion/rem/reader.html must not exist alongside reader_ui/; "
        "keep one authoritative source tree"
    )
    assert (UI_DIR / "shell.html").is_file()

    listed_styles = [UI_DIR / rel for rel in reader_template.STYLE_PARTS]
    actual_styles = sorted((UI_DIR / "styles").glob("*.css"))
    assert sorted(listed_styles) == actual_styles, "every styles/*.css file must be in STYLE_PARTS"

    listed_scripts = [UI_DIR / rel for rel in reader_template.SCRIPT_PARTS]
    actual_scripts = sorted((UI_DIR / "scripts").glob("*.js"))
    assert sorted(listed_scripts) == actual_scripts, "every scripts/*.js file must be in SCRIPT_PARTS"


def test_domain_cohesive_names_and_bounded_module_sizes():
    from connectonion.rem import reader_template

    all_parts = [UI_DIR / "shell.html", *(UI_DIR / p for p in reader_template.STYLE_PARTS + reader_template.SCRIPT_PARTS)]
    for path in all_parts:
        tokens = set(re.split(r"[_\-.]", path.stem.lower()))
        assert not (tokens & FORBIDDEN_STEMS), f"non-domain catch-all filename forbidden: {path.name}"
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        assert 10 <= line_count <= MAX_PART_LINES, (
            f"{path.relative_to(REPO_ROOT)} has {line_count} lines (ceiling {MAX_PART_LINES})"
        )


def test_every_script_and_style_part_is_syntactically_self_contained():
    from connectonion.rem import reader_template

    for idx, rel in enumerate(reader_template.STYLE_PARTS):
        css = (UI_DIR / rel).read_text(encoding="utf-8")
        if idx == 0:
            assert "/* fuse:tokens */" in css and "/* /fuse:tokens */" in css
        else:
            assert "/* fuse:tokens */" not in css, f"token sheet belongs only in styles/tokens.css, found in {rel}"
        assert css.count("/*") == css.count("*/"), f"unclosed CSS block comment in {rel}"
        stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        stripped = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', stripped)
        assert stripped.count("{") == stripped.count("}"), f"unbalanced CSS braces in {rel}"

    for rel in reader_template.SCRIPT_PARTS:
        js = (UI_DIR / rel).read_text(encoding="utf-8").replace("/*__REM_DATA__*/null", "null")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as handle:
            handle.write(js)
            tmp_js = Path(handle.name)
        try:
            proc = subprocess.run(["node", "--check", str(tmp_js)], capture_output=True, text=True)
            assert proc.returncode == 0, f"JS syntax error in {rel}:\n{proc.stderr}"
        finally:
            tmp_js.unlink(missing_ok=True)


def test_template_path_compat_and_mtime_invalidation(tmp_path):
    from connectonion.rem.reader_template import ReaderTemplatePath

    assert isinstance(rem_reader.TEMPLATE, Path)
    assert rem_reader.TEMPLATE.name == "reader.html"
    assert rem_reader.TEMPLATE.parent == REM_DIR
    assert rem_reader.TEMPLATE.parents[2] == REPO_ROOT

    assembled = rem_reader.TEMPLATE.read_text(encoding="utf-8")
    assert "/*__REM_DATA__*/null" in assembled
    assert "/*__D3__*/" in assembled
    assert "/*__REM_DETAIL__*/" in assembled
    assert assembled.count("<style>") == 1 and assembled.count("</style>") == 1

    # Verify mtime and content cache update immediately when any part changes on disk
    sandbox_rem = tmp_path / "rem"
    shutil.copytree(UI_DIR, sandbox_rem / "reader_ui")
    tpl = ReaderTemplatePath(sandbox_rem / "reader.html")
    before_text = tpl.read_text(encoding="utf-8")
    before_stat = tpl.stat()

    target = sandbox_rem / "reader_ui" / "scripts" / "router_evidence_palette.js"
    time.sleep(0.01)
    target.write_text(target.read_text(encoding="utf-8") + "\n// cache-invalidation-sentinel\n", encoding="utf-8")

    after_stat = tpl.stat()
    after_text = tpl.read_text(encoding="utf-8")
    assert after_stat.st_mtime_ns > before_stat.st_mtime_ns
    assert "// cache-invalidation-sentinel" in after_text
    assert "// cache-invalidation-sentinel" not in before_text


def test_pure_domain_module_runs_directly_in_node_without_regex_slicing():
    from connectonion.rem.reader_template import read_part

    markdown_js = read_part("scripts/markdown_and_tags.js")
    harness = (
        "const REM = { owner: 'people/owner.md', tags: {} }, UI = { zh: {} };\n"
        "let uiLanguage = 'en', privacyLevel = 'cover';\n"
        "const t = s => s;\n"
        + markdown_js
        + "\nconsole.log(JSON.stringify(plainLine('## Review PR #58 and issue #1886 [1]')));\n"
    )
    proc = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == '"Review PR #58 and issue #1886"'


def test_pyproject_packages_css_html_and_js_assets():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for pattern in ('"connectonion/**/*.css"', '"connectonion/**/*.html"', '"connectonion/**/*.js"'):
        assert pattern in pyproject, f"missing {pattern} in pyproject.toml [tool.hatch.build] include"
