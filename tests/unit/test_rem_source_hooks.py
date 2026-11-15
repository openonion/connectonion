"""Selected-source contract with two fictional offline snapshot providers."""

from copy import deepcopy
from datetime import datetime, timezone
import importlib
import json
import sys
from types import ModuleType

import pytest

from connectonion.rem import source_hooks as hooks, source_versions
from connectonion.rem.files import RemError, state_path, write_json
from connectonion.rem.source import Batch


def selection(kind, **overrides):
    return {"kind": kind, "enabled": True, "consented": True,
            "folders": ["Work"], **overrides}


def save(root, **subscriptions):
    write_json(state_path(root, "subscriptions.json"), subscriptions)


@pytest.fixture
def providers(monkeypatch):
    events, loaded, modules = [], [], {}
    for kind in ("tasks", "notes"):
        module = ModuleType(f"fictional_{kind}_source")
        module.kind, module.skill = kind, f"rem-source-{kind}"
        modules[kind] = module
        monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(hooks, "MODULES", {kind: module.__name__ for kind, module in modules.items()})
    original = importlib.import_module

    def load(name):
        loaded.append(name)
        return original(name)

    monkeypatch.setattr(hooks.importlib, "import_module", load)
    for kind, module in modules.items():
        install(module, kind, events)
    return modules, events, loaded


def install(module, kind, events):
    def status(sub):
        events.append((kind, "status"))
        return {"folders": sub["folders"]}

    def fetch(root, sub):
        events.append((kind, "fetch", root, sub))
        return {"saved": 1}

    def collect(root, sub, progress, max_items, max_chars):
        events.append((kind, "collect", root, sub))
        progress.setdefault("cursor", {})["sequence"] = 3
        item = {"source": f"{kind}:Work/one@3", "text": "saved revision three",
                "timestamp": "2026-11-01T00:00:00Z", "reference": "saved:Work/one", "project": ""}
        if len(json.dumps(item)) > max_chars:
            raise RemError("Batch input limit is too small")
        return Batch([item][:max_items], progress)

    def gather(root, sub, handles, *, start, record):
        events.append((kind, "gather", root, sub, handles, start, record))
        return [{"text": "saved result", "source": f"{kind}:Work/one@3"}], [f"{kind}: searched"]

    def cited(root, sub, source_id):
        events.append((kind, "cited", root, sub))
        path = source_id.partition(":")[2].partition("@")[0]
        if path.split("/")[0] not in sub["folders"]:
            return None
        text = {f"{kind}:Work/one@1": "old words", f"{kind}:Work/one@3": "new words"}.get(source_id)
        return {"excerpt": text, "truncated": False} if text is not None else None

    module.status, module.fetch, module.collect, module.gather, module.cited = status, fetch, collect, gather, cited
    module.consent = lambda sub: "Read " + ", ".join(sub["folders"])
    module.record_of = lambda source_id: source_id.partition("@")[0] if "@" in source_id else None


def test_unselected_notebook_does_not_import_or_touch_registered_providers(tmp_path, providers):
    _, events, loaded = providers
    assert hooks.statuses(tmp_path) == {}
    assert hooks.consent_lines(tmp_path) == {}
    assert hooks.fetch(tmp_path) == {}
    assert hooks.gather(tmp_path, [], start=datetime.now(timezone.utc), record="projects/demo.md") == ([], [])
    assert hooks.cited(tmp_path, "notes:Work/one@1") is None
    assert hooks.record_of(tmp_path, "tasks:Work/one@3") is None
    assert hooks.superseded(tmp_path, {"notes:Work/one@1"}, {"notes:Work/one@3"}) == set()
    assert events == loaded == []
    assert not (tmp_path / ".state").exists()


def test_metadata_can_describe_selection_before_consent_without_acquisition(tmp_path, providers):
    _, events, loaded = providers
    save(tmp_path, notes=selection("notes", consented=False))
    assert hooks.statuses(tmp_path) == {"notes": {"folders": ["Work"]}}
    assert hooks.consent_lines(tmp_path) == {"notes": "Read Work"}
    assert events == [("notes", "status")]
    assert set(loaded) == {"fictional_notes_source"}


@pytest.mark.parametrize("flags", [{"enabled": False}, {"consented": False}, {"unsubscribed": True}])
def test_no_content_or_import_before_approval(tmp_path, providers, flags):
    _, events, loaded = providers
    save(tmp_path, notes=selection("notes", **flags))
    assert hooks.fetch(tmp_path) == {}
    assert hooks.cited(tmp_path, "notes:Work/one@1") is None
    assert hooks.gather(tmp_path, [], start=datetime.now(timezone.utc), record="people/demo.md") == ([], [])
    with pytest.raises(RemError, match="authorized"):
        hooks.collect(tmp_path, "notes", {}, 10, 1000)
    assert events == loaded == []


def test_lookup_loads_only_the_matching_selected_kind(tmp_path, providers):
    _, _, loaded = providers
    save(tmp_path, notes=selection("notes"), tasks=selection("tasks"))
    assert hooks.cited(tmp_path, "notes:Work/one@1")["excerpt"] == "old words"
    assert loaded == ["fictional_notes_source"]


def test_saved_version_scope_and_notebook_are_rechecked_on_every_call(tmp_path, providers):
    first, other = tmp_path / "first", tmp_path / "other"
    save(first, notes=selection("notes"))
    save(other, notes=selection("notes", folders=["Public"]))
    assert hooks.cited(first, "notes:Work/one@1")["excerpt"] == "old words"
    assert hooks.cited(other, "notes:Work/one@1") is None
    assert hooks.cited(first, "notes:Work/one@9") is None
    save(first, notes=selection("notes", folders=["Public"]))
    assert hooks.cited(first, "notes:Work/one@1") is None
    save(first, notes=selection("notes", consented=False))
    assert hooks.cited(first, "notes:Work/one@1") is None


def test_scoped_lookup_never_uses_a_global_registration(tmp_path, providers, monkeypatch):
    def forbidden(*args):
        pytest.fail("A global callback bypassed the notebook's selection")
    monkeypatch.setitem(source_versions.KINDS, "notes", source_versions.Kind(forbidden, forbidden))
    assert hooks.cited(tmp_path, "notes:Work/one@1") is None
    assert hooks.record_of(tmp_path, "notes:Work/one@1") is None


def test_shared_replacement_logic_keeps_unrelated_and_missing_evidence(tmp_path, providers):
    save(tmp_path, notes=selection("notes"), tasks=selection("tasks"))
    old = {"notes:Work/one@1", "tasks:Work/two@1", "gmail:abc"}
    new = {"notes:Work/one@3", "tasks:Work/three@3", "gmail:def"}
    assert hooks.superseded(tmp_path, old, new) == {"notes:Work/one@1"}
    # Identity replacement deliberately makes no chronological claim.
    assert hooks.superseded(tmp_path, {"notes:Work/one@3"}, {"notes:Work/one@1"}) == {"notes:Work/one@3"}


def test_matching_local_ids_from_different_kinds_do_not_hide_lost_evidence(tmp_path, providers, monkeypatch):
    modules, _, _ = providers
    save(tmp_path, notes=selection("notes"), tasks=selection("tasks"))
    for module in modules.values():
        monkeypatch.setattr(module, "record_of", lambda source_id: "42")
    assert hooks.superseded(tmp_path, {"tasks:42@1"}, {"notes:42@2"}) == set()


@pytest.mark.parametrize("replacement", [None, selection("tasks"), selection("notes", consented=False)])
def test_selection_changed_during_module_load_cannot_reach_snapshot(tmp_path, providers, monkeypatch, replacement):
    _, events, _ = providers
    save(tmp_path, chosen=selection("notes"))
    original = hooks.importlib.import_module
    def changed(name):
        save(tmp_path, **({"chosen": replacement} if replacement is not None else {}))
        return original(name)
    monkeypatch.setattr(hooks.importlib, "import_module", changed)
    assert hooks.cited(tmp_path, "notes:Work/one@1") is None
    assert events == []


def test_citation_checks_each_current_subscription_scope(tmp_path, providers):
    save(tmp_path, public=selection("notes", folders=["Public"]), work=selection("notes"))
    assert hooks.cited(tmp_path, "notes:Work/one@1")["excerpt"] == "old words"
    save(tmp_path, public=selection("notes", folders=["Public"]), work=selection("notes", consented=False))
    assert hooks.cited(tmp_path, "notes:Work/one@1") is None


def test_two_sources_share_offline_batches_without_committing_checkpoints(tmp_path, providers):
    _, events, _ = providers
    save(tmp_path, notes=selection("notes"), tasks=selection("tasks"))
    original = {"cursor": {"sequence": 1}}
    before = deepcopy(original)
    disk_before = {path.name: path.read_bytes() for path in (tmp_path / ".state").iterdir()}
    for name in ("tasks", "notes"):
        batch = hooks.collect(tmp_path, name, original, 1, 1000)
        assert batch.progress == {"cursor": {"sequence": 3}}
        assert len(batch.items) == 1
    assert original == before
    assert all(event[1] == "collect" and event[2] == tmp_path for event in events)
    assert {path.name: path.read_bytes() for path in (tmp_path / ".state").iterdir()} == disk_before


def test_failed_batch_leaves_original_progress_intact(tmp_path, providers):
    save(tmp_path, notes=selection("notes"))
    progress = {"cursor": {"sequence": 1}}
    with pytest.raises(RemError, match="too small"):
        hooks.collect(tmp_path, "notes", progress, 1, 1)
    assert progress == {"cursor": {"sequence": 1}}


def test_investigation_reports_only_selected_saved_sources(tmp_path, providers):
    _, events, loaded = providers
    save(tmp_path, notes=selection("notes"))
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    items, coverage = hooks.gather(tmp_path, ["Atlas"], start=start, record="projects/atlas.md")
    assert coverage == ["notes: searched"]
    assert items[0]["source"] == "notes:Work/one@3"
    assert events[0][-3:] == (["Atlas"], start, "projects/atlas.md")
    assert loaded == ["fictional_notes_source"]


def test_expected_fetch_failure_is_visible_and_other_sources_continue(tmp_path, providers, monkeypatch):
    modules, events, _ = providers
    save(tmp_path, tasks=selection("tasks"), notes=selection("notes"))
    def unavailable(*args):
        raise hooks.SourceUnavailable("Selected account is offline")
    monkeypatch.setattr(modules["tasks"], "fetch", unavailable)
    result = hooks.fetch(tmp_path)
    assert result["tasks"] == {"ok": False, "error": "Selected account is offline"}
    assert result["notes"] == {"ok": True, "result": {"saved": 1}}
    assert events[0][0:2] == ("notes", "fetch")


@pytest.mark.parametrize("error", [KeyError("schema"), TypeError("bug"), RemError("corrupt store")])
def test_programming_and_corruption_errors_propagate(tmp_path, providers, monkeypatch, error):
    modules, _, _ = providers
    save(tmp_path, notes=selection("notes"))
    def broken(*args):
        raise error
    monkeypatch.setattr(modules["notes"], "fetch", broken)
    monkeypatch.setattr(modules["notes"], "cited", broken)
    with pytest.raises(type(error)):
        hooks.fetch(tmp_path)
    with pytest.raises(type(error)):
        hooks.cited(tmp_path, "notes:Work/one@1")


def test_failed_import_can_be_retried(tmp_path, providers, monkeypatch):
    save(tmp_path, notes=selection("notes"))
    original = hooks.importlib.import_module
    def missing(name):
        raise ModuleNotFoundError(name)
    monkeypatch.setattr(hooks.importlib, "import_module", missing)
    with pytest.raises(ModuleNotFoundError):
        hooks.cited(tmp_path, "notes:Work/one@1")
    monkeypatch.setattr(hooks.importlib, "import_module", original)
    assert hooks.cited(tmp_path, "notes:Work/one@1")["excerpt"] == "old words"


@pytest.mark.parametrize("flag", ["enabled", "consented", "unsubscribed"])
def test_string_flags_fail_before_import(tmp_path, providers, flag):
    _, _, loaded = providers
    save(tmp_path, notes=selection("notes", **{flag: "false"}))
    with pytest.raises(RemError, match="flag"):
        hooks.fetch(tmp_path)
    assert loaded == []


def test_subscription_cannot_choose_an_import_path(tmp_path, providers):
    _, _, loaded = providers
    save(tmp_path, unknown=selection("arbitrary.module"))
    assert hooks.statuses(tmp_path) == {}
    assert loaded == []
