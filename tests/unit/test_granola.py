"""Unit tests for connectonion.useful_tools.granola (Granola API v1 read-only client)."""

import httpx
import pytest


def _mock_client(handler):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer grn_test_key"},
    )


def test_missing_api_key_names_env_setup_command(monkeypatch, tmp_path):
    from connectonion.useful_tools.granola import GranolaClient, GranolaError

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GRANOLA_API_KEY", raising=False)
    monkeypatch.setattr("connectonion.useful_tools.granola._read_saved_key", lambda: "")

    with pytest.raises(GranolaError) as exc:
        GranolaClient()
    assert exc.value.kind == "unauthorized"
    assert "co env set GRANOLA_API_KEY" in exc.value.next_step


def test_401_and_403_raise_typed_errors_without_echoing_secret(monkeypatch):
    from connectonion.useful_tools.granola import GranolaClient, GranolaError

    secret = "grn_super_secret_token_999"
    monkeypatch.setenv("GRANOLA_API_KEY", secret)

    def handle_401(_req):
        return httpx.Response(401, json={"error": "invalid token"})

    client_401 = GranolaClient(_http=_mock_client(handle_401))
    with pytest.raises(GranolaError) as e401:
        client_401.check()
    assert e401.value.kind == "unauthorized"
    assert secret not in str(e401.value)

    def handle_403(_req):
        return httpx.Response(403, json={"error": "forbidden"})

    client_403 = GranolaClient(_http=_mock_client(handle_403))
    with pytest.raises(GranolaError) as e403:
        client_403.list_folders()
    assert e403.value.kind == "forbidden"
    assert secret not in str(e403.value)


def test_transient_429_retries_then_succeeds(monkeypatch):
    from connectonion.useful_tools import granola

    monkeypatch.setenv("GRANOLA_API_KEY", "grn_test")
    waits = []
    monkeypatch.setattr(granola, "_sleep", lambda s: waits.append(s))

    attempts = {"n": 0}

    def handler(req):
        if req.url.path.endswith("/folders"):
            return httpx.Response(200, json={"folders": [], "hasMore": False})
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "1"}, json={"message": "slow down"})
        return httpx.Response(200, json={"notes": [{"id": "not_1", "title": "Standup"}], "hasMore": False})

    client = granola.GranolaClient(_http=_mock_client(handler))
    res = client.check()
    assert res["verified_read"] is True
    assert res["sample_title"] == "Standup"
    assert waits == [1.0, 1.0]


def test_excessive_retry_after_stops_immediately(monkeypatch):
    from connectonion.useful_tools import granola

    monkeypatch.setenv("GRANOLA_API_KEY", "grn_test")
    monkeypatch.setattr(granola, "_sleep", lambda _s: (_ for _ in ()).throw(AssertionError("must not sleep")))

    def handler(_req):
        return httpx.Response(429, headers={"Retry-After": "120"}, json={})

    client = granola.GranolaClient(_http=_mock_client(handler))
    with pytest.raises(granola.GranolaError) as exc:
        client.check()
    assert exc.value.kind == "rate_limited"


def test_folder_pagination_separates_personal_from_shared_and_guards_loops(monkeypatch):
    from connectonion.useful_tools.granola import GranolaClient, GranolaError

    monkeypatch.setenv("GRANOLA_API_KEY", "grn_test")

    def handler(req):
        cur = req.url.params.get("cursor")
        if not cur:
            return httpx.Response(200, json={
                "folders": [
                    {"id": "fld_personal", "name": "1:1 Notes", "space_id": None, "parent_folder_id": None},
                    {"id": "fld_shared", "name": "Company Shared", "space_id": "spc_99", "parent_folder_id": None},
                ],
                "hasMore": True,
                "cursor": "c2",
            })
        return httpx.Response(200, json={
            "folders": [
                {"id": "fld_child", "name": "Direct Reports", "space_id": None, "parent_folder_id": "fld_personal"},
            ],
            "hasMore": False,
        })

    client = GranolaClient(_http=_mock_client(handler))
    listing = client.list_folders()
    assert [f["id"] for f in listing["personal"]] == ["fld_personal", "fld_child"]
    assert listing["shared_count"] == 1
    assert listing["personal"][0]["child_count"] == 1

    # Parent folder with children requires explicit include_children=True
    with pytest.raises(GranolaError) as need_children:
        client.resolve_personal_folder("fld_personal", include_children=False)
    assert need_children.value.kind == "scope"
    assert "--include-children" in need_children.value.next_step

    scope = client.resolve_personal_folder("fld_personal", include_children=True)
    assert scope["allowed_ids"] == {"fld_personal", "fld_child"}

    # Shared folder is always rejected
    with pytest.raises(GranolaError) as shared_err:
        client.resolve_personal_folder("fld_shared", include_children=False)
    assert shared_err.value.kind == "scope"


def test_parent_folder_with_shared_descendant_is_rejected(monkeypatch):
    from connectonion.useful_tools.granola import GranolaClient, GranolaError

    monkeypatch.setenv("GRANOLA_API_KEY", "grn_test")

    def handler(_req):
        return httpx.Response(200, json={
            "folders": [
                {"id": "fld_root", "name": "Root", "space_id": None, "parent_folder_id": None},
                {"id": "fld_sub_shared", "name": "Team Sub", "space_id": "spc_team", "parent_folder_id": "fld_root"},
            ],
            "hasMore": False,
        })

    client = GranolaClient(_http=_mock_client(handler))
    with pytest.raises(GranolaError) as exc:
        client.resolve_personal_folder("fld_root", include_children=True)
    assert exc.value.kind == "scope"


def test_get_note_strips_private_fields_and_enforces_personal_folder_scope(monkeypatch):
    from connectonion.useful_tools.granola import GranolaClient, GranolaError

    monkeypatch.setenv("GRANOLA_API_KEY", "grn_test")

    def handler(req):
        if req.url.path.endswith("/folders"):
            return httpx.Response(200, json={
                "folders": [
                    {"id": "fld_ok", "name": "My Meetings", "space_id": None, "parent_folder_id": None},
                    {"id": "fld_other", "name": "Other", "space_id": None, "parent_folder_id": None},
                ],
                "hasMore": False,
            })
        if req.url.path.endswith("/notes/not_good"):
            return httpx.Response(200, json={
                "id": "not_good",
                "title": "Design Review",
                "created_at": "2026-11-20T09:00:00Z",
                "updated_at": "2026-11-20T10:15:00Z",
                "web_url": "https://notes.granola.ai/d/not_good",
                "folder_id": "fld_ok",
                "space_id": None,
                "summary": {"markdown": "## Decisions\n- Ship CLI contract", "plain_text": "Decisions: Ship CLI contract"},
                "private_notes": "NEVER INCLUDE THIS RAW SCRATCHPAD",
                "attendees": [{"name": "Alice", "email": "alice@example.com"}],
                "transcript": [{"speaker": "Alice", "text": "verbatim words"}],
                "calendar_event": {"scheduled_start": "2026-11-20T09:00:00Z", "organizer": "alice@example.com"},
            })
        if req.url.path.endswith("/notes/not_shared"):
            return httpx.Response(200, json={
                "id": "not_shared",
                "title": "All Hands",
                "created_at": "2026-11-20T09:00:00Z",
                "updated_at": "2026-11-20T10:00:00Z",
                "space_id": "spc_company",
                "folder_id": "fld_shared",
                "summary_markdown": "Shared summary",
            })
        return httpx.Response(404, json={"error": "not found"})

    client = GranolaClient(_http=_mock_client(handler))
    note = client.get_note("not_good", folder_id="fld_ok")
    assert note["id"] == "not_good"
    assert "private_notes" not in note
    assert "attendees" not in note
    assert "transcript" not in note
    assert "organizer" not in note.get("calendar_event", {})

    # Out of selected folder -> refused
    with pytest.raises(GranolaError) as wrong_folder:
        client.get_note("not_good", folder_id="fld_other")
    assert wrong_folder.value.kind == "scope"

    # Shared-space note -> refused even without --folder
    with pytest.raises(GranolaError) as shared_note:
        client.get_note("not_shared")
    assert shared_note.value.kind == "scope"
