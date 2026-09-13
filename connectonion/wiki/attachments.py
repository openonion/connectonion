"""What an attachment says, as text the investigate turn can read.

The terms of a relationship are in the contract, not the mail that carried
it; a real investigation of Emma reported "no attachment bodies are included,
so terms should be rechecked against the actual files". This reads the files.
PDF through pypdf, Word through python-docx, plain text as it is; anything else
is named but not read, which is a finding the page can carry.
"""

from pathlib import Path

READABLE = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".html", ".htm"}


def extract_text(path: Path, limit: int = 20_000) -> str:
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
    if len(text) > limit:
        text = text[:limit] + f" …[{len(text) - limit} more characters not shown]"
    return text
