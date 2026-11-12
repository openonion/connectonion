"""The terms are in the contract, not the mail that carried it."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import shlex
import sys

import pytest

from connectonion.rem.attachments import extract_text, spreadsheet_install_command


def test_a_pdf_is_read_as_text(tmp_path):
    from pypdf import PdfWriter
    pdf = tmp_path / "terms.pdf"
    writer = PdfWriter(); writer.add_blank_page(width=200, height=200); writer.write(str(pdf))
    assert isinstance(extract_text(pdf), str)      # empty page reads as empty, not a crash


def test_a_word_document_is_read_including_its_tables(tmp_path):
    from docx import Document
    doc = Document(); doc.add_paragraph("Fee: 7.5% of Net Booking Revenue")
    table = doc.add_table(rows=1, cols=2); table.rows[0].cells[0].text = "Term"; table.rows[0].cells[1].text = "90 days"
    path = tmp_path / "agreement.docx"; doc.save(str(path))
    text = extract_text(path)
    assert "7.5% of Net Booking Revenue" in text and "Term | 90 days" in text


def test_plain_text_and_html_are_read_and_markup_is_dropped(tmp_path):
    (tmp_path / "a.txt").write_text("hello   world\n", encoding="utf-8")
    (tmp_path / "b.html").write_text("<p>Signed <b>2026-08-07</b></p>", encoding="utf-8")
    assert extract_text(tmp_path / "a.txt") == "hello world"
    assert extract_text(tmp_path / "b.html") == "Signed 2026-08-07"


def test_an_unreadable_type_is_named_not_pretended(tmp_path):
    path = tmp_path / "photo.heic"; path.write_bytes(b"\x00\x01")
    text = extract_text(path)
    assert "photo.heic" in text and "not read" in text


def test_long_text_is_capped_and_says_so(tmp_path):
    (tmp_path / "big.txt").write_text("x " * 30_000, encoding="utf-8")
    text = extract_text(tmp_path / "big.txt", limit=100)
    assert len(text) < 200 and "more characters not shown" in text


def test_investigation_can_read_full_attachment_for_chunking(tmp_path):
    path = tmp_path / "long.txt"
    path.write_text("a " * 30000 + "important final clause")
    text = extract_text(path, limit=None)
    assert text.endswith("important final clause") and "not shown" not in text


def test_spreadsheet_reads_all_sheets_and_cells(tmp_path):
    from openpyxl import Workbook
    book = Workbook()
    book.active.title = "Contacts"
    book.active.append(["Alice", "+61 2 5550 0100"])
    book.create_sheet("Terms").append(["Fee", 0.08])
    path = tmp_path / "terms.xlsx"
    book.save(path)
    text = extract_text(path)
    assert "Contacts" in text and "+61 2 5550 0100" in text
    assert "Terms" in text and "0.08" in text


def test_presentation_reads_text_tables_and_speaker_notes(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Aurora partnership"
    slide.notes_slide.notes_text_frame.text = "Alice is the lead."
    table = slide.shapes.add_table(1, 2, Inches(1), Inches(1), Inches(4), Inches(1)).table
    table.cell(0, 0).text = "Review"
    table.cell(0, 1).text = "90 days"
    path = tmp_path / "brief.pptx"
    deck.save(path)
    text = extract_text(path)
    assert "Aurora partnership" in text and "Alice is the lead" in text and "Review | 90 days" in text


def test_calendar_attachment_keeps_dates_and_organizer(tmp_path):
    path = tmp_path / "event.ics"
    path.write_text("BEGIN:VEVENT\nDTSTART:20260915T100000Z\nORGANIZER:mailto:alice@example.org\nEND:VEVENT")
    text = extract_text(path)
    assert "20260915T100000Z" in text and "alice@example.org" in text


def test_gather_lists_files_without_creating_attachment_store(tmp_path):
    from connectonion.rem import investigate as inv

    class Mail:
        def my_addresses(self): return {"me@example.org"}
        def list_between(self, start, end, limit):
            row = {"id": "mail-terms", "from": "ivy@lantern.example", "to": ["me@example.org"],
                   "date": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                   "subject": "Pilot contract"}
            return [row] if start <= row["date"] < end else []
        def get_email_body(self, email_id): return "Please see the contract."
        def list_attachments(self, email_id):
            return [{"id": "a1", "filename": "pilot.pdf", "mime_type": "application/pdf", "size": 2048}]
        def download_attachments(self, *args, **kwargs):
            pytest.fail("Indexing must not download attachments")

    store = tmp_path / "attachments"
    items, coverage = inv.gather("Ivy", ["ivy@lantern.example"], days=1, clients={"gmail": Mail()},
                                 subscriptions={}, attachments_dir=store)
    assert [item["role"] for item in items] == ["other", "attachments-index"]
    assert "pilot.pdf" in items[1]["text"]
    assert any("1 attachments indexed" in line for line in coverage)
    assert not store.exists()


@pytest.mark.parametrize("environment", ["uv/tools/connectonion", "plain venv", "custom-tools/connectonion"])
def test_without_the_rem_extra_a_spreadsheet_says_how_to_install_it(tmp_path, monkeypatch, environment):
    """openpyxl is the `co rem` extra, not a core dependency; a plain install names the
    spreadsheet as unread and gives the exact command, rather than crashing."""
    import builtins
    from connectonion._version import __version__

    prefix = tmp_path / environment
    executable = prefix / "bin" / "python"
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(sys, "executable", str(executable))
    if environment.startswith("custom-tools"):
        prefix.mkdir(parents=True)
        (prefix / "uv-receipt.toml").write_text("[tool]\n")
    installer = ([str(executable), "-m", "pip", "install"] if environment == "plain venv"
                 else ["uv", "tool", "install", "--force"])
    command = shlex.join([*installer, f"connectonion[rem]=={__version__}"])
    real_import = builtins.__import__

    def no_openpyxl(name, *args, **kwargs):
        if name == "openpyxl":
            raise ImportError("No module named 'openpyxl'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_openpyxl)
    path = tmp_path / "terms.xlsx"
    path.write_bytes(b"PK")
    assert extract_text(path) == (
        f"[XLSX not read: spreadsheet support is optional; run {command}, then investigate again]"
    )


@pytest.mark.parametrize("specifier", ["", ">=0.0.14,<1"])
def test_spreadsheet_install_preserves_uv_companion_requirements(tmp_path, monkeypatch, specifier):
    from connectonion._version import __version__

    (tmp_path / "uv-receipt.toml").write_text(
        '[tool]\nrequirements = [\n'
        '  { name = "connectonion", specifier = "==1.9.3rc47" },\n'
        f'  {{ name = "onionwright", specifier = "{specifier}" }},\n'
        '  { name = "other-package", specifier = "==2.0" },\n'
        ']\npython = "3.14"\n'
    )
    monkeypatch.setattr(sys, "prefix", str(tmp_path))

    command = spreadsheet_install_command()
    assert command == (
        f"uv tool install --force 'connectonion[rem]=={__version__}'"
        f" --with {shlex.quote('onionwright' + specifier)} --with other-package==2.0 --python 3.14"
    )


def test_pdf_annotation_text_is_not_mistaken_for_blank_party_fields(tmp_path):
    from pypdf import PdfWriter
    from pypdf.annotations import FreeText
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject

    writer = PdfWriter()
    writer.add_blank_page(width=400, height=500)
    writer.add_annotation(0, FreeText(text='Example Client Ltd', rect=(100, 300, 300, 340)))
    writer.add_annotation(0, FreeText(text='Sam Example, Director', rect=(100, 240, 300, 280)))
    writer.add_annotation(0, DictionaryObject({
        NameObject('/Subtype'): NameObject('/Stamp'),
        NameObject('/Rect'): ArrayObject([FloatObject(v) for v in (100, 180, 200, 210)]),
    }))
    path = tmp_path / 'returned agreement.pdf'
    writer.write(path)
    text = extract_text(path, limit=None)
    assert 'Example Client Ltd' in text and 'Sam Example, Director' in text
    assert 'PDF page 1' in text and 'stamp' in text.lower()
    assert 'appearance not read' in text
