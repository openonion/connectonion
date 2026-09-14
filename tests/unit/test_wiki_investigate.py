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
    root = tmp_path / "wiki"
    prepare(root)
    set_config(root, ["runner", runner])
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


def test_the_status_line_names_the_sources_searched_and_does_not_claim_the_web(tmp_path, co_ai):
    """Whether the web was reached is the Skill's to report on the page: a real
    run had `co browser` fail inside the thread while the line still said web."""
    from connectonion.wiki.files import Notebook
    for runner in ("codex", "coai"):
        root = _notebook(tmp_path / runner, runner)
        inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                        clients={"outlook": Quiet()}, subscriptions={})
        status = next(line for line in Notebook(root).read("people/vern.md").splitlines()
                      if line.startswith("Investigation:"))
        assert "outlook" in status and "web" not in status, (runner, status)


def test_oversized_attachment_is_split_without_losing_text_or_sources():
    config = {"limits": {"extract_items_per_batch": 40, "extract_chars_per_batch": 500}}
    items = [{"text": '合同条款\\\"\n' * 600, "source": "gmail:contract.pdf",
              "timestamp": "2026-09-01T00:00:00Z", "role": "attachment"},
             {"text": "Latest signed terms", "source": "outlook:signed",
              "timestamp": "2026-09-02T00:00:00Z", "role": "other"}]
    seen = []

    def extract(chunk, config, kind):
        assert len(json.dumps(chunk, ensure_ascii=False)) <= 500
        seen.extend(chunk)
        return {"notes": "A sourced digest", "usage": {"input_tokens": 10}}

    digests, usage = inv.digest_in_chunks(items, config, extract)
    for original in items:
        assert "".join(i["text"] for i in seen if i["source"] == original["source"]) == original["text"]
    assert seen[-1]["source"] == "outlook:signed"
    assert usage["input_tokens"] == len(digests) * 10


def test_chunk_limit_includes_json_framing():
    item = {"text": "x", "source": "gmail:1", "timestamp": "2026-09-01T00:00:00Z"}
    limit = len(json.dumps([item, item], ensure_ascii=False)) - 1
    config = {"limits": {"extract_items_per_batch": 40, "extract_chars_per_batch": limit}}
    batches = []

    def extract(chunk, config, kind):
        batches.append(chunk)
        return {"notes": "Notes"}

    inv.digest_in_chunks([item, item], config, extract)
    assert len(batches) == 2
    assert all(len(json.dumps(c, ensure_ascii=False)) <= limit for c in batches)


def test_owner_over_input_limit_reaches_writer_with_every_digest_and_existing_page(tmp_path, monkeypatch):
    root = _notebook(tmp_path, "codex")
    config = read_config(root)
    original = inv.Notebook(root).read("people/vern.md")
    items = [{"text": f"message {i}: " + "x" * 30_000, "source": f"outlook:{i}",
              "timestamp": f"2026-09-{i + 1:02d}T00:00:00Z"} for i in range(12)]
    assert len(json.dumps(items)) > config["limits"]["input_chars_per_batch"]
    monkeypatch.setattr(inv, "gather", lambda *a, **kw: (items, ["outlook: 12 matched"]))
    seen = []

    def extract(chunk, config, kind):
        seen.extend(chunk)
        return {"notes": "\n".join(i["source"] for i in chunk), "usage": {"input_tokens": 10}}

    def write(notebook, material, config, **kw):
        assert original in material[0]["text"]
        assert all(i["role"] == "extract" for i in material[2:])
        text = "\n".join(i["text"] for i in material[2:])
        assert all(i["source"] in text for i in items)
        assert len(json.dumps(material)) < config["limits"]["input_chars_per_batch"]
        page = notebook.path("people/vern.md")
        page.write_text(original.replace("- Role: Unknown", "- Role: Account owner [1]"))
        return {"changed": ["people/vern.md"], "usage": {"input_tokens": 5}}

    out = inv.investigate(root, "people/vern.md", "Vern", ["me@x.y"], days=7,
                          clients={}, subscriptions={}, extractor=extract, runner=write)
    assert seen == items
    assert out["changed"] == ["people/vern.md"]
    assert out["usage"]["input_tokens"] == 10 * out["items"] + 5
    assert "investigated" in inv.Notebook(root).read("people/vern.md")


def test_impossible_chunk_limit_fails_before_spending_tokens():
    config = {"limits": {"extract_items_per_batch": 40, "extract_chars_per_batch": 5}}
    items = [{"text": "x", "source": "outlook:1", "timestamp": "2026-09-01T00:00:00Z"}]
    with pytest.raises(inv.WikiError, match="increase limits.extract_chars_per_batch"):
        inv.digest_in_chunks(items, config, lambda *a: pytest.fail("must validate before calling the model"))


@pytest.mark.parametrize("stdout,returncode", [
    ("", 1), ("not JSON", 0), ("{}", 0),
    (json.dumps({"outcome": "natural", "result": "ok"}), 1),
    (json.dumps({"outcome": "error", "error": "model unavailable"}), 0),
])
def test_failed_command_never_marks_owner_investigated(tmp_path, monkeypatch, co_ai, stdout, returncode):
    root = _notebook(tmp_path, "codex")
    before = inv.Notebook(root).read("people/vern.md")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: types.SimpleNamespace(
        stdout=stdout, stderr="command failed", returncode=returncode))
    with pytest.raises(inv.WikiError, match="co ai"):
        inv.investigate(root, "people/vern.md", "Vern", ["vern"], days=7,
                        clients={}, subscriptions={})
    assert inv.Notebook(root).read("people/vern.md") == before


def test_timeout_preserves_unfinished_page(tmp_path, monkeypatch, co_ai):
    import subprocess
    root = _notebook(tmp_path, "codex")
    before = inv.Notebook(root).read("people/vern.md")

    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired("co ai", 900)

    monkeypatch.setattr("subprocess.run", timeout)
    with pytest.raises(inv.WikiError, match="timed out"):
        inv.investigate(root, "people/vern.md", "Vern", ["vern"], days=7,
                        clients={}, subscriptions={})
    assert inv.Notebook(root).read("people/vern.md") == before
