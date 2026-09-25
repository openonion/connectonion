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

    def fake_run(argv, cwd, capture_output, text, timeout, env=None):
        calls.append(argv)
        import re
        from pathlib import Path
        path = Path(re.search(r'NEW file (.+?candidate.md)', argv[-1])[1])
        path.write_text(next(Path(cwd).glob('investigate-*/notebook/people/vern.md')).read_text())
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


def test_runner_codex_is_co_ai_delegating_to_codex_in_the_workspace_sandbox(tmp_path, co_ai):
    root = _notebook(tmp_path, "codex")
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    argv = co_ai[0]
    assert argv[1:3] == ["ai", "--json"]
    assert argv[3:9] == ["--harness", "codex", "--sandbox", "workspace-write",
                         "--model", read_config(root)["model"]]
    # The Skill is told the page's real path, extension included: an earlier
    # version cut the record at its first "." and pointed it at people/vern.
    assert argv[-1].startswith("/wiki-investigate ") and "/notebook/people/vern.md" in argv[-1]


# The whole command line before the prompt, pinned per executor. Investigation
# puts correspondents' mail and attachments in front of the model, and the same
# page is investigated unattended by the daily job `co wiki start` installs.
# Codex used to get danger-full-access and Claude bypassPermissions here, so
# anyone who could email the user could hand instructions to an agent with a
# shell, the network and the user's mailbox. Our code fetches the mail; the
# model only reads the material and writes candidate.md in its task directory.
PINNED = {
    "codex": ["ai", "--json", "--harness", "codex", "--sandbox", "workspace-write",
              "--model", "gpt-5.6-luna", "--timeout", "1200"],
    "claude-code": ["ai", "--json", "--harness", "claude-code", "--permission-mode", "acceptEdits",
                    "--model", "sonnet", "--timeout", "1200"],
}


def _pinned_notebook(tmp_path, runner):
    root = _notebook(tmp_path, runner)
    set_config(root, ["model", "gpt-5.6-luna" if runner == "codex" else "sonnet"])
    set_config(root, ["limits.timeout_seconds", "1200"])
    return root


@pytest.mark.parametrize("runner", sorted(PINNED))
def test_an_investigation_the_user_starts_runs_confined(tmp_path, co_ai, runner):
    root = _pinned_notebook(tmp_path, runner)
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    assert co_ai[0][1:-1] == PINNED[runner]


@pytest.mark.parametrize("runner", sorted(PINNED))
def test_the_scheduled_daily_investigation_runs_confined(tmp_path, co_ai, monkeypatch, runner):
    from connectonion.wiki.daily import run_daily
    monkeypatch.setattr("connectonion.wiki.service.mail_available", lambda kind: False)
    root = _pinned_notebook(tmp_path, runner)
    result = run_daily(root, scheduled=True,
                       maintain=lambda root, scheduled: {"outcome": "no_change"})
    assert result["run"]["outcome"] == "completed", result
    assert [argv[1:-1] for argv in co_ai] == [PINNED[runner]]


def test_runner_coai_is_co_ai_on_our_own_loop_and_its_own_default_model(tmp_path, co_ai):
    root = _notebook(tmp_path, "coai")
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    argv = co_ai[0]
    assert argv[1:3] == ["ai", "--json"] and argv[-1].startswith("/wiki-investigate ")
    assert argv[3:5] == ["--harness", "ours"]
    assert not {"--sandbox", "--model"} & set(argv)


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


def test_coding_search_continues_past_first_batch_and_matches_aliases(tmp_path, monkeypatch):
    from connectonion.wiki.source import Batch
    seen = []
    def collect(sub, cursor, *limits):
        seen.append(cursor)
        if not cursor:
            return Batch([{"text": "unrelated", "timestamp": "2026-09-01", "source": "codex:1"}], {"offset": 40})
        if cursor == {"offset": 40}:
            return Batch([{"text": "odi accepted the terms", "timestamp": "2026-09-02",
                           "source": "codex:2"}], {"offset": 80})
        return Batch([], cursor)
    monkeypatch.setattr(inv, "collect", collect)
    items, coverage = inv.gather("Ody Zhou", ["ody@example.org", "odi"], days=30, clients={},
                                subscriptions={"codex": {"kind": "codex", "root": str(tmp_path)}})
    assert [i["source"] for i in items] == ["codex:2"]
    assert seen == [{}, {"offset": 40}, {"offset": 80}]
    assert "2 messages" in next(line for line in coverage if line.startswith("codex"))


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


def test_a_person_s_mail_is_asked_of_the_server_not_found_by_listing_everything():
    """Listing the whole window took minutes per person and a busy week past the
    listing cap lost mail silently. With the person's addresses in hand, the
    mailbox is asked for exactly their mail, every address once."""
    class Searchable(Quiet):
        asked = []
        def list_between(self, s, e, n): raise AssertionError("listed the whole mailbox")
        def list_with(self, address, start, end):
            self.asked.append(address)
            return [{"id": f"{address}-1", "from": f"Vern <{address}>", "to": ["me@x.y"],
                     "subject": "Practice of Work", "date": "2026-07-21T00:00:00Z"}]
        def get_email_body(self, i): return "--- Email Body ---\nOne team of 4-6 works."

    box = Searchable()
    items, coverage = inv.gather("Vern Chan", ["vern.chan@unsw.edu.au", "vern@founders.unsw.edu.au", "Vern Chan"],
                                 days=90, clients={"outlook": box}, subscriptions={})
    assert box.asked == ["vern.chan@unsw.edu.au", "vern@founders.unsw.edu.au"]
    assert [i["text"].split("\n")[-1] for i in items] == ["One team of 4-6 works."] * 2
    assert "searched on the server" in coverage[0] and "2 matched" in coverage[0]


def test_a_mailbox_not_searched_is_named_in_coverage():
    _, coverage = inv.gather("Vern Chan", ["vern.chan@unsw.edu.au"], days=30, clients={"outlook": Quiet()},
                             subscriptions={"gmail": {"kind": "gmail", "unsubscribed": True}})
    assert "gmail: unsubscribed by the user; not searched" in coverage
    _, coverage = inv.gather("Vern Chan", ["vern.chan@unsw.edu.au"], days=30, clients={}, subscriptions={})
    assert any(line.startswith("outlook: not connected (co auth microsoft)") for line in coverage)


def test_a_model_the_login_cannot_run_is_named_with_the_fix(tmp_path, monkeypatch):
    """Codex 0.155 refuses Spark for ChatGPT logins at the first turn; the provider's
    JSON told nobody what to do next."""
    root = _notebook(tmp_path, "codex")
    refused = json.dumps({"outcome": "error", "error": 'turn failed: {"status":400,"error":{"message":'
                          '"The \'gpt-5.3-codex-spark\' model is not supported when using Codex with a ChatGPT account."}}'})
    monkeypatch.setattr("subprocess.run", lambda *a, **k: types.SimpleNamespace(stdout=refused, stderr="", returncode=1))
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/co")
    config = read_config(root)
    from connectonion.wiki.runner import RunFailed, run_task
    with pytest.raises(RunFailed, match="co wiki config set model gpt-6-luna"):
        run_task(root, "prompt", config, "investigate")


def test_a_listed_source_nobody_cites_is_dropped_not_a_reason_to_refuse_the_page(tmp_path, monkeypatch):
    """A real Ian Chan page was refused whole because its Sources listed the old
    page as [1] and no sentence cited it. The listing is harmless; the page was not."""
    from pathlib import Path
    from connectonion.wiki.files import Notebook

    def fake_run(argv, cwd, capture_output, text, timeout):
        import re
        path = Path(re.search(r'NEW file (.+?candidate.md)', argv[-1])[1])
        page = next(Path(cwd).glob('investigate-*/notebook/people/vern.md')).read_text()
        page = page.replace("## Who they are\n- Unknown — not investigated yet",
                            "## Who they are\n- Vern works at UNSW. [W1]", 1)
        page = page.replace("## Sources\n- (none yet)",
                            "## Sources\n- [1] Existing page people/vern.md, prior context only.\n"
                            "- [W1] https://www.unsw.edu.au/staff/vern-chan, observed 2026-09-23.", 1)
        path.write_text(page)
        return types.SimpleNamespace(stdout=json.dumps({"outcome": "natural", "result": "ok", "usage": None}),
                                     stderr="", returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/co")
    root = _notebook(tmp_path, "codex")
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    page = Notebook(root).read("people/vern.md")
    assert "Vern works at UNSW. [W1]" in page
    assert "[W1] https://www.unsw.edu.au/staff/vern-chan" in page and "[1] Existing page" not in page


def test_a_message_read_through_a_digest_can_still_be_cited_by_its_own_id():
    """Ody Zhou's 201 mails were digested first, and the page cited the real
    message ids the digests named -- all refused, because the digest item kept
    only "gmail +4". Everyone with enough mail to need a digest was refused."""
    from connectonion.wiki.extract import extraction_item
    from connectonion.wiki.page_review import validate
    from connectonion.wiki.files import Notebook
    import tempfile
    from pathlib import Path
    root = Path(tempfile.mkdtemp()) / "wiki"
    prepare(root)
    notebook = Notebook(root)
    notebook.stub_person("people/ody.md", "Ody Zhou", ["ody"], email="zhouodywork@gmail.com")
    original = notebook.read("people/ody.md")
    chunk = [{"source": "gmail:3a7a430fcee5", "timestamp": "2026-08-01T00:00:00+00:00", "text": "a"},
             {"source": "gmail:db0abd133958:Draft_v8.docx", "timestamp": "2026-08-02T00:00:00+00:00", "text": "b"}]
    items = [extraction_item("Ody drafted v8 of the Emma agreement (gmail:db0abd133958).", chunk)]
    candidate = original.replace("## Who they are\n- Unknown — not investigated yet",
                                 "## Who they are\n- Ody drafts contracts. [1]", 1).replace(
        "## Sources\n- (none yet)",
        "## Sources\n- [1] `gmail:3a7a430fcee5`, `gmail:db0abd133958:Draft_v8.docx`, observed 2026-09-23.", 1)
    assert validate("people/ody.md", candidate, original, items) == []
    forged = candidate.replace("gmail:3a7a430fcee5", "gmail:ffffffffffff").replace(
        "`gmail:db0abd133958:Draft_v8.docx`, ", "")
    assert validate("people/ody.md", forged, original, items)          # an id no digest read is still refused
    session = [{"source": "claude-code:3994b2ee-ff35:81", "timestamp": "2026-08-30T00:00:00+00:00", "text": "c"},
               {"source": "gmail:c74572cd7d0e", "timestamp": "2026-08-31T00:00:00+00:00", "text": "d"}]
    items.append(extraction_item("Dora reviewed the deck.", session))
    whole = original.replace("## Who they are\n- Unknown — not investigated yet",
                             "## Who they are\n- Dora reviews decks. [1]", 1).replace(
        "## Sources\n- (none yet)", "## Sources\n- [1] `claude-code:3994b2ee-ff35`, observed 2026-08-30.", 1)
    assert validate("people/ody.md", whole, original, items) == []     # the whole session it came from


def test_the_owners_own_address_never_lands_on_someone_elses_page(tmp_path, monkeypatch):
    """Dora's page listed xietianle@outlook.com -- the user's own Outlook -- as her
    email and handle, from mail the two of them exchanged. The owner's addresses
    are known; they are removed mechanically, the rest of the page is kept."""
    from pathlib import Path
    from connectonion.wiki.files import Notebook, state_path, write_json

    def fake_run(argv, cwd, capture_output, text, timeout):
        import re
        path = Path(re.search(r'NEW file (.+?candidate.md)', argv[-1])[1])
        page = next(Path(cwd).glob('investigate-*/notebook/people/vern.md')).read_text()
        page = re.sub(r'^- Email: .*$', '- Email: vern.chan@unsw.edu.au; me@outlook.com', page, count=1, flags=re.M)
        page = re.sub(r'^- Handles: .*$', '- Handles: me@outlook.com', page, count=1, flags=re.M)
        page = page.replace("## Who they are\n- Unknown — not investigated yet",
                            "## Who they are\n- Vern works at UNSW. [W1]", 1).replace(
            "## Sources\n- (none yet)", "## Sources\n- [W1] https://www.unsw.edu.au/staff/vern-chan, observed 2026-09-23.", 1)
        path.write_text(page)
        return types.SimpleNamespace(stdout=json.dumps({"outcome": "natural", "result": "ok", "usage": None}),
                                     stderr="", returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/co")
    root = _notebook(tmp_path, "codex")
    write_json(state_path(root, "map.json"), {"owner": {"record": "people/me.md", "addresses": ["me@outlook.com"]}})
    inv.investigate(root, "people/vern.md", "Vern Chan", ["vern"], days=7,
                    clients={"outlook": Quiet()}, subscriptions={})
    page = Notebook(root).read("people/vern.md")
    assert "me@outlook.com" not in page
    assert "- Email: vern.chan@unsw.edu.au" in page and "- Handles: Unknown" in page


def test_the_owners_page_reads_what_the_owner_sent_from_every_address():
    """`investigate me` passes all the owner's addresses. A mailbox knows only its
    own login, so the others were searched for as if they were other people and
    the first real run found 6 of about 150 sent mails."""
    class Box:
        def my_addresses(self): return {"me@outlook.com"}
        def list_with(self, *a, **k): raise AssertionError("the owner is not a correspondent to search for")
        def list_between(self, start, end, n):
            return [{"id": "a", "from": "me@outlook.com", "to": ["x@y.z"], "date": start, "subject": "s"},
                    {"id": "b", "from": "Me <me@mail.example.org>", "to": ["x@y.z"], "date": start, "subject": "s"},
                    {"id": "c", "from": "x@y.z", "to": ["me@outlook.com"], "date": start, "subject": "s"}]
        def get_email_body(self, i): return f"body {i}"
    items, coverage = inv.gather("Me", ["me@outlook.com", "me@mail.example.org"], days=7,
                                 clients={"outlook": Box()}, subscriptions={}, sent_only=True)
    assert sorted(i["text"] for i in items) == ["body a", "body b"]          # both addresses, only what was sent
    assert "kept the owner's own sent mail" in coverage[0]


def test_a_mailbox_left_out_on_purpose_says_why_not_that_it_is_disconnected():
    """A project page skips mail by design; its coverage said "not connected (co auth
    microsoft)", which sends a user to log in again for nothing."""
    items, coverage = inv.gather("Aurora", ["/work/aurora"], days=7, clients={}, subscriptions={},
                                 mail_skipped="not read for a project page; name its mail with --handle")
    assert "outlook: not read for a project page; name its mail with --handle; not searched" in coverage
    assert not any("co auth" in line for line in coverage)
