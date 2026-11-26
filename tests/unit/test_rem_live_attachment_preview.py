"""Owner-only native file previews, bounded live refreshes and quiet idle readers."""

import asyncio
import gzip
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

import pytest

from connectonion.network.host import rem_http
from connectonion.rem import attachments, evidence, reader, reader_model, translate
from connectonion.rem.config import prepare
from connectonion.rem.files import state_path, write_json
from tests.unit.test_rem_reader import _reader_function, _run_reader_js

SOURCE = "gmail:012345abcdef:pilot.pdf"


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    monkeypatch.setattr("connectonion.rem.live_host.reader_token", lambda directory: "reader-test-token")
    return root


def request(root, path, *, source=SOURCE, cookie=True, client="127.0.0.1", host="localhost:8123",
            encoding="", method="GET", payload=None):
    headers = [[b"host", host.encode()], [b"content-type", b"application/json"]]
    if cookie:
        headers.append([b"cookie", b"co_rem=reader-test-token"])
    if encoding:
        headers.append([b"accept-encoding", encoding.encode()])
    scope = {"type": "http", "method": method, "path": path, "client": (client, 10),
             "headers": headers, "query_string": urlencode({"id": source}).encode()}
    sent = []

    async def receive():
        return {"body": json.dumps(payload or {}).encode(), "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(rem_http.handle_rem_http(scope, receive, send, {"rem_root": root, "identity_dir": root.parent}))
    return sent[0]["status"], {k.decode(): v.decode() for k, v in sent[0]["headers"]}, sent[1]["body"]


def retained(root, name="pilot.pdf", content=b"retained"):
    path = state_path(root, "attachments/gmail/012345abcdef/" + name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path, "gmail:012345abcdef:" + name


@pytest.mark.parametrize("suffix,mime,inline", [
    (".pdf", "application/pdf", True), (".png", "image/png", True),
    (".jpg", "image/jpeg", True), (".jpeg", "image/jpeg", True),
    (".gif", "image/gif", True), (".webp", "image/webp", True),
    *[(suffix, "application/octet-stream", False) for suffix in
      (".html", ".htm", ".svg", ".xml", ".js", ".docx", ".xlsx", ".pptx", ".zip")],
    *[(suffix, "text/plain; charset=utf-8", False) for suffix in (".txt", ".md", ".csv", ".ics")],
])
def test_authenticated_attachment_headers(notebook, suffix, mime, inline):
    path, source = retained(notebook, "pilot" + suffix, b"file bytes")
    status, headers, body = request(notebook, "/rem/attachment", source=source)
    assert status == 200 and body == path.read_bytes()
    assert headers["content-type"] == mime
    assert headers["content-disposition"].startswith(("inline" if inline else "attachment") + "; filename=\"pilot")
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["cache-control"] == "private, max-age=300"
    assert headers["x-frame-options"] == "SAMEORIGIN"
    policy = headers["content-security-policy"]
    if inline:
        assert "sandbox" not in policy and "script-src 'none'" in policy
    else:
        assert policy == "sandbox; default-src 'none'"


@pytest.mark.parametrize("options,status", [({"cookie": False}, 401), ({"client": "192.0.2.1"}, 404),
                                            ({"host": "rebound.example"}, 404)])
def test_attachment_requires_the_reader_cookie_and_loopback(notebook, options, status):
    retained(notebook)
    assert request(notebook, "/rem/attachment", **options)[0] == status


@pytest.mark.parametrize("source", ["file:pilot.pdf", "gmail:short:pilot.pdf", "gmail:012345abcdef:../pilot.pdf",
                                    "gmail:012345abcdef:..", "gmail:012345abcdef:pilot\\file.pdf",
                                    "gmail:012345abcdef:pilot\r\n.pdf", "gmail:012345abcdef:pilot\x00.pdf",
                                    "gmail:012345abcdef:absent.pdf"])
def test_attachment_rejects_traversal_and_invalid_ids(notebook, source):
    assert request(notebook, "/rem/attachment", source=source)[0] == 404


@pytest.mark.parametrize("linked", ["file", "message", "attachments", "state"])
def test_attachment_rejects_symlinked_files_and_ancestors(notebook, tmp_path, linked):
    path, source = retained(notebook)
    target = tmp_path / "outside"
    if linked == "file":
        target.write_bytes(b"private")
        path.unlink()
        path.symlink_to(target)
    else:
        import shutil
        folder = {"message": path.parent, "attachments": path.parents[2], "state": path.parents[3]}[linked]
        shutil.move(str(folder), target)
        folder.symlink_to(target, target_is_directory=True)
    assert request(notebook, "/rem/attachment", source=source)[0] == 404


def test_attachment_filename_cannot_inject_response_headers(notebook):
    _, source = retained(notebook, 'pilot";name.pdf')
    status, headers, _ = request(notebook, "/rem/attachment", source=source)
    assert status == 200 and '%22%3B' in headers["content-disposition"]


@pytest.mark.parametrize("path", ["/rem", "/rem/data.json", "/rem/query", "/rem/source"])
@pytest.mark.parametrize("encoding,compressed", [("gzip", True), ("br, gzip;q=0.5", True),
                                                 ("gzip;q=0", False), ("br", False), ("", False)])
def test_large_reader_responses_negotiate_gzip(notebook, monkeypatch, path, encoding, compressed):
    data = {"excerpt": "retained words " * 150, "truncated": False}
    monkeypatch.setattr(reader, "cached_page", lambda *args: (json.dumps(data), False))
    monkeypatch.setattr("connectonion.rem.store.dispatch_query", lambda *args, **kwargs: data)
    monkeypatch.setattr(reader_model, "cited_context", lambda *args, **kwargs: {SOURCE: data})
    status, headers, body = request(notebook, path, encoding=encoding)
    assert status == 200
    assert (headers.get("content-encoding") == "gzip") == compressed
    if compressed:
        assert headers["vary"] == "Accept-Encoding"
        body = gzip.decompress(body)
    assert json.loads(body) == data


def test_small_response_is_not_compressed(notebook, monkeypatch):
    monkeypatch.setattr(reader, "cached_page", lambda *args: ("small", False))
    assert "content-encoding" not in request(notebook, "/rem", encoding="gzip")[1]


def test_structured_attachment_text_keeps_spreadsheet_rows_and_document_paragraphs(notebook):
    from openpyxl import Workbook
    from docx import Document

    sheet, source = retained(notebook, "pilot.xlsx")
    book = Workbook()
    book.active.title = "Terms"
    book.active.append(["Fee", "Term"])
    book.active.append(["8%", "90 days"])
    book.save(sheet)
    context = attachments.attachment_context(notebook, source)
    assert context["excerpt"] == "Sheet: Terms\nFee | Term\n8% | 90 days"
    assert context["preview_kind"] == "table" and context["size"] == sheet.stat().st_size
    assert context["url"] == context["file"] == "/rem/attachment?id=" + source.replace(":", "%3A")
    document, _ = retained(notebook, "pilot.docx")
    doc = Document()
    doc.add_paragraph("First clause")
    doc.add_paragraph("Second clause")
    doc.save(document)
    assert attachments.extract_structured_text(document) == "First clause\nSecond clause"
    assert attachments.extract_text(document) == "First clause Second clause"


@pytest.mark.parametrize("suffix,kind", [(".pdf", "pdf"), (".png", "image"), (".zip", "download")])
def test_empty_text_attachments_still_have_native_context(notebook, suffix, kind):
    path, source = retained(notebook, "pilot" + suffix)
    if suffix == ".pdf":
        from pypdf import PdfWriter
        pdf = PdfWriter()
        pdf.add_blank_page(width=100, height=100)
        pdf.write(path)
    context = attachments.attachment_context(notebook, source)
    assert context["preview_kind"] == kind and context["excerpt"] == ""
    assert not context["truncated"] and context["file"].startswith("/rem/attachment?")


def test_attachment_excerpt_is_bounded_and_reports_truncation(notebook):
    path, source = retained(notebook, "pilot.txt", ("clause\n" * 2000).encode())
    context = attachments.attachment_context(notebook, source)
    assert len(context["excerpt"]) == 8000 and context["truncated"]
    assert "\n" in context["excerpt"]
    assert len(attachments.extract_structured_text(path, limit=10)) == 10


def test_bulk_mail_cannot_starve_attachments_or_structured_sources(notebook, monkeypatch):
    _, source = retained(notebook, "pilot.txt", b"important clause")
    records = [{"text": "## Sources\n- [1] gmail:bulk\n- [2] " + source + "\n- [3] https://example.test/pilot"}]
    monkeypatch.setattr(reader_model, "has_message_index", lambda path: True)
    class Database:
        def close(self): pass
    monkeypatch.setattr(reader_model.sqlite3, "connect", lambda *args, **kwargs: Database())
    monkeypatch.setattr(reader_model, "_cited_row", lambda db, value: {"source": "gmail"} if value == "gmail:bulk" else None)
    monkeypatch.setattr(reader_model, "archived_message", lambda *args: {"body": "m" * 40_000})
    monkeypatch.setattr(evidence, "research_contexts", lambda *args, **kwargs: {
        "https://example.test/pilot": {"excerpt": "web finding", "truncated": False}})
    context = reader_model.cited_context(notebook, records, budget=100, private=True)
    assert context[source]["excerpt"] == "important clause"
    assert context["https://example.test/pilot"]["excerpt"] == "web finding"
    assert len(reader_model.cited_context(notebook, records, budget=500_000)["gmail:bulk"]["excerpt"]) == 4096
    assert len(reader_model.cited_context(notebook, records, budget=200_000)["gmail:bulk"]["excerpt"]) == 32768


def test_private_file_citations_are_local_text_without_links_or_secrets(notebook, tmp_path):
    (notebook / "pilot.md").write_text("Local terms\nSecond line")
    record = [{"text": "## Sources\n- [1] file:pilot.md"}]
    assert reader_model.cited_context(notebook, record, private=True)["file:pilot.md"]["excerpt"] == "Local terms\nSecond line"
    assert reader_model.cited_context(notebook, record) == {}
    (notebook / "secret.md").write_text("private key")
    (notebook / "link.md").symlink_to(notebook / "pilot.md")
    for relative in ("../outside.md", ".env", "secret.md", "link.md", "pilot.pdf", str(tmp_path / "outside.md")):
        assert reader_model.local_file_context(notebook, "file:" + relative, True) is None


@pytest.mark.parametrize("date", ["2026-11-26", "2026-11-25"])
def test_research_dates_accept_full_timestamps_and_fall_back_to_saved_capture(notebook, date):
    from pypdf import PdfWriter
    path, source = retained(notebook)
    pdf = PdfWriter()
    pdf.add_blank_page(width=100, height=100)
    pdf.write(path)
    digest = hashlib.sha256(source.encode()).hexdigest()
    write_json(state_path(notebook, f"research/{digest}/capture.json"),
               {"source": source, "text": "Saved finding", "timestamp": "2026-11-26T10:15:30Z"})
    records = [{"text": f"\n## Sources\n- [1] {source} — {date}"}]
    context = evidence.research_contexts(notebook, records)[source]
    assert context["excerpt"] == "Saved finding" and context["preview_kind"] == "pdf"
    assert context["url"] == context["file"] and context["url"].startswith("/rem/attachment?")


@pytest.mark.parametrize("path,payload", [
    ("/rem/thread", {"key": "people/alice.md\nthread", "state": "done"}),
    ("/rem/sender", {"address": "reader@example.test", "ignored": True}),
    ("/rem/language", {"language": "zh"}),
    ("/rem/translation-request", {"page": "people/alice.md", "language": "zh"}),
])
def test_lightweight_state_actions_never_rebuild_the_notebook(notebook, monkeypatch, path, payload):
    monkeypatch.setattr("connectonion.rem.threads.set_state", lambda *args, **kwargs: {"state": "done"})
    monkeypatch.setattr("connectonion.rem.threads.ignore_sender", lambda *args, **kwargs: True)
    monkeypatch.setattr("connectonion.rem.config.request_language", lambda *args: {"language": "zh"})
    monkeypatch.setattr(translate, "request", lambda *args: {"state": "saved"})
    changed = []
    monkeypatch.setattr(reader, "owner_changed", lambda root, *, builds: changed.append(builds))
    assert request(notebook, path, method="POST", payload=payload)[0] == 200
    assert changed == [("live",)]


def test_owner_changes_and_live_refreshes_never_build_file_html(notebook, monkeypatch):
    requested = []
    monkeypatch.setattr(reader, "_spawn_refresh", lambda root, builds: requested.extend(builds) or True)
    reader.owner_changed(notebook)
    assert requested == ["live", "full"]
    assert reader.NEEDS["live.html"] == ("live", "full")
    assert reader.NEEDS["data.json"] == ("full",)
    assert reader.NEEDS["file.html"] == ("file",)
    monkeypatch.setattr(reader, "snapshot", lambda *args, **kwargs: {"as_of": "now"})
    monkeypatch.setattr(reader, "_page", lambda *args, **kwargs: "HTML")
    monkeypatch.setattr(reader, "_today_data", lambda data: data)
    assert set(reader._render(notebook, "live")[0]) == {"live.html"}
    assert set(reader._render(notebook, "full")[0]) == {"data.json"}
    assert set(reader._render(notebook, "file")[0]) == {"file.html"}


def test_shell_action_during_full_render_only_queues_the_shell(notebook, monkeypatch):
    builds = []
    monkeypatch.setattr(reader.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("worker already holds the lock"))

    def render(root, build, as_of=None):
        builds.append(build)
        if build == "full":
            (root / "pilot.md").write_text("New state during full render")
            reader.owner_changed(root, builds=("live",))
        return {"data.json" if build == "full" else "live.html": "{}"}, as_of, 0

    monkeypatch.setattr(reader, "_render", render)
    reader.refresh(notebook, ("full",))
    assert builds == ["full", "live"]


def test_a_saved_snapshot_does_not_bypass_waiting_for_http_host(notebook, monkeypatch):
    monkeypatch.setattr(reader, "_has_saved_page", lambda root: True)
    monkeypatch.setattr("connectonion.rem.live_host.ensure_local", lambda address: ("http://localhost:8123/rem?token=test", None))
    monkeypatch.setattr(reader, "_rebuild_stale", lambda *args, **kwargs: True)
    monkeypatch.setattr(reader, "open_snapshot", lambda *args, **kwargs: pytest.fail("opened stale file snapshot"))
    assert reader.local_or_snapshot(notebook, "local-agent", launch=False)["page"] == "http://localhost:8123/rem"


def test_idle_translation_counts_are_cached_briefly(notebook, monkeypatch):
    translate.IDLE_COUNTS.clear()
    translate.JOBS.clear()
    scans = []
    monkeypatch.setattr(translate, "readable", lambda root: scans.append(root) or ["pilot.md"])
    monkeypatch.setattr(translate, "current", lambda *args: True)
    clock = [1.0]
    monkeypatch.setattr(translate, "monotonic", lambda: clock[0])
    for _ in range(5):
        assert translate.every_page(notebook, "status", "zh")["done"] == 1
    assert len(scans) == 1
    clock[0] += translate.IDLE_COUNTS_TTL + 1
    translate.every_page(notebook, "status", "zh")
    assert len(scans) == 2


@pytest.mark.parametrize("state,polls", [(s, s in ("starting", "running", "stopping")) for s in
                                       ("idle", "starting", "running", "stopping", "done", "failed", "stopped", "halted")])
@pytest.mark.parametrize("offline", [False, True])
def test_translation_polling_stops_in_every_terminal_or_idle_state(state, polls, offline):
    script = _reader_function("translateAllSend")
    # The extracted function is async in the real page too.
    result = _run_reader_js("async " + script + "\n" + f'''
      let translateAllPoll = 7, translateAllWait = 1500, translateAllJob = {{state: {json.dumps(state)}}};
      let timers = 0, cleared = false;
      const clearTimeout = id => {{ cleared = id === 7; }}, setTimeout = () => {{ timers++; return 8; }};
      const translateAllLanguage = () => 'zh', renderLangProgress = () => {{}};
      const document = {{querySelectorAll: () => []}};
      const fetch = async () => {{
        if ({json.dumps(offline)}) throw Error('offline');
        return {{ok: true, json: async () => ({{state: {json.dumps(state)}}})}};
      }};
      translateAllSend('status').then(() => console.log(JSON.stringify({{timers, cleared, timer: translateAllPoll}})));
    ''')
    assert result["cleared"] and result["timers"] == int(polls)
    assert result["timer"] == (8 if polls else None)


@pytest.mark.parametrize("kind,filename,tag", [("pdf", "pilot.pdf", "iframe"), ("image", "pilot.png", "img")])
def test_native_previews_use_only_local_http_attachment_routes(kind, filename, tag):
    result = _run_reader_js(_reader_function("attachmentPreview") + f'''
      const el = (tag, attrs) => ({{tag, ...attrs}}), location = {{protocol: 'http:'}};
      const context = {{preview_kind: {json.dumps(kind)}, filename: {json.dumps(filename)}, url: '/rem/attachment?id=source'}};
      const native = attachmentPreview(context);
      const unsafe = attachmentPreview({{...context, url: 'https://example.test/active.html'}});
      location.protocol = 'file:';
      console.log(JSON.stringify({{native, unsafe, offline: attachmentPreview(context)}}));
    ''')
    assert result["native"]["tag"] == tag and result["unsafe"] is None and result["offline"] is None


def test_a_live_refresh_never_refreshes_an_existing_offline_snapshot(notebook, monkeypatch):
    builds = []
    def render(root, build, as_of=None):
        builds.append(build)
        texts = {"file.html": "offline"} if build == "file" else {"live.html": "live"} if build == "live" else {"data.json": "{}"}
        return texts, as_of, 0
    monkeypatch.setattr(reader, "_render", render)
    reader.refresh(notebook, ["file"])
    offline = reader.saved(notebook, "file")
    (notebook / "pilot.md").write_text("New terms")
    reader.refresh(notebook)
    assert builds == ["file", "live", "full"]
    assert reader.saved(notebook, "file") == offline


@pytest.mark.parametrize("active,requested", [("live", "full"), ("full", "live")])
def test_explicit_build_requests_waiting_behind_another_build_are_not_lost(notebook, monkeypatch, active, requested):
    builds = []
    def render(root, build, as_of=None):
        builds.append(build)
        if len(builds) == 1:
            assert reader._spawn_refresh(root, [requested])
        texts = {"file.html": "offline"} if build == "full" else {"live.html": "live", "data.json": "{}"}
        return texts, as_of, 0
    monkeypatch.setattr(reader, "_render", render)
    assert reader.refresh(notebook, [active])
    assert builds == [active, requested]
    assert reader._pending_builds(notebook) == []
    assert reader.page_path(notebook, "file.html") is not None
    assert reader.page_path(notebook, "live.html") is not None


def test_documents_keep_research_only_attachments_and_open_the_evidence_drawer():
    result = _run_reader_js(_reader_function("recordContext") + r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children,
        appendChild(node) { this.children.push(node); }});
      const sourceList = () => [{n: '1', text: 'saved'}, {n: '2', text: 'local'}];
      const sourceId = text => text, citeChip = n => n, connectedContext = () => null;
      let opened = null;
      const openEvidence = (r, n, trigger, options) => { opened = {n, options}; };
      const REM = {source_context: {
        saved: {source: 'attachment', filename: 'retained.pdf', excerpt: 'research capture'},
        local: {source: 'attachment', filename: 'pilot.pdf', url: '/rem/attachment?id=local'}}};
      const section = recordContext({path: 'people/alice.md', category: 'people'}).children[0];
      const list = section.children[1].children;
      list[0].children[0].onclick();
      console.log(JSON.stringify({count: list.length, fallback: list[0].children[0].tag,
        local: list[1].children[0], opened}));
    ''')
    assert result["count"] == 2 and result["fallback"] == "button"
    assert result["local"]["href"] == "/rem/attachment?id=local"
    assert result["opened"] == {"n": "1", "options": {"fromList": True}}


def test_structured_preview_search_targets_the_visible_preserved_text():
    result = _run_reader_js(_reader_function("evidenceOriginal") + r'''
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children, textContent: attrs.html || attrs.text || ''});
      const sourceChannel = () => 'Attachment', sourceSender = () => '', attachmentPreview = () => null;
      let searched;
      const sourceFind = (text, node) => { searched = node; return {tag: 'search'}; };
      UI.zh = {Open: '打开'}; uiLanguage = 'zh';
      const html = 'Sheet: Terms\nFee | <mark>8%</mark>\n' + 'Clause | Value\n'.repeat(200);
      const context = {source: 'attachment', filename: 'pilot.xlsx', excerpt: html, url: '/rem/attachment?id=pilot'};
      const result = evidenceOriginal(context, {innerHTML: html, textContent: html});
      const visible = result.children.find(node => node?.tag === 'pre');
      console.log(JSON.stringify({same: searched === visible, html: visible.html,
        link: result.children.find(node => node?.tag === 'a').text}));
    ''')
    assert result["same"] and "\nFee | <mark>8%</mark>\n" in result["html"]
    assert result["link"] == "打开 pilot.xlsx →"


def test_first_live_render_schedules_an_explicit_snapshot_waiting_on_its_lock(notebook, monkeypatch):
    spawned = []
    monkeypatch.setattr(reader.subprocess, "Popen", lambda command, **kwargs: spawned.append(command))
    def render(root, build, as_of=None):
        assert build == "live"
        assert reader._spawn_refresh(root, ["file"])
        assert spawned == []  # the first render still owns the lock
        return {"live.html": "live"}, as_of, 0
    monkeypatch.setattr(reader, "_render", render)
    assert reader.cached_page(notebook, "live.html")[0] == "live"
    assert len(spawned) == 1 and spawned[0][-2:] == ["file", "full"]
