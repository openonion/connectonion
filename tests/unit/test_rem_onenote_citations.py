"""Immutable OneNote citations at the Reader and live translation boundaries."""
import asyncio
import json
from pathlib import Path

import pytest

from connectonion.rem.source_links import source_record_context, public_source_text
from connectonion.rem.files import RemError
from connectonion.useful_tools.adapter import append_daily_jsonl, make_record, record_reference


def original(tmp_path, *, text="A synthetic proposal remains unapproved.", url="https://example.invalid/note"):
    row = make_record("onenote", "synthetic-account", "page", "page", title="Synthetic note", text=text, url=url)
    path, _ = append_daily_jsonl([row], tmp_path / "docs/onenote", keep_versions=True)
    ref = "adapter:" + record_reference(path, row, tmp_path)
    return row, path, ref


@pytest.mark.parametrize("url,reason", [
    ("https://graph.microsoft.com/v1.0/me/onenote/pages/page/content", "api_only"),
    ("javascript:alert(1)", "unsafe_url"),
    ("https://example.invalid/note?access_token=synthetic", "unsafe_url"),
    ("https://user:password@example.invalid/note", "unsafe_url"),
])
def test_reader_rejects_api_and_unsafe_original_links(tmp_path, url, reason):
    _, _, ref = original(tmp_path, url=url)
    context = source_record_context(tmp_path, ref)
    assert context["status"] == "resolved"
    assert context["url"] == ""
    assert context["reason"] == reason


def test_old_citation_keeps_exact_original_and_private_text_is_withheld(tmp_path):
    row, path, ref = original(tmp_path, text="[personal] Synthetic private sentence.")
    append_daily_jsonl([{**row, "text": "Later public version."}], tmp_path / "docs/onenote", keep_versions=True)
    assert source_record_context(tmp_path, ref)["excerpt"] == ""
    assert "Synthetic private sentence" in source_record_context(tmp_path, ref, private=True)["excerpt"]
    path.write_text(json.dumps({**row, "text": "Mutated history"}) + "\n")
    assert source_record_context(tmp_path, ref)["status"] == "not_found"


def test_symlinked_citation_never_reads_outside_notebook(tmp_path):
    row, path, ref = original(tmp_path)
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    assert source_record_context(tmp_path, ref)["status"] == "error"


def test_secret_shaped_original_is_withheld_from_reader_and_models(tmp_path):
    from connectonion.rem.onenote_imports import evidence_item, item

    synthetic = "sk-" + "x" * 32
    row, path, ref = original(tmp_path, text=f"Synthetic text with {synthetic}.",
                              url=f"https://example.invalid/{synthetic}")
    before = path.read_bytes()
    context = source_record_context(tmp_path, ref, private=True)
    assert context["excerpt"] == "[secret-shaped text withheld]"
    assert context["url"] == "" and context["reason"] == "unsafe_url"
    with pytest.raises(RemError, match="secret-shaped text"):
        item(tmp_path, row, ref.removeprefix("adapter:"))
    with pytest.raises(RemError, match="secret-shaped text"):
        evidence_item(tmp_path, ref)
    assert path.read_bytes() == before


@pytest.mark.parametrize("completed", [False, True])
def test_live_translation_aliases_citations_for_cached_and_completed_paths(tmp_path, monkeypatch, completed):
    from connectonion.network.host import rem_http
    from connectonion.rem import translate
    _, _, ref = original(tmp_path)
    text = "# Synthetic\n\nProposal [1].\n\n## Sources\n- [1] " + ref + "\n"
    monkeypatch.setattr(translate, "cached", lambda *a: text)
    monkeypatch.setattr(rem_http, "TASKS", {})
    async def run():
        if completed:
            future = asyncio.get_running_loop().create_future()
            future.set_result(text)
            rem_http.TASKS[(str(tmp_path), "notes/test.md", "zh")] = future
        return rem_http._progress(tmp_path, "notes/test.md", "zh")
    result = asyncio.run(run())
    assert result["state"] == "ready"
    assert ref not in result["text"]
    assert "synthetic-account" not in result["text"]
    assert "source-ref:" in result["text"]
    assert result["text"] == public_source_text(text)


@pytest.mark.parametrize("status,link,url,expected", [
    ("resolved", "ok", "https://example.invalid/note", True),
    ("resolved", "api_only", "", False),
    ("resolved", "unavailable", "javascript:alert(1)", False),
    ("not_found", "unavailable", "", False),
    ("error", "unavailable", "", False),
])
def test_current_reader_original_link_and_unavailable_states(status, link, url, expected):
    from onenote_reader_fixtures import _run
    context = {"source": "onenote", "status": status, "link": link, "url": url}
    result = _run("const sourceView=onenoteSourceLink(" + json.dumps(context) + ");console.log(JSON.stringify({tag:sourceView.tag,href:sourceView.attrs.href||'',text:sourceView.textContent}));", {"records": []}, ("onenoteSourceLink",))
    assert (result["tag"] == "a") is expected
    assert result["href"] == (url if expected else "")
    assert result["text"]
