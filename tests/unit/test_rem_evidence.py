"""The evidence directory an investigation searches instead of summarising (#1850)."""

from connectonion.rem.evidence import write_evidence


def item(source, when, text, **extra):
    return {"source": source, "timestamp": when, "text": text, **extra}


def test_a_mail_is_one_file_and_a_session_or_chat_is_one_conversation(tmp_path):
    items = [
        item("outlook:a1", "2026-09-02T09:00:00Z", "Invoice attached", speaker="vern@x.y", subject="Invoice"),
        item("outlook:a1:invoice.pdf", "2026-09-02T09:00:00Z", "Total $4,200", role="attachment",
             speaker="vern@x.y", subject="Invoice — invoice.pdf"),
        item("codex:s1:10", "2026-09-03T01:00:00Z", "fix the login bug", project="oo-chat"),
        item("codex:s1:20", "2026-09-03T01:05:00Z", "now ship it", project="oo-chat"),
        item("whatsapp:0a1b2c", "2026-09-04T05:00:00Z", "Venue booked", speaker="John",
             correspondent="120363@g.us"),
        item("whatsapp:3d4e5f", "2026-09-04T06:00:00Z", "Great", speaker="user", correspondent="120363@g.us"),
    ]

    out = write_evidence(tmp_path / "ev", items)

    files = sorted(p.relative_to(tmp_path / "ev").as_posix() for p in (tmp_path / "ev").rglob("*.md")
                   if p.name != "index.md")
    assert len(files) == 4 and out["files"] == 4          # mail, attachment, one session, one chat
    assert sorted(out["sources"]) == sorted(i["source"] for i in items)
    session = next(p for p in (tmp_path / "ev").rglob("*.md") if "fix the login bug" in p.read_text())
    assert "now ship it" in session.read_text()
    assert session.read_text().index("### codex:s1:10 ·") < session.read_text().index("### codex:s1:20 ·")
    index = out["index"].read_text()
    assert all(name in index for name in files)
    assert "6 items in 4 files" in index and "cite that source id" in index


def test_an_odd_source_id_cannot_escape_the_evidence_directory(tmp_path):
    out = write_evidence(tmp_path / "ev", [item("outlook:../../etc/passwd", "2026-09-01", "x")])

    written = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert all((tmp_path / "ev") in p.parents for p in written) and out["files"] == 1


def test_indexed_mail_preserves_actual_cc_when_rendered_body_omits_it(tmp_path):
    participants = {"from": "Lead <lead@school.example>", "to": ["me@example.org"],
                    "cc": ["Member <member@school.example>"]}
    text = "From: lead@school.example\nTo: me@example.org\n\nPlease approve the scope."
    write_evidence(tmp_path / "ev", [item("outlook:request", "2026-10-02", text,
                                         participants=participants)])
    packet = next(p.read_text() for p in (tmp_path / "ev").rglob("*.md") if p.name != "index.md")
    assert '"cc": ["Member <member@school.example>"]' in packet
    assert text in packet


def test_legacy_timestamp_scope_survives_an_indexed_evidence_packet(tmp_path):
    out = write_evidence(tmp_path / "ev", [item(
        "codex:legacy:100", "2025-11-04T15:24:50Z", "Vern asked about the placement",
        timestamp_scope="Legacy session start only; individual message time was not recorded")])
    body = next(p.read_text() for p in (tmp_path / "ev").rglob("*.md") if p.name != "index.md")
    assert "Timestamp scope: Legacy session start only; individual message time was not recorded" in body
    assert out["sources"] == ["codex:legacy:100"]


def test_a_month_of_one_mailbox_is_one_file_split_when_large(tmp_path):
    """#2080: Ody Zhou's 98k characters of mail were 373 files, one tool call each,
    and the turn re-sent its context every time: 2.77M input tokens."""
    from connectonion.rem.evidence import FILE_CHARS
    items = [item(f"outlook:m{n:03d}", f"2026-{7 + n % 3:02d}-{1 + n % 28:02d}T09:00:00Z", "x" * 260,
                  speaker="ody@x.y", subject=f"Thread {n}") for n in range(373)]
    items.append(item("gmail:g1", "2026-09-05T09:00:00Z", "From the other mailbox", speaker="ody@x.y"))

    out = write_evidence(tmp_path / "ev", items)

    files = [p for p in (tmp_path / "ev").rglob("*.md") if p.name != "index.md"]
    assert out["files"] == len(files) <= 8                         # 3 months × outlook, split once each, + gmail
    assert all(len(p.read_text()) <= FILE_CHARS + 1_000 for p in files)
    text = "".join(p.read_text() for p in files)
    assert all(text.count(f"### outlook:m{n:03d} ·") == 1 for n in range(373))   # each mail still citable
    assert sorted(out["sources"]) == sorted(i["source"] for i in items)
    assert any("gmail" in p.as_posix() for p in files) and not any(
        "From the other mailbox" in p.read_text() for p in files if "outlook" in p.as_posix())
