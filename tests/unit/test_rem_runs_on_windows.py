"""co rem on a Windows PC: found on the first real run, on a Windows 11 box."""

import importlib
import sys
import types

config = importlib.import_module("connectonion.rem.config")


def test_windows_reads_its_timezone_from_the_registry_through_tzlocal(monkeypatch):
    # Windows has no /etc/localtime: co rem init stopped at "Set schedule.timezone
    # to a valid IANA timezone" on every Windows PC.
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(config, "os", types.SimpleNamespace(name="nt", environ={}))
    monkeypatch.setitem(sys.modules, "tzlocal",
                        types.SimpleNamespace(get_localzone_name=lambda: "Pacific/Chatham"))
    assert config.local_timezone() == "Pacific/Chatham"


def test_tz_still_wins_on_windows(monkeypatch):
    monkeypatch.setattr(config, "os", types.SimpleNamespace(name="nt", environ={"TZ": "Europe/Oslo"}))
    assert config.local_timezone() == "Europe/Oslo"
