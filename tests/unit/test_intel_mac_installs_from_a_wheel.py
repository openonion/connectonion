"""A fresh install on an Intel Mac must not compile cryptography from source.

cryptography 49+ ships macOS wheels for arm64 only. On an Intel Mac pip picked
50.0.2's sdist and sat in "Preparing metadata (pyproject.toml): still running"
for over thirty minutes installing 1.9.2b3 (2026-10-11). 48.0.1 has a
universal2 wheel.
"""

try:
    import tomllib
except ImportError:  # Python 3.10; pytest itself depends on tomli there
    import tomli as tomllib
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.version import Version

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _cryptography(environment):
    deps = [Requirement(line) for line in tomllib.loads(PYPROJECT.read_text())["project"]["dependencies"]]
    return [dep for dep in deps if dep.name == "cryptography" and (dep.marker is None or dep.marker.evaluate(environment))]


def test_an_intel_mac_resolves_cryptography_with_a_wheel():
    intel = {**default_environment(), "sys_platform": "darwin", "platform_machine": "x86_64"}
    (dep,) = _cryptography(intel)
    assert not dep.specifier.contains(Version("49.0.0")) and dep.specifier.contains(Version("48.0.1"))


def test_other_platforms_keep_the_current_cryptography():
    for platform, machine in (("darwin", "arm64"), ("linux", "x86_64"), ("win32", "AMD64")):
        env = {**default_environment(), "sys_platform": platform, "platform_machine": machine}
        (dep,) = _cryptography(env)
        assert dep.specifier.contains(Version("50.0.2")), platform
