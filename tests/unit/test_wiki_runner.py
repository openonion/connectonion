"""The native adapter exposes file tools, not a second semantic merge engine."""


import pytest

from connectonion.wiki.config import default_config, prepare
from connectonion.wiki.files import Notebook, WikiError
from connectonion.wiki.runner import (
    FileTools,
    WikiServer,
    maintenance_instructions,
    thread_parameters,
    verify_native_config,
)


def test_dynamic_file_tools_write_read_and_reorganize(tmp_path):
    prepare(tmp_path)
    tools = FileTools(Notebook(tmp_path), 10000)
    assert tools.call("wiki_write", {"path": "notes/a.md", "content": "# First"})["changed"]
    assert tools.call("wiki_read", {"path": "notes/a.md"}) == "# First"
    tools.call("wiki_write", {"path": "decisions/a.md", "content": "# First"})
    tools.call("wiki_delete", {"path": "notes/a.md"})
    assert tools.call("wiki_list", {}) == ["decisions/a.md"]
    assert tools.changed == {"notes/a.md", "decisions/a.md"}


def test_unknown_tools_and_state_writes_are_rejected(tmp_path):
    prepare(tmp_path)
    tools = FileTools(Notebook(tmp_path), 1000)
    for name, args in [("exec", {"command": "anything"}),
                       ("wiki_write", {"path": ".state/config.md", "content": "bad"})]:
        with pytest.raises(WikiError):
            tools.call(name, args)


def test_context_reads_share_a_budget(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).write("notes/a.md", "x" * 200)
    tools = FileTools(Notebook(tmp_path), 100)
    with pytest.raises(WikiError, match="context"):
        tools.call("wiki_read", {"path": "notes/a.md"})


def test_thread_is_ephemeral_and_has_no_execution_environment(tmp_path):
    params = thread_parameters(str(tmp_path), default_config())
    assert params["environments"] == []
    assert params["sandbox"] == "read-only"
    assert params["approvalPolicy"] == "never"
    assert params["ephemeral"] is True
    assert params["allowProviderModelFallback"] is False
    assert params["model"] == "gpt-5.3-codex-spark"
    assert params["baseInstructions"] == maintenance_instructions()
    assert {t["name"] for t in params["dynamicTools"]} == {
        "wiki_list", "wiki_search", "wiki_read", "wiki_write", "wiki_delete"}


def test_usage_notifications_replace_cumulative_counts_not_sum(tmp_path):
    server = WikiServer(["fake"], str(tmp_path), FileTools(Notebook(tmp_path), 1000), {})
    usage = {"inputTokens": 20, "outputTokens": 5, "cachedInputTokens": 10}
    for _ in range(2):
        server._handle_notification("thread/tokenUsage/updated", {
            "threadId": "thread-1", "tokenUsage": {"total": usage}})
    assert server.usage == {"input_tokens": 20, "output_tokens": 5, "cached_input_tokens": 10}


def test_unsupported_server_request_does_not_execute(tmp_path, monkeypatch):
    prepare(tmp_path)
    server = WikiServer(["fake"], str(tmp_path), FileTools(Notebook(tmp_path), 1000), {})
    sent = []
    monkeypatch.setattr(server, "_send", sent.append)
    server._handle_server_request(1, "item/tool/call", {
        "tool": "wiki_write", "arguments": {"path": "../escape.md", "content": "bad"}})
    assert sent[0]["result"]["success"] is False
    assert server.file_operation_failed is False and server.refused == 1
    server._handle_server_request(2, "item/commandExecution/requestApproval", {})
    assert sent[-1]["result"]["decision"] in ("decline", "cancel")


def test_context_limit_does_not_report_success_after_failed_read(tmp_path, monkeypatch):
    prepare(tmp_path)
    Notebook(tmp_path).write("notes/long.md", "x" * 300)
    server = WikiServer(["fake"], str(tmp_path), FileTools(Notebook(tmp_path), 100), {})
    sent = []
    monkeypatch.setattr(server, "_send", sent.append)
    server._handle_server_request(1, "item/tool/call", {
        "tool": "wiki_read", "arguments": {"path": "notes/long.md"}})
    assert server.file_operation_failed is False and server.refused == 1
    assert sent[0]["result"]["success"] is False


def test_empty_mcp_override_is_not_assumed_to_clear_inherited_servers():
    # Measured on 0.147.0: -c mcp_servers={} retains inherited server entries.
    with pytest.raises(WikiError, match="MCP"):
        verify_native_config({"mcp_servers": {"inherited": {"command": "do-not-run"}}})


def test_native_config_rejects_unknown_or_active_feature_surfaces():
    for config in ({}, {"features": {"shell_tool": True}, "mcp_servers": {}}):
        with pytest.raises(WikiError):
            verify_native_config(config)


def test_refused_file_operation_is_reported_but_does_not_fail_the_run(tmp_path, monkeypatch):
    """A refusal is the boundary working; the model is told and continues. Failing the
    whole run here would re-feed the same hostile message every pass, forever."""
    prepare(tmp_path)
    server = WikiServer(["fake"], str(tmp_path), FileTools(Notebook(tmp_path), 1000), {})
    sent = []
    monkeypatch.setattr(server, "_send", sent.append)
    server._handle_server_request(1, "item/tool/call", {
        "tool": "wiki_write", "arguments": {"path": ".state/progress.json", "content": "{}"}})
    assert sent[0]["result"]["success"] is False
    assert server.file_operation_failed is False
    assert server.refused == 1
    assert server.refusals == ["wiki_write: Hidden paths and traversal are not notebook content"]


def test_disk_failure_still_fails_the_run(tmp_path, monkeypatch):
    prepare(tmp_path)
    tools = FileTools(Notebook(tmp_path), 1000)
    monkeypatch.setattr(tools.notebook, "write", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    server = WikiServer(["fake"], str(tmp_path), tools, {})
    monkeypatch.setattr(server, "_send", lambda m: None)
    server._handle_server_request(1, "item/tool/call", {
        "tool": "wiki_write", "arguments": {"path": "notes/a.md", "content": "x"}})
    assert server.file_operation_failed is True


def test_search_tool_finds_existing_pages_without_reading_them_all(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).write("people/alice-chen.md", "# Alice Chen\nPrefers email.")
    Notebook(tmp_path).write("people/bob.md", "# Bob\n")
    tools = FileTools(Notebook(tmp_path), 10000)
    found = tools.call("wiki_search", {"query": "alice"})
    assert [hit["record"] for hit in found] == ["people/alice-chen.md"]
    assert {t["name"] for t in thread_parameters(str(tmp_path), default_config())["dynamicTools"]} >= {"wiki_search"}
