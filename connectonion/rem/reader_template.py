"""Zero-build modular source assembler for the REM Reader (`connectonion/rem/reader_ui/`).

Domain-cohesive HTML, CSS, and JS source files live under `reader_ui/` for
clear authorship and isolated testing, then assemble deterministically in
memory (<2ms, mtime-cached) into a single self-contained HTML document for
both `/rem` live views and offline `file://` snapshots.
"""

from __future__ import annotations

import os
from pathlib import Path

STYLE_PLACEHOLDER = "/*__READER_STYLES__*/"
SCRIPT_PLACEHOLDER = "/*__READER_SCRIPTS__*/"

STYLE_PARTS: tuple[str, ...] = (
    "styles/tokens.css",
    "styles/shell_and_reading.css",
    "styles/today_and_overview.css",
    "styles/organisations.css",
    "styles/knowledge_graph.css",
    "styles/desk_and_open.css",
)

SCRIPT_PARTS: tuple[str, ...] = (
    "scripts/i18n_and_boot.js",
    "scripts/privacy_and_theme.js",
    "scripts/markdown_and_tags.js",
    "scripts/page_facts_and_threads.js",
    "scripts/rail_and_settings.js",
    "scripts/today_cards.js",
    "scripts/waiting_and_desk.js",
    "scripts/people_and_keys.js",
    "scripts/agenda_and_projects.js",
    "scripts/orgs_skills_sessions.js",
    "scripts/record_and_search.js",
    "scripts/knowledge_graph.js",
    "scripts/router_evidence_palette.js",
)

_CACHE: dict[Path, tuple[tuple[tuple[int, int], ...], str]] = {}


def ui_parts(ui_dir: Path | None = None) -> tuple[Path, ...]:
    base = (ui_dir or Path(__file__).with_name("reader_ui")).resolve()
    return (
        base / "shell.html",
        *(base / rel for rel in STYLE_PARTS),
        *(base / rel for rel in SCRIPT_PARTS),
    )


def read_part(relative_path: str, ui_dir: Path | None = None) -> str:
    """Read one domain CSS/JS/HTML source module directly (e.g. for isolated unit tests)."""
    base = (ui_dir or Path(__file__).with_name("reader_ui")).resolve()
    return (base / relative_path).read_text(encoding="utf-8")


def assemble_template(ui_dir: Path | None = None) -> str:
    """Assemble `reader_ui/` parts into one self-contained HTML template, cached by `(mtime_ns, size)`."""
    base = (ui_dir or Path(__file__).with_name("reader_ui")).resolve()
    parts = ui_parts(base)
    stamp = tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in parts)
    cached = _CACHE.get(base)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    shell = (base / "shell.html").read_text(encoding="utf-8")
    if STYLE_PLACEHOLDER not in shell or SCRIPT_PLACEHOLDER not in shell:
        raise RuntimeError("reader_ui/shell.html is missing style or script slot placeholders")

    css = "\n".join((base / rel).read_text(encoding="utf-8").removesuffix("\n") for rel in STYLE_PARTS)
    js = "\n".join((base / rel).read_text(encoding="utf-8").removesuffix("\n") for rel in SCRIPT_PARTS)
    html = shell.replace(STYLE_PLACEHOLDER, css, 1).replace(SCRIPT_PLACEHOLDER, js, 1)
    _CACHE[base] = (stamp, html)
    return html


class _CompositeStat:
    """`os.stat_result`-compatible view aggregating `max(st_mtime_ns)` and `sum(st_size)` across `reader_ui/`."""

    __slots__ = ("_base", "st_mtime_ns", "st_mtime", "st_size")

    def __init__(self, base: os.stat_result, max_mtime_ns: int, total_size: int) -> None:
        self._base = base
        self.st_mtime_ns = max_mtime_ns
        self.st_mtime = max_mtime_ns / 1_000_000_000
        self.st_size = total_size

    def __getattr__(self, name: str):
        return getattr(self._base, name)


class ReaderTemplatePath(type(Path())):
    """Virtual `Path` at `connectonion/rem/reader.html` backed by `connectonion/rem/reader_ui/`."""

    def _ui_dir(self) -> Path:
        raw = Path(os.fspath(self))
        return raw.with_name("reader_ui") if raw.name == "reader.html" else Path("")

    def exists(self, *, follow_symlinks: bool = True) -> bool:  # type: ignore[override]
        ui = self._ui_dir()
        return (ui / "shell.html").is_file() or super().exists()

    def is_file(self, *, follow_symlinks: bool = True) -> bool:  # type: ignore[override]
        ui = self._ui_dir()
        return (ui / "shell.html").is_file() or super().is_file()

    def read_text(
        self,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        ui = self._ui_dir()
        if (ui / "shell.html").is_file():
            return assemble_template(ui)
        extra = {"newline": newline} if newline is not None else {}
        return super().read_text(encoding=encoding or "utf-8", errors=errors, **extra)

    def read_bytes(self) -> bytes:
        return self.read_text(encoding="utf-8").encode("utf-8")

    def stat(self, *, follow_symlinks: bool = True):  # type: ignore[override]
        ui = self._ui_dir()
        if (ui / "shell.html").is_file():
            parts = ui_parts(ui)
            stats = [p.stat() for p in parts]
            return _CompositeStat(
                stats[0],
                max(s.st_mtime_ns for s in stats),
                sum(s.st_size for s in stats),
            )
        return super().stat(follow_symlinks=follow_symlinks)
