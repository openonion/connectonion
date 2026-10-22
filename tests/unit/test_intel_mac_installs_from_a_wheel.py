"""Platform-specific wheel preferences must not retain vulnerable cryptography.

Upstream 50.x has no Intel macOS wheel. Security takes precedence over the
former <49 pin; Intel builds need the documented native build dependencies.
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


def test_an_intel_mac_does_not_retain_vulnerable_cryptography():
    intel = {**default_environment(), "sys_platform": "darwin", "platform_machine": "x86_64"}
    (dep,) = _cryptography(intel)
    assert not dep.specifier.contains(Version("48.0.1"))
    assert not dep.specifier.contains(Version("49.0.0"))
    assert dep.specifier.contains(Version("50.0.2"))


def test_other_platforms_keep_the_current_cryptography():
    for platform, machine in (("darwin", "arm64"), ("linux", "x86_64"), ("win32", "AMD64")):
        env = {**default_environment(), "sys_platform": platform, "platform_machine": machine}
        (dep,) = _cryptography(env)
        assert dep.specifier.contains(Version("50.0.2")), platform
