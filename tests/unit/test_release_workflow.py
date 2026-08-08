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
    assert 'git rev-parse --verify --quiet "refs/tags/$tag"' in RELEASE
    assert 'tagged_commit="$(git rev-list -n 1 "$tag")"' in RELEASE
    assert '"$tagged_commit" != "$GITHUB_SHA"' in RELEASE


def test_manual_release_is_only_a_retry_for_an_existing_reviewed_tag():
    assert "Release tag $tag does not exist" in RELEASE
    assert 'git rev-list -n 1 "$tag"' in RELEASE


def test_test_job_does_not_inherit_repository_secrets():
    assert "secrets: inherit" not in RELEASE


def test_release_uses_trusted_publishing_and_verifies_pypi():
    assert "id-token: write" in RELEASE
    assert "pypa/gh-action-pypi-publish@" in RELEASE
    assert "--no-cache-dir \"connectonion==$VERSION\"" in RELEASE
    assert "connectonion.__version__ == '$VERSION'" in RELEASE


def test_build_publish_and_finalize_permissions_are_separated():
    before_jobs = RELEASE.split("jobs:", 1)[0]
    tests_job = RELEASE.split("  tests:", 1)[1].split("  build:", 1)[0]
    build_job = RELEASE.split("  build:", 1)[1].split("  publish:", 1)[0]
    publish_job = RELEASE.split("  publish:", 1)[1].split("  finalize:", 1)[0]
    finalize_job = RELEASE.split("  finalize:", 1)[1]

    assert "contents: read" in before_jobs
    assert "contents: write" not in before_jobs
    assert "id-token: write" not in before_jobs
    assert "contents: read" in tests_job
    assert "contents: read" in build_job
    assert "contents: write" not in build_job
    assert "id-token: write" not in build_job
    assert "id-token: write" in publish_job
    assert "contents: write" not in publish_job
    assert "environment:" in publish_job
    assert "contents: write" in finalize_job
    assert "id-token: write" not in finalize_job


def test_only_the_current_pair_is_built_and_attached():
    assert "rm -rf dist" in RELEASE
    assert 'wheel="dist/connectonion-${VERSION}-py3-none-any.whl"' in RELEASE
    assert 'sdist="dist/connectonion-${VERSION}.tar.gz"' in RELEASE
    assert "verify_published_artifacts.py" in RELEASE
    assert 'wheel="published/connectonion-${VERSION}-py3-none-any.whl"' in RELEASE
    assert 'sdist="published/connectonion-${VERSION}.tar.gz"' in RELEASE
    assert "gh release create" in RELEASE


def test_announcements_cannot_fail_a_package_release():
    assert "Discord/LinkedIn integration" in RELEASE
    assert "discord.com/api/webhooks" not in RELEASE.lower()


def test_external_actions_are_pinned_to_immutable_commits():
    workflows = RELEASE + TESTS
    external_uses = [
        line.strip()
        for line in workflows.splitlines()
        if line.strip().startswith("uses:") and "uses: ./" not in line
    ]

    assert external_uses
    for line in external_uses:
        reference = line.split("@", 1)[1].split()[0]
        assert len(reference) == 40
        assert all(character in "0123456789abcdef" for character in reference)
