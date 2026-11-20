"""Capture actual CLI output against synthetic Graph routes; never use an account.

Run with development dependencies in an isolated HOME. The HTTP transport is
replaced before executing commands, including the legacy create demonstration.
Screenshots render the captured output; they are synthetic acceptance evidence,
not live Microsoft or model acceptance. Real-account evidence is a separate gate.
"""
import argparse
import json
import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests/unit"), str(ROOT / "scripts")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshots", action="store_true")
    args = parser.parse_args()
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    import httpx
    from pytest import MonkeyPatch
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from onenote_source_fixtures import BASE, DATA, graph
    from capture_186a2_release_cli import page
    from tempfile import TemporaryDirectory

    runner, captures = CliRunner(), {}
    os.environ["COLUMNS"] = "96"
    with MonkeyPatch.context() as patch, TemporaryDirectory() as work:
        patch.chdir(work)
        routes, calls = graph.__wrapped__(patch)
        patch.setenv("MICROSOFT_SCOPES", "Notes.ReadWrite User.Read")
        routes["/me/onenote/notebooks"]["value"][0]["sections"] = DATA["sections"]
        routes["/me/onenote/pages"] = {"value": DATA["pages"][:2]}
        get = httpx.request
        allow_create = False

        def transport(method, url, **kwargs):
            if method == "POST":
                assert allow_create and url == BASE + "/me/onenote/sections/section-fixture/pages"
                return httpx.Response(201, request=httpx.Request(method, url), json={"id": "synthetic-created-page"})
            return get(method, url, **kwargs)

        patch.setattr(httpx, "request", transport)

        def run(group, words, expected=0):
            result = runner.invoke(app, words, color=True)
            assert result.exit_code == expected, (words, result.output, result.exception)
            text = result.output.replace(str(Path(work)), "./fixture-work").replace(str(Path.home()), "~")
            assert "fixture-secret-token" not in text
            captures.setdefault(group, []).append((shlex.join(["co", *words]), text))
            return result

        commands = runner.invoke(app, ["commands"])
        assert commands.exit_code == 0
        captures["discovery"] = [("co commands (OneNote entries)", "\n".join(line for line in commands.output.splitlines() if "onenote" in line))]
        for words in [[], ["ls"], ["pages"], ["read"], ["create"], ["source"],
                      *[["source", name] for name in ("verify", "notebooks", "sections", "pages", "sync")]]:
            run("help", ["onenote", *words, "--help"])
        run("browsing", ["onenote"])
        run("browsing", ["onenote", "ls", "--ids"])
        run("browsing", ["onenote", "ls", "--json"])
        run("browsing", ["onenote", "pages", "section-fixture", "--ids"])
        run("browsing", ["onenote", "read", "1"])
        allow_create = True
        run("browsing", ["onenote", "create", "section-fixture", "Synthetic acceptance", "Fictional text only."])
        allow_create = False
        for words in [["verify"], ["notebooks"], ["sections", "nb-fixture"],
                      ["pages", "nb-fixture", "section-fixture"]]:
            run("source", ["onenote", "source", *words])
        sync = ["onenote", "source", "sync", "nb-fixture", "section-fixture", "page-good", "--output", "note-source"]
        run("imports", sync)
        run("imports", [*sync, "--full"])
        run("imports", [*sync, "--mode", "export", "--export-id", "snapshot-1"])
        run("errors", ["onenote", "source", "pages", "nb-fixture", "not-selected", "--json"], 1)
        run("errors", ["onenote", "source", "pages", "nb-fixture", "section-fixture", "--limit", "0", "--json"], 2)
        run("errors", [*sync, "--mode", "export", "--export-id", "snapshot-1", "--json"], 1)
        run("errors", [*sync, "page-outside", "--output", "partial-source", "--json"], 2)
        assert calls and all(call[0] == "GET" for call in calls)
    # An actual missing-authorization invocation, in this isolated HOME.
    run_missing = runner.invoke(app, ["onenote", "source", "verify", "--json"])
    assert run_missing.exit_code == 1
    captures["errors"].append(("co onenote source verify --json (no authorization)", run_missing.output))
    (destination / "transcript.json").write_text(json.dumps({"sample": "synthetic Graph; no live account or model", "groups": captures}, ensure_ascii=False, indent=2) + "\n")
    if args.screenshots:
        from patchright.sync_api import sync_playwright
        with sync_playwright() as play:
            browser = play.chromium.launch(channel="chrome")
            try:
                view = browser.new_page(viewport={"width": 1080, "height": 100}, device_scale_factor=1)
                for name, blocks in captures.items():
                    label = ("SYNTHETIC ACCEPTANCE — actual CLI output", "No live Microsoft account or model. HTTP transport replaced; create is simulated.\n")
                    view.set_content("<body style='margin:0;background:#1d1f21'>" + page("", [label, *blocks]) + "</body>")
                    view.screenshot(path=str(destination / f"{name}.png"), full_page=True)
            finally:
                browser.close()
    print(f"Captured {sum(map(len, captures.values()))} actual invocations/listings using synthetic Graph only.")


if __name__ == "__main__":
    main()
