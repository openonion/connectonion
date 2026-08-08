"""Security-sensitive dependencies must not regress below patched releases."""

import re
from pathlib import Path

from packaging.version import Version


REPO = Path(__file__).resolve().parents[2]

PATCHED_LOCK_FLOORS = {
    "click": "8.3.3",
    "httplib2": "0.32.0",
    "idna": "3.15",
    "protobuf": "6.33.5",
    "pyasn1": "0.6.4",
    "pygments": "2.20.0",
    "pynacl": "1.6.2",
    "python-dotenv": "1.2.2",
    "requests": "2.33.0",
    "soupsieve": "2.8.4",
    "urllib3": "2.7.0",
}


def test_security_sensitive_dependency_floors_are_patched(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (REPO / "uv.lock").read_text(encoding="utf-8")
    locked = dict(re.findall(
        r'\[\[package\]\]\s*name = "([^"]+)"\s*version = "([^"]+)"',
        lockfile,
    ))

    assert '"python-dotenv>=1.2.2"' in pyproject
    assert '"PyNaCl>=1.6.2"' in pyproject
    assert '{ name = "python-dotenv", specifier = ">=1.2.2" }' in lockfile
    assert '{ name = "pynacl", specifier = ">=1.6.2" }' in lockfile
    for package, floor in PATCHED_LOCK_FLOORS.items():
        assert package in locked, f"{package} is missing from uv.lock"
        assert Version(locked[package]) >= Version(floor), (
            f"{package} {locked[package]} regressed below patched {floor}"
        )
