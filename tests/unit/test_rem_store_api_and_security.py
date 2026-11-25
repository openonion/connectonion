"""Regression and edge-case tests for Issue #3453:
- First-class `devices` category alongside `people` and `orgs` (files, store, CLI, reader UI rail & pageWords)
- SQLite store v2 universal `records` + `records_fts` + CJK fallback + pagination + tag filter + incremental per-file sync
- Server-side `[personal]` / `[sensitive]` (ASCII & fullwidth) redaction on `public` queries, translations, and `local=False` snapshots (#3435)
- Agent Host `/rem/*` OPTIONS preflight, DNS rebinding, external IP, `Origin: null`, and `Sec-Fetch-Site` CSRF defense
- Unified Agent Host query adapters (`GET /rem/query` on loopback HTTP and `WIKI_READ` query ops on OIP WS)
- Snapshot `repair_titles` N+1 file-read regression guard
- Reader JS O(1) `byPath` & language-keyed `KNOWN`/`FACTS`/`swapLanguage` cache execution in Node
"""

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from connectonion.network.host.http_router import handle_http
from connectonion.network.host.rem_http import handle_rem_http
from connectonion.network.host.ws_router.rem import handle_rem_read
from connectonion.rem import live_host, store
from connectonion.rem.config import prepare
from connectonion.rem.files import CATEGORIES, Notebook, RemError, state_path
from connectonion.rem.reader import TEMPLATE, render, snapshot


class OwnerTrust:
    def is_admin(self, address):
        return address == "owner"


def _build_base_fixture(root):
    prepare(root)
    book = Notebook(root)
    book.write(
        "people/corin.md",
        "# Corin Mar\n\n"
        "## Facts\n"
        "- Email: corin@acme.test [1]\n"
        "- Phone: +61 499 999 999 [personal]\n"
        "- Company: Acme [1]\n"
        "- Personal mobile: +61 488 888 888 [personal]\n"
        "- Tags: gateway, melbourne\n\n"
        "## Who they are\n"
        "Works with us on the gateway rollout [1].\n"
        "Going through a family hospital visit this week [sensitive].\n"
        "Fullwidth secret note ［personal］.\n"
        "- Discussed Q4 milestone timeline\n"
        "  and private family medical leave [sensitive]\n\n"
        "## Personal notes [personal]\n"
        "Private medical schedule details that must never leave public mode.\n\n"
        "### Nested medical subsection\n"
        "Nested secret under personal H2 that must also stay redacted.\n\n"
        "## Public follow-up\n"
        "Shipped v2 gateway benchmark.\n\n"
        "## Sources\n"
        "- [1] gmail:m1\n",
    )
    book.write(
        "knowledge/private-diary.md",
        "# Private diary [personal]\n\nPersonal reflections.\n",
    )
    book.write(
        "orgs/family-trust.md",
        "# Wu Family Holdings\n\n## Facts\n- Kind: personal\n\n## What it is\nPrivate family entity.\n",
    )
    book.write(
        "decisions/health-plan.md",
        "# Pause travel in December [personal]\n\nPrivate decision body.\n",
    )
    return book


def test_devices_is_a_first_class_category_across_store_cli_and_reader(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    assert "devices" in CATEGORIES
    assert CATEGORIES.index("devices") == CATEGORIES.index("orgs") + 1

    root = tmp_path / "rem"
    book = _build_base_fixture(root)
    book.write(
        "devices/aaron-dev-vm.md",
        "# aaron-dev GCP VM\n\n"
        "## Facts\n"
        "- Host: 34.129.107.227\n"
        "- Kind: Cloud VM\n"
        "- SSH key slot: YubiKey 9a [sensitive]\n"
        "- Tags: melbourne, cloud\n\n"
        "## What it is\n"
        "墨尔本主力云端开发机与 REM Host。\n",
    )
    info = store.refresh(root)
    assert info["rows"]["records"] >= 3

    devices = store.query_records(root, category="devices", include_unlisted=True)
    assert devices["total"] == 1
    row = devices["items"][0]
    assert row["record"] == "devices/aaron-dev-vm.md"
    assert row["title"] == "aaron-dev GCP VM"
    assert row["facts"]["Kind"] == "Cloud VM"
    assert row["tags"] == ["melbourne", "cloud"]

    # Public query redacts sensitive device facts while keeping public facts
    pub_devices = store.query_records(root, category="devices", privacy="public", include_unlisted=True)
    assert "SSH key slot" not in pub_devices["items"][0]["facts"]
    assert pub_devices["items"][0]["facts"]["Kind"] == "Cloud VM"

    # CLI `co rem list devices` works natively
    from typer.testing import CliRunner
    from connectonion.cli.main import app

    res = CliRunner().invoke(app, ["rem", "--root", str(root), "list", "devices"])
    assert res.exit_code == 0, res.output
    assert "devices/aaron-dev-vm.md" in res.output or "aaron-dev GCP VM" in res.output

    # Rendered HTML includes devices in categories and supports Chinese label
    html = render(root, local=True)
    assert '"devices"' in html
    assert '"Devices": "设备"' in html


def test_store_pagination_tag_filter_and_cjk_search(tmp_path):
    root = tmp_path / "rem"
    book = _build_base_fixture(root)
    for idx in range(5):
        book.write(
            f"devices/box-{idx}.md",
            f"# Build Box {idx}\n\n## Facts\n- Kind: Server\n- Tags: rack-{idx % 2}, infra\n\n"
            f"## What it is\nLocated in 墨尔本机房 node {idx}.\n",
        )
    store.refresh(root)

    page1 = store.query_records(root, category="devices", limit=2, offset=0)
    page2 = store.query_records(root, category="devices", limit=2, offset=2)
    page3 = store.query_records(root, category="devices", limit=2, offset=4)
    assert page1["total"] == 5
    assert len(page1["items"]) == 2 and len(page2["items"]) == 2 and len(page3["items"]) == 1
    seen = [r["record"] for p in (page1, page2, page3) for r in p["items"]]
    assert len(set(seen)) == 5

    tagged = store.query_records(root, tag="Rack 1")
    assert {r["record"] for r in tagged["items"]} == {"devices/box-1.md", "devices/box-3.md"}
    # Exact json_each tag match never false-matches prefix substrings
    assert store.query_records(root, tag="rack")["items"] == []

    # Unlisted pages (e.g. candidate skills) are excluded from search_records by default
    book.write("skills/candidates/local-helper.md", "# Local Helper\n\n## What it is\n墨尔本机房 staging script.\n")
    store.refresh(root)

    # CJK search works via FTS5 + substring fallback and respects listed=1
    cjk_hits = store.search_records(root, "墨尔本机房")
    assert len(cjk_hits) == 5
    assert "skills/candidates/local-helper.md" not in {h["record"] for h in cjk_hits}
    assert len(store.search_records(root, "墨尔本机房", include_unlisted=True)) == 6
    # Private text is never indexed into FTS5 or matched via public query_records (no search oracle)
    assert store.search_records(root, "hospital visit", privacy="public") == []
    assert store.query_records(root, query="hospital visit", privacy="public", include_unlisted=True)["items"] == []
    assert store.search_records(root, "Private diary", privacy="public") == []
    assert store.search_records(root, "Wu Family Holdings", privacy="public") == []
    assert store.search_records(root, "Pause travel", privacy="public") == []


def test_store_incremental_refresh_reads_only_changed_markdown_page_and_matches_full_rebuild(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    book = _build_base_fixture(root)
    store.refresh(root)

    book.write(
        "projects/atlas.md",
        "# Atlas\n\n## Facts\n- Repo: /repo/atlas\n\n## What it is\nCore search index.\n",
    )
    book.write(
        "devices/mac-mini.md",
        "# Studio Mac Mini\n\n## Facts\n- Kind: Mac Mini\n\n## What it is\nDesktop runner.\n",
    )
    read_paths = []
    real_read = Notebook.read

    def tracked_read(self, record):
        read_paths.append(record)
        return real_read(self, record)

    monkeypatch.setattr(Notebook, "read", tracked_read)
    store.refresh(root)
    monkeypatch.undo()

    assert set(read_paths) == {"projects/atlas.md", "devices/mac-mini.md"}
    assert "people/corin.md" not in read_paths
    assert [item["record"] for item in store.search_records(root, "Core search index")] == ["projects/atlas.md"]

    # Incremental leaf file removal cleans both records and records_fts without rereading people/
    book.delete("devices/mac-mini.md")
    read_paths.clear()
    monkeypatch.setattr(Notebook, "read", tracked_read)
    store.refresh(root)
    monkeypatch.undo()
    assert read_paths == []
    assert store.search_records(root, "Desktop runner") == []

    # Incremental state matches fresh rebuild from scratch
    incremental_rows = store.query_records(root, include_unlisted=True, limit=100)["items"]
    state_path(root, "rem.db").unlink()
    store.refresh(root)
    fresh_rows = store.query_records(root, include_unlisted=True, limit=100)["items"]
    assert incremental_rows == fresh_rows


def test_public_privacy_strips_personal_sensitive_fullwidth_and_translations_server_side(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    _build_base_fixture(root)

    monkeypatch.setattr(
        "connectonion.rem.translate.cached_languages",
        lambda _root, rec: (
            {
                "zh": "# Corin Mar\n\n## Who they are\n负责网关上线 [1]。\n本周家人在医院陪护 [sensitive]。\n\n"
                      "## 私人备注 ［personal］\n绝不能出现在公开模式的医疗排期。\n"
            }
            if rec == "people/corin.md"
            else {}
        ),
    )

    shared = snapshot(root, local=False, public_only=True)
    serialized = json.dumps(shared, ensure_ascii=False)
    assert "gateway rollout" in serialized
    assert "Shipped v2 gateway benchmark." in serialized
    assert "负责网关上线" in serialized
    for forbidden in (
        "+61 499 999 999",
        "+61 488 888 888",
        "hospital visit",
        "Private medical schedule",
        "Nested secret under personal H2",
        "Discussed Q4 milestone timeline",
        "private family medical leave",
        "Fullwidth secret",
        "Wu Family Holdings",
        "Pause travel in December",
        "医院陪护",
        "医疗排期",
    ):
        assert forbidden not in serialized, f"Leaked {forbidden!r} in public_only snapshot"

    store.refresh(root)
    public_page = store.get_record(root, "people/corin.md", privacy="public")
    assert public_page is not None
    assert "gateway rollout" in public_page["text"]
    assert "Shipped v2 gateway benchmark." in public_page["text"]
    assert "负责网关上线" in public_page["translations"]["zh"]
    for forbidden in (
        "+61 499 999 999",
        "+61 488 888 888",
        "hospital visit",
        "Private medical schedule",
        "Nested secret under personal H2",
        "Discussed Q4 milestone timeline",
        "private family medical leave",
        "Fullwidth secret",
    ):
        assert forbidden not in public_page["text"]
    assert "医院陪护" not in public_page["translations"]["zh"]
    assert "医疗排期" not in public_page["translations"]["zh"]
    assert "Personal mobile" not in json.dumps(public_page["facts"])
    assert "Phone" not in json.dumps(public_page["facts"])
    assert store.get_record(root, "knowledge/private-diary.md", privacy="public") is None
    assert store.get_record(root, "orgs/family-trust.md", privacy="public") is None
    assert store.get_record(root, "decisions/health-plan.md", privacy="public") is None

    # Public CRM people query recomputes derived columns from public_facts so private phone never leaks
    pub_people = store.dispatch_query(root, {"op": "people", "privacy": "public", "include_unlisted": "1"})["items"]
    assert len(pub_people) == 1
    assert pub_people[0]["phone"] == ""
    assert "+61" not in json.dumps(pub_people[0])


def test_corrupt_store_raises_actionable_recovery_command_on_read_and_rebuilds_on_refresh(tmp_path):
    root = tmp_path / "rem"
    _build_base_fixture(root)
    store.refresh(root)
    state_path(root, "rem.db").write_bytes(b"corrupted sqlite bytes")
    for suffix in ("-wal", "-shm"):
        Path(str(state_path(root, "rem.db")) + suffix).unlink(missing_ok=True)

    with pytest.raises(RemError, match="co rem sync"):
        store.query_records(root)

    rebuilt = store.refresh(root)
    assert "pages" in rebuilt["rebuilt"]
    assert store.query_records(root, include_unlisted=True)["total"] >= 2


def test_agent_host_rem_http_security_matrix_blocks_cors_rebinding_and_csrf(tmp_path):
    root = tmp_path / "rem"
    identity = tmp_path / "id"
    identity.mkdir()
    _build_base_fixture(root)
    token = live_host.reader_token(identity)
    routes = {"rem_root": root, "identity_dir": identity}

    async def raw_http(method, path, *, client="127.0.0.1", headers=(), body=b""):
        sent = []

        async def receive():
            return {"body": body, "more_body": False}

        async def send(msg):
            sent.append(msg)

        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "client": (client, 5000),
            "headers": list(headers),
        }
        await handle_http(
            scope,
            receive,
            send,
            route_handlers=routes,
            storage=None,
            trust="careful",
            start_time=0.0,
        )
        return sent[0]["status"], {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in sent[0]["headers"]}

    # 1. OPTIONS preflight on /rem/* never returns Access-Control-Allow-Origin
    for opt_path in ("/rem", "/rem/translate", "/rem/query", "/rem/keys/reveal"):
        status, hdrs = asyncio.run(
            raw_http(
                "OPTIONS",
                opt_path,
                headers=[[b"host", b"127.0.0.1:8123"], [b"origin", b"https://evil.example"]],
            )
        )
        assert status == 405
        assert "access-control-allow-origin" not in hdrs

    # 2. Non-loopback client IP -> 404
    status, _ = asyncio.run(
        raw_http("GET", "/rem/query", client="198.51.100.7", headers=[[b"host", b"127.0.0.1:8123"], [b"cookie", f"co_rem={token}".encode()]])
    )
    assert status == 404

    # 3. DNS rebinding Host header -> 404
    status, _ = asyncio.run(
        raw_http("GET", "/rem/query", headers=[[b"host", b"rebind.attacker.test:8123"], [b"cookie", f"co_rem={token}".encode()]])
    )
    assert status == 404

    # 4. Cross-site and cross-port POSTs/GETs -> 403
    for bad_headers in (
        [[b"origin", b"https://evil.example"]],
        [[b"origin", b"http://127.0.0.1:3000"]],
        [[b"origin", b"null"]],
        [[b"sec-fetch-site", b"cross-site"]],
        [[b"sec-fetch-site", b"same-site"]],
    ):
        status, _ = asyncio.run(
            raw_http(
                "POST",
                "/rem/thread",
                headers=[
                    [b"host", b"127.0.0.1:8123"],
                    [b"content-type", b"application/json"],
                    [b"cookie", f"co_rem={token}".encode()],
                    *bad_headers,
                ],
                body=b'{"key":"k1","state":"done"}',
            )
        )
        assert status == 403
        get_status, _ = asyncio.run(
            raw_http(
                "GET",
                "/rem/query",
                headers=[
                    [b"host", b"127.0.0.1:8123"],
                    [b"cookie", f"co_rem={token}".encode()],
                    *bad_headers,
                ],
            )
        )
        assert get_status == 403

    # Top-level browser link navigation to /rem with Sec-Fetch-Mode: navigate is permitted
    nav_status, _ = asyncio.run(
        raw_http(
            "GET",
            "/rem",
            headers=[
                [b"host", b"127.0.0.1:8123"],
                [b"sec-fetch-site", b"cross-site"],
                [b"sec-fetch-mode", b"navigate"],
                [b"cookie", f"co_rem={token}".encode()],
            ],
        )
    )
    assert nav_status == 200

    # 5. Legitimate same-origin loopback POST passes the origin gate (reaches action validation, not 403)
    status, _ = asyncio.run(
        raw_http(
            "POST",
            "/rem/language",
            headers=[
                [b"host", b"127.0.0.1:8123"],
                [b"origin", b"http://127.0.0.1:8123"],
                [b"sec-fetch-site", b"same-origin"],
                [b"content-type", b"application/json"],
                [b"cookie", f"co_rem={token}".encode()],
            ],
            body=b'{"language":"zh"}',
        )
    )
    assert status == 200


def test_agent_host_rem_query_works_over_local_http_and_remote_ws(tmp_path):
    root = tmp_path / "rem"
    identity = tmp_path / "id"
    identity.mkdir()
    _build_base_fixture(root)
    store.refresh(root)
    token = live_host.reader_token(identity)
    routes = {"rem_root": root, "identity_dir": identity, "trust_agent": OwnerTrust()}

    async def local_query(query_string, cookie=True):
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(msg):
            sent.append(msg)

        headers = [[b"host", b"127.0.0.1:8123"]]
        if cookie:
            headers.append([b"cookie", f"co_rem={token}".encode()])
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/rem/query",
            "query_string": query_string.encode(),
            "client": ("127.0.0.1", 5000),
            "headers": headers,
        }
        await handle_rem_http(scope, receive, send, routes)
        return sent[0]["status"], sent[1]["body"].decode("utf-8")

    status, body = asyncio.run(local_query("op=records&category=people&include_unlisted=1"))
    assert status == 200
    payload = json.loads(body)
    assert payload["total"] == 1
    assert payload["items"][0]["record"] == "people/corin.md"

    bad_op_status, _ = asyncio.run(local_query("op=unknown_op"))
    assert bad_op_status == 400

    unauth_status, _ = asyncio.run(local_query("op=records", cookie=False))
    assert unauth_status == 401

    async def ws_query(frame, *, address="owner", authenticated=True, signed=True, session_sync_only=False):
        sent = []

        async def send(msg):
            sent.append(msg)

        conn = {
            "authenticated": authenticated,
            "signed_commands": signed,
            "agent_address": address,
            "session_sync_only": session_sync_only,
        }
        await handle_rem_read(frame, send, conn, routes)
        return sent[0]

    ws_res = asyncio.run(
        ws_query({"request_id": "q1", "op": "record", "record": "people/corin.md", "privacy": "public"})
    )
    assert ws_res["ok"] is True
    assert "gateway rollout" in ws_res["result"]["text"]
    assert "hospital visit" not in ws_res["result"]["text"]

    ws_search = asyncio.run(ws_query({"request_id": "q-search", "op": "search", "query": "gateway", "include_unlisted": True}))
    assert ws_search["ok"] is True
    assert ws_search["result"]["items"][0]["record"] == "people/corin.md"

    assert asyncio.run(ws_query({"request_id": "q2", "op": "records"}, address="stranger"))["ok"] is False
    assert asyncio.run(ws_query({"request_id": "q3", "op": "records"}, authenticated=False))["ok"] is False
    assert asyncio.run(ws_query({"request_id": "q4", "op": "records"}, signed=False))["ok"] is False
    assert asyncio.run(ws_query({"request_id": "q5", "op": "drop_all"}))["ok"] is False
    assert asyncio.run(ws_query({"request_id": "q6", "op": "records"}, session_sync_only=True))["ok"] is False
    assert asyncio.run(ws_query({"request_id": "q7", "op": "records", "limit": "not-an-int"}))["ok"] is False


def test_snapshot_repair_titles_does_not_multiply_reads_by_tag_count(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    book = _build_base_fixture(root)
    for i in range(12):
        book.write(f"knowledge/topic-{i}.md", f"# Topic {i}\n\n- Tags: tag-{i}\n\nBody {i}.\n")

    reads = 0
    disk_md_reads = 0
    real_read = Notebook.read
    real_bytes = Path.read_bytes
    real_text = Path.read_text
    resolved_root = root.resolve()

    def counting_read(self, record):
        nonlocal reads
        reads += 1
        return real_read(self, record)

    def counting_bytes(self, *args, **kwargs):
        nonlocal disk_md_reads
        if self.suffix == ".md" and str(self).startswith(str(resolved_root)):
            disk_md_reads += 1
        return real_bytes(self, *args, **kwargs)

    def counting_text(self, *args, **kwargs):
        nonlocal disk_md_reads
        if self.suffix == ".md" and str(self).startswith(str(resolved_root)):
            disk_md_reads += 1
        return real_text(self, *args, **kwargs)

    monkeypatch.setattr(Notebook, "read", counting_read)
    monkeypatch.setattr(Path, "read_bytes", counting_bytes)
    monkeypatch.setattr(Path, "read_text", counting_text)
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    snapshot(root, local=True, today=True)
    assert disk_md_reads <= 20, f"Expected <=20 disk .md reads for 16 files, got {disk_md_reads}"
    assert reads < 150, f"Too many Notebook.read calls during snapshot: {reads}"


def test_tags_held_cache_is_thread_local_and_invalidates_on_notebook_mutation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from connectonion.rem.tags import held, once

    root_a = tmp_path / "rem_a"
    root_b = tmp_path / "rem_b"
    book_a = _build_base_fixture(root_a)
    _build_base_fixture(root_b)

    with held(root_a):
        assert "Corin Mar" in book_a.read("people/corin.md")
        once(root_a, "_custom_derived", lambda: "stale")
        book_a.write("people/corin.md", "# Corin Mar Updated\n\nFresh body.\n")
        assert "Corin Mar Updated" in book_a.read("people/corin.md")
        assert once(root_a, "_custom_derived", lambda: "recomputed") == "recomputed"

    def worker(root, label):
        with held(root):
            return once(root, "worker_tag", lambda: label)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(worker, root_a, f"a-{i}") if i % 2 == 0 else pool.submit(worker, root_b, f"b-{i}")
            for i in range(8)
        ]
        results = [f.result() for f in futures]
    assert len(results) == 8


def test_reader_js_executes_o1_path_index_devices_links_and_language_caches():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to run reader JS unit test")
    page = TEMPLATE.read_text(encoding="utf-8")
    assert "BY_PATH" in page
    assert "KNOWN.delete(r.path)" not in page
    assert "FACTS.delete(r.path)" not in page

    by_path_block = page[page.index("const BY_PATH = true"):page.index("// A list shows what the address's tag filter keeps")]
    swap_match = re.search(r"function swapLanguage\(.*?\n\}", page, re.S)
    words_match = re.search(r"function pageWords\(.*?\n\}", page, re.S)
    assert swap_match is not None and words_match is not None
    swap_fn = swap_match.group(0)
    page_words_fn = words_match.group(0)

    script = (
        'const STATEMENT_CATEGORIES = ["decisions", "principles"];\n'
        'const ACTIVITY = new Set(["notes", "logs"]);\n'
        + by_path_block
        + "\n"
        + swap_fn
        + "\n"
        + page_words_fn
        + r"""
        const REM = {
          owner: "people/me.md",
          records: [
            { path: "people/me.md", category: "people", title: "Aaron" },
            { path: "devices/aaron-dev.md", category: "devices", title: "aaron-dev GCP VM",
              text: "# aaron-dev GCP VM\n\nEnglish body", translations: { zh: "# aaron-dev 云主机\n\n中文内容" } }
          ]
        };
        const dev = byPath("devices/aaron-dev.md");
        const beforePush = inCategory("devices").map(r => r.path);
        const linked = pageWords("Deployed on devices/aaron-dev.md today.");
        swapLanguage(dev, "zh");
        const zhText = dev.text, zhShown = dev.shown;
        swapLanguage(dev, "");
        const enText = dev.text, enShown = dev.shown;
        // Mutating REM.records updates both BY_PATH and listedRecords/inCategory automatically
        REM.records.push({ path: "devices/mac-mini.md", category: "devices", title: "Mac Mini" });
        console.log(JSON.stringify({
          foundTitle: dev.title,
          beforePush,
          afterPushDevices: inCategory("devices").map(r => r.path),
          linked,
          zhText, zhShown,
          enText, enShown,
          afterPush: byPath("devices/mac-mini.md")?.title
        }));
        """
    )
    proc = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["foundTitle"] == "aaron-dev GCP VM"
    assert out["beforePush"] == ["devices/aaron-dev.md"]
    assert out["afterPushDevices"] == ["devices/aaron-dev.md", "devices/mac-mini.md"]
    assert out["linked"] == "Deployed on aaron-dev GCP VM today."
    assert out["zhShown"] == "zh" and "中文内容" in out["zhText"]
    assert out["enShown"] == "" and "English body" in out["enText"]
    assert out["afterPush"] == "Mac Mini"
