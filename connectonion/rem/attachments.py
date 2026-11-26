"""What an attachment says, as text the investigate turn can read.

PDFs, documents and spreadsheets provide text for investigation. The reader also
keeps native previews and download links when a file has no extractable text.
"""

import re
import shlex
import sys
import tomllib
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from .files import state_path

READABLE = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".html", ".htm", ".ics"}


def spreadsheet_install_command() -> str:
    """Install the optional spreadsheet reader into the running co environment."""
    from .._version import __version__

    package = f"'connectonion[rem]=={__version__}'"
    prefix = Path(sys.prefix)
    receipt = prefix / "uv-receipt.toml"
    if prefix.parent.parts[-2:] == ("uv", "tools") or receipt.is_file():
        command = f"uv tool install --force {package}"
        if receipt.is_file():
            tool = tomllib.loads(receipt.read_text(encoding="utf-8"))["tool"]
            for requirement in tool.get("requirements", []):
                if requirement["name"] != "connectonion":
                    command += " --with " + shlex.quote(requirement["name"] + requirement.get("specifier", ""))
            if "python" in tool:
                command += " --python " + shlex.quote(tool["python"])
        return command
    return f"{shlex.quote(str(Path(sys.executable).absolute()))} -m pip install {package}"


def attachment_path(root: Path, source: str) -> Path | None:
    """Resolve one retained mail attachment without following links outside its store."""
    match = re.fullmatch(r"(gmail|outlook):([0-9a-f]{12}):([^/\\\r\n]+)", source)
    if not match:
        return None
    provider, message, filename = match.groups()
    relative = Path(f".state/attachments/{provider}/{message}/{filename}")
    if (filename.startswith(".") or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in filename)
            or any((root / parent).is_symlink() for parent in (relative, *relative.parents))):
        return None
    path = state_path(root, f"attachments/{provider}/{message}/{filename}")
    if (path.is_symlink() or not path.is_file()
            or not path.resolve().is_relative_to(state_path(root, "attachments").resolve())):
        return None
    return path


def attachment_type(path: Path) -> tuple[str, str]:
    """An explicit inline allowlist; every other file is a download."""
    suffix = path.suffix.lower()
    images = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".gif": "image/gif", ".webp": "image/webp"}
    if suffix == ".pdf":
        return "application/pdf", "pdf"
    if suffix in images:
        return images[suffix], "image"
    mime = "text/plain; charset=utf-8" if suffix in (".txt", ".md", ".csv", ".ics") else "application/octet-stream"
    kind = "table" if suffix in (".xlsx", ".csv") else "text" if suffix in READABLE | {".pptx"} else "download"
    return mime, kind


def attachment_context(root: Path, source: str) -> dict | None:
    path = attachment_path(root, source)
    if path is None:
        return None
    stat = path.stat()
    mime, kind = attachment_type(path)
    text = _preview(path, stat.st_mtime_ns, stat.st_size) if kind not in ("image", "download") else ""
    url = f"/rem/attachment?id={quote(source, safe='')}"
    return {"source": "attachment", "excerpt": text[:8_000], "truncated": len(text) > 8_000,
            "filename": path.name, "url": url, "file": url, "mime_type": mime,
            "preview_kind": kind, "size": stat.st_size,
            "body_format": "Local attachment text extraction; images and signature appearances are not verified.",
            "input_scope": "Current local attachment. Original capture time and the version read by the writer are unknown."}


@lru_cache(maxsize=512)
def _preview(path: Path, mtime_ns: int, size: int) -> str:
    """Keep one extra character to distinguish a complete excerpt from a truncated one."""
    return extract_structured_text(path, limit=8_001)


def _pdf_page_text(page, number: int) -> str:
    annotations = []
    for reference in page.get("/Annots", []):
        annotation = reference.get_object()
        if annotation.get("/Subtype") == "/FreeText" and annotation.get("/Contents"):
            annotations.append(f"[annotation text: {annotation['/Contents']}]")
        elif annotation.get("/Subtype") == "/Stamp":
            annotations.append("[stamp present; appearance not read; signature not verified]")
    body = page.extract_text() or ""
    if not annotations:
        return body
    return f"PDF page {number}\n" + "\n".join(annotations + [body])


def _read_text(path: Path, *, preview_limit: int | None = None) -> str:
    """Read attachment text; a PDF preview stops once its excerpt is long enough."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        try:
            parts = []
            for number, page in enumerate(PdfReader(str(path)).pages, 1):
                parts.append(_pdf_page_text(page, number))
                if preview_limit is not None and len(" ".join("\n".join(parts).split())) > preview_limit:
                    break
            text = "\n".join(parts)
        except Exception as error:  # noqa: BLE001 -- a broken PDF is a finding, not a crash
            return f"[could not read PDF: {type(error).__name__}]"
    elif suffix == ".docx":
        from docx import Document
        try:
            document = Document(str(path))
            text = "\n".join(p.text for p in document.paragraphs)
            for table in document.tables:
                for row in table.rows:
                    text += "\n" + " | ".join(cell.text for cell in row.cells)
        except Exception as error:  # noqa: BLE001
            return f"[could not read document: {type(error).__name__}]"
    elif suffix == ".pptx":
        from pptx import Presentation
        try:
            chunks = []
            for number, slide in enumerate(Presentation(str(path)).slides, 1):
                chunks.append(f"Slide {number}")
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        chunks.append(shape.text)
                    if shape.has_table:
                        chunks.extend(" | ".join(cell.text for cell in row.cells) for row in shape.table.rows)
                if slide.has_notes_slide:
                    chunks.append(slide.notes_slide.notes_text_frame.text)
            text = "\n".join(chunks)
        except Exception as error:
            return f"[could not read presentation: {type(error).__name__}]"
    elif suffix == ".xlsx":
        try:
            from openpyxl import load_workbook
        except ImportError:
            # An optional extra (see pyproject.toml). One unreadable attachment is a
            # finding the page can carry, not a reason to stop the investigation.
            return ("[XLSX not read: spreadsheet support is optional; "
                    f"run {spreadsheet_install_command()}, then investigate again]")
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                chunks = []
                for sheet in workbook:
                    chunks.append(f"Sheet: {sheet.title}")
                    chunks.extend(" | ".join("" if cell is None else str(cell) for cell in row)
                                  for row in sheet.iter_rows(values_only=True))
                text = "\n".join(chunks)
            finally:
                workbook.close()
        except Exception as error:
            return f"[could not read spreadsheet: {type(error).__name__}]"
    elif suffix in READABLE:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            return f"[could not read file: {type(error).__name__}]"
        if suffix in (".html", ".htm"):
            import re
            text = re.sub(r"<[^>]+>", " ", text)
    else:
        return f"[{path.name}: {suffix or 'no extension'} is not read; open it by hand if it matters]"
    return text


def extract_structured_text(path: Path, limit: int = 8_000) -> str:
    """Preserve paragraph breaks and table rows in the reader's attachment excerpt."""
    text = _read_text(Path(path), preview_limit=limit)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()[:limit]


def extract_text(path: Path, limit: int | None = 20_000, *, preview_limit: int | None = None) -> str:
    """The investigation's compact text, with its existing truncation notice."""
    text = " ".join(_read_text(path, preview_limit=preview_limit).split())
    if limit is not None and len(text) > limit:
        text = text[:limit] + f" …[{len(text) - limit} more characters not shown]"
    return text
