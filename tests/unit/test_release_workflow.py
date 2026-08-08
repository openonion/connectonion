"""The release path is automated, gated, and separate from announcements."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RELEASE = (ROOT / ".github/workflows/release.yml").read_text()
TESTS = (ROOT / ".github/workflows/tests.yml").read_text()


def test_release_reuses_the_full_test_workflow():
    assert "workflow_call:" in TESTS
    assert "uses: ./.github/workflows/tests.yml" in RELEASE
    assert "needs: tests" in RELEASE


def test_tag_and_emergency_manual_release_paths_exist():
    assert 'tags:\n      - "v*"' in RELEASE
    assert "workflow_dispatch:" in RELEASE
    assert "MANUAL_VERSION" in RELEASE


def test_release_uses_trusted_publishing_and_verifies_pypi():
    assert "id-token: write" in RELEASE
    assert "pypa/gh-action-pypi-publish@release/v1" in RELEASE
    assert "--no-cache-dir \"connectonion==$VERSION\"" in RELEASE
    assert "connectonion.__version__ == '$VERSION'" in RELEASE


def test_only_the_current_pair_is_built_and_attached():
    assert "rm -rf dist" in RELEASE
    assert 'wheel="dist/connectonion-${VERSION}-py3-none-any.whl"' in RELEASE
    assert 'sdist="dist/connectonion-${VERSION}.tar.gz"' in RELEASE
    assert "gh release create" in RELEASE


def test_announcements_cannot_fail_a_package_release():
    assert "Discord/LinkedIn integration" in RELEASE
    assert "discord.com/api/webhooks" not in RELEASE.lower()
