"""Private, bounded metadata snapshot of sources observed while building a map."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .files import atomic_write, state_path


class SourceInventory:
    """Collect source pointers, never message bodies or session transcripts."""

    def __init__(self, root: Path, progress=None):
        self.root = root
        self.progress = progress or (lambda message: None)
        self.records: list[dict] = []
        self.windows: list[dict] = []
        self.snapshot_report: dict | None = None

    def mail(self, provider: str, row: dict) -> None:
        # Provider listings may contain bodyPreview or arbitrary extra fields.
        # Explicitly allowlist the metadata needed to locate an original mail.
        def headers(value):
            return [str(item) for item in value] if isinstance(value, (list, tuple)) else [str(value)] if value else []
        self.records.append({"source": provider, "type": "mail",
                             "id": str(row.get("id") or ""),
                             "date": str(row.get("date") or ""),
                             "from": str(row.get("from") or ""),
                             "to": headers(row.get("to")),
                             "cc": headers(row.get("cc")),
                             "subject": str(row.get("subject") or "")})

    def window(self, provider: str, start: str, end: str, count: int | None, limit: int,
               complete: bool = False) -> None:
        if count is None:
            self.progress(f"{provider}: scanning {start[:10]} to {end[:10]} (limit {limit})")
            return
        self.windows.append({"source": provider, "start": start, "end": end,
                             "observed": count, "limit": limit,
                             "possibly_truncated": count >= limit and not complete,
                             "subdivided": count >= limit and complete})
        if self.snapshot_report is not None:
            self.save(self.snapshot_report)
        self.progress(f"{provider}: {count} observed in window; "
                      + ("scan split past the listing cap" if count >= limit and complete else
                         "cap reached, window incomplete" if count >= limit else "below cap"))

    def session(self, subscription: str, path: Path, stamp: datetime, cwd: str) -> None:
        self.records.append({"source": subscription, "type": "session",
                             "path": str(path), "modified": stamp.isoformat(), "cwd": cwd})

    def skill(self, row: dict) -> None:
        self.records.append({"source": row.get("location", "installed"), "type": "skill",
                             "path": row["path"], "name": row["name"]})

    def save(self, report: dict) -> dict:
        """Replace the snapshot atomically; an init rerun never appends duplicates."""
        records = state_path(self.root, "source-inventory.jsonl")
        summary = state_path(self.root, "source-inventory.md")
        atomic_write(records, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in self.records))
        mail_count = sum(row["type"] == "mail" for row in self.records)
        session_count = sum(row["type"] == "session" for row in self.records)
        capped = sum(row["possibly_truncated"] for row in self.windows)
        subdivided = sum(row["subdivided"] for row in self.windows)
        lines = ["# Wiki source inventory", "", f"Observed at: {report['started']}",
                 f"Window: last {report['days']} days", "",
                 f"- Mail metadata rows observed: {mail_count}",
                 f"- Local session pointers observed: {session_count}",
                 f"- Installed skill metadata entries: {len(report.get('skills', {}).get('skills', []))}",
                 f"- Mail windows at the {self.windows[0]['limit'] if self.windows else 200}-item cap: {capped}",
                 f"- Mail windows split past that cap: {subdivided}",
                 "- Mailbox lifetime total: unknown (this is a window-limited scan)",
                 "- Contents: private metadata pointers only; no mail bodies, attachments, or session text", "",
                 "## Mail windows", ""]
        lines += [f"- {row['source']}: {row['start'][:10]} to {row['end'][:10]} — "
                  f"{row['observed']} observed" + ("; possibly truncated" if row['possibly_truncated'] else
                                                   "; split past cap" if row['subdivided'] else "")
                  for row in self.windows] or ["- No connected mail source was scanned."]
        lines += ["", "## Coverage and errors", ""]
        lines += [f"- {entry}" for entry in report.get("coverage", [])]
        lines += [f"- {entry.get('source', 'unknown')}: {entry.get('stage', 'unknown')} "
                  f"({entry.get('error', 'error')})" for entry in report.get("errors", [])]
        atomic_write(summary, "\n".join(lines) + "\n")
        return {"summary": str(summary.relative_to(self.root)),
                "records": str(records.relative_to(self.root)),
                "mail_observed": mail_count, "sessions_observed": session_count,
                "capped_mail_windows": capped, "split_mail_windows": subdivided,
                "mailbox_total": "unknown"}
