"""Security-sensitive dependencies must not regress below patched releases."""

from pathlib import Path


def test_security_sensitive_dependency_floors_are_patched():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert '"python-dotenv>=1.2.2"' in pyproject
    assert '"PyNaCl>=1.6.2"' in pyproject
