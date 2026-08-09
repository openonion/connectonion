"""Security-sensitive dependencies must not regress below patched releases."""

import re
from pathlib import Path

from packaging.version import Version

REPO = Path(__file__).resolve().parents[2]

PATCHED_FLOORS = {
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


def _locked_versions(lockfile: str) -> dict[str, str]:
    return dict(re.findall(
        r'\[\[package\]\]\s*name = "([^"]+)"\s*version = "([^"]+)"',
        lockfile,
    ))


def test_security_sensitive_dependency_floors_are_patched(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (REPO / "uv.lock").read_text(encoding="utf-8")
    locked = _locked_versions(lockfile)

    for package, floor in PATCHED_FLOORS.items():
        published_floor = re.search(
            rf'^\s*"{re.escape(package)}>={re.escape(floor)}",\s*$',
            pyproject,
            re.IGNORECASE | re.MULTILINE,
        )
        assert published_floor, (
            f"{package} metadata does not require the patched floor {floor}"
        )
        assert (
            f'{{ name = "{package}", specifier = ">={floor}" }}' in lockfile
        ), f"{package} floor is missing from uv.lock root metadata"
        assert package in locked, f"{package} is missing from uv.lock"
        assert Version(locked[package]) >= Version(floor), (
            f"{package} {locked[package]} regressed below patched {floor}"
        )


def test_pytest_dev_floor_is_patched(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    floor = "9.0.3"
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (REPO / "uv.lock").read_text(encoding="utf-8")

    assert re.search(
        rf'^\s*"pytest>={re.escape(floor)}",\s*$',
        pyproject,
        re.MULTILINE,
    ), f"pytest dev metadata does not require the patched floor {floor}"

    root_requirement = (
        f'{{ name = "pytest", marker = "extra == \'dev\'", '
        f'specifier = ">={floor}" }}'
    )
    assert lockfile.count(root_requirement) == 1, (
        "pytest's dev-only floor is missing from uv.lock root metadata"
    )

    locked = _locked_versions(lockfile)
    assert "pytest" in locked, "pytest is missing from uv.lock"
    assert Version(locked["pytest"]) >= Version(floor), (
        f"pytest {locked['pytest']} regressed below patched {floor}"
    )
