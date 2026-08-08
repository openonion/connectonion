"""Security-sensitive dependencies must not regress below patched releases."""

from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_security_sensitive_dependency_floors_are_patched(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (REPO / "uv.lock").read_text(encoding="utf-8")

    assert '"python-dotenv>=1.2.2"' in pyproject
    assert '"PyNaCl>=1.6.2"' in pyproject
    assert 'name = "python-dotenv"\nversion = "1.2.2"' in lockfile
    assert 'name = "pynacl"\nversion = "1.6.2"' in lockfile
    assert '{ name = "python-dotenv", specifier = ">=1.2.2" }' in lockfile
    assert '{ name = "pynacl", specifier = ">=1.6.2" }' in lockfile
