"""Both runners are co ai; the runner setting only picks which harness answers."""

import json
import types

import pytest

from connectonion.wiki import investigate as inv
from connectonion.wiki.config import prepare, read_config, set_config


class Quiet:
    def my_addresses(self): return {"me@x.y"}
    def list_between(self, s, e, n): return []
    def get_email_body(self, i): return ""


@pytest.fixture
def co_ai(monkeypatch):
    """A `co` that answers at once and remembers how it was called."""
    calls = []

    def fake_run(argv, cwd, capture_output, text, timeout):
        calls.append(argv)
        return types.SimpleNamespace(stdout=json.dumps({"outcome": "natural", "result": "ok", "usage": None}),
                                     stderr="", returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/co")
    return calls


def _notebook(tmp_path, runner):
    root = tmp_path / "wiki"; prepare(root); set_config(root, ["runner", runner])
    inv.Notebook(root).stub_person("people/vern.md", "Vern Chan", ["vern"], email="vern.chan@unsw.edu.au")
    return root


def test_runner_codex_is_co_ai_delegating_to_codex_with_the_full_access_sandbox(tmp_path, co_ai):
    """Investigating means running co outlook / co gmail / co browser inside the
    thread, and every one of them needs the network a read-only thread lacks."""
    root = _notebook(tmp_path, "codex")
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    argv = co_ai[0]
    assert argv[1:3] == ["ai", "--json"]
    assert argv[3:9] == ["--harness", "codex", "--sandbox", "danger-full-access",
                         "--model", read_config(root)["model"]]
    # The Skill is told the page's real path, extension included: an earlier
    # version cut the record at its first "." and pointed it at people/vern.
    assert argv[-1].startswith("/wiki-investigate ") and str(root / "people/vern.md") in argv[-1]


def test_runner_coai_is_co_ai_on_our_own_loop_and_its_own_default_model(tmp_path, co_ai):
    root = _notebook(tmp_path, "coai")
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    argv = co_ai[0]
    assert argv[1:3] == ["ai", "--json"] and argv[-1].startswith("/wiki-investigate ")
    assert not {"--harness", "--sandbox", "--model"} & set(argv)


def test_either_harness_records_that_the_web_was_searched(tmp_path, co_ai):
    """The status line names what was reachable; both harnesses can open the web."""
    from connectonion.wiki.files import Notebook
    for runner in ("codex", "coai"):
        root = _notebook(tmp_path / runner, runner)
        inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                        clients={"outlook": Quiet()}, subscriptions={})
        status = [l for l in Notebook(root).read("people/vern.md").splitlines() if l.startswith("Investigation:")][0]
        assert "web" in status and "outlook" in status, (runner, status)
