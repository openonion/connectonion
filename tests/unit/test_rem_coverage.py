"""REM shows, per source, how much of it can be read, so a gap is seen without the owner noticing it (#3353)."""
from connectonion.rem import coverage as rem_coverage
from connectonion.useful_tools import wechat
from tests.unit.test_wechat_coverage import _storage


def test_wechat_coverage_names_the_gap_and_its_fix(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch, keyed=1, unkeyed=10)
    monkeypatch.setattr(wechat, "db_storage_in_use", lambda: storage)
    found = rem_coverage.source_coverage("wechat", {"kind": "wechat", "enabled": True})
    assert (found["found"], found["read"], found["missing_keys"]) == (11, 1, 10)
    assert "co wechat key capture" in found["line"]
    assert rem_coverage.gaps({"wechat": {"kind": "wechat", "enabled": True}}) == [found]


def test_an_unreadable_wechat_folder_is_a_gap_too(monkeypatch):
    monkeypatch.setattr(wechat, "db_storage_in_use", lambda: None)
    found = rem_coverage.source_coverage("wechat", {"kind": "wechat", "enabled": True})
    assert found["skipped"] and "co wechat doctor" in found["line"]


def test_disabled_and_unmeasured_sources_report_nothing():
    assert rem_coverage.source_coverage("wechat", {"kind": "wechat", "enabled": False}) is None
    assert rem_coverage.source_coverage("gmail", {"kind": "gmail", "enabled": True}) is None


def test_status_shows_the_gap_under_the_source_row(tmp_path, monkeypatch):
    from connectonion.cli.commands import rem_status
    from connectonion.rem import service
    storage = _storage(tmp_path, monkeypatch, keyed=1, unkeyed=2)
    monkeypatch.setattr(wechat, "db_storage_in_use", lambda: storage)
    monkeypatch.setattr(service, "subscriptions", lambda root: {"wechat": {"kind": "wechat", "enabled": True, "consented": True}})
    root = tmp_path / "rem"
    (root / ".state").mkdir(parents=True)
    rows = "\n".join(rem_status._sources_mapped(root))
    assert "缺 2" in rows and "co wechat key capture" in rows


def test_too_few_friends_with_chats_is_a_gap_with_the_phone_fix(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch, keyed=1, unkeyed=0)
    monkeypatch.setattr(wechat, "db_storage_in_use", lambda: storage)
    monkeypatch.setattr(wechat, "text_coverage", lambda db: {"friends": 1659, "with_chats": 25, "missing": 1634})
    found = rem_coverage.source_coverage("wechat", {"kind": "wechat", "enabled": True})
    assert found["skipped"] and "迁移到电脑" in found["skipped"][-1]["fix"]


def test_the_night_stores_the_gaps_for_today(tmp_path, monkeypatch):
    storage = _storage(tmp_path, monkeypatch, keyed=1, unkeyed=3)
    monkeypatch.setattr(wechat, "db_storage_in_use", lambda: storage)
    root = tmp_path / "rem"
    (root / ".state").mkdir(parents=True)
    rem_coverage.record(root, {"wechat": {"kind": "wechat", "enabled": True}})
    gap, = rem_coverage.stored(root)
    assert gap["missing_keys"] == 3 and gap["fix"] == "co wechat key capture"
    assert "缺 3" in gap["line"] and "missing a key" in gap["line_en"]
    rem_coverage.record(root, {"wechat": {"kind": "wechat", "enabled": False}})
    assert rem_coverage.stored(root) == []  # a fixed or removed source clears the line
