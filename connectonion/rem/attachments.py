"""What an attachment says, as text the investigate turn can read.

The terms of a relationship are in the contract, not the mail that carried
it; a real investigation of Emma reported "no attachment bodies are included,
so terms should be rechecked against the actual files". This reads the files.
PDF through pypdf, Word through python-docx, plain text as it is; anything else
is named but not read, which is a finding the page can carry.
"""

import re
from pathlib import Path

from .files import state_path

READABLE = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".html", ".htm", ".ics"}


def attachment_context(root: Path, source: str) -> dict | None:
    match = re.fullmatch(r"(gmail|outlook):([0-9a-f]{12}):([^/\\]+)", source)
    if not match:
        return None
    provider, message, filename = match.groups()
    path = state_path(root, f"attachments/{provider}/{message}/{filename}")
    if not path.is_file():
        return None
    text = extract_text(path, limit=None, preview_limit=640)
    if not text:
        return None
    return {"source": "attachment", "excerpt": text[:640], "truncated": len(text) > 640,
            "filename": filename, "file": path.as_uri(),
            "body_format": "Local attachment text extraction; images and signature appearances are not verified.",
            "input_scope": "Current local attachment. Original capture time and the version read by the writer are unknown."}


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


def extract_text(path: Path, limit: int | None = 20_000, *, preview_limit: int | None = None) -> str:
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
                    "run pip install 'connectonion[rem]', then investigate again]")
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
    text = " ".join(text.split())
    if limit is not None and len(text) > limit:
        text = text[:limit] + f" …[{len(text) - limit} more characters not shown]"
    return text
