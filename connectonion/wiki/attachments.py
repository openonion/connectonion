"""What an attachment says, as text the investigate turn can read.

The terms of a relationship are in the contract, not the mail that carried
it; a real investigation of Emma reported "no attachment bodies are included,
so terms should be rechecked against the actual files". This reads the files.
PDF through pypdf, Word through python-docx, plain text as it is; anything else
is named but not read, which is a finding the page can carry.
"""

from pathlib import Path

READABLE = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".html", ".htm", ".ics"}


def extract_text(path: Path, limit: int | None = 20_000) -> str:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        try:
            pages = PdfReader(str(path)).pages
            text = "\n".join((page.extract_text() or "") for page in pages)
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
            return "[XLSX not read: install openpyxl, then investigate again]"
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
