"""What the person typed in Codex Desktop, told apart from what the client added (#1978).

Codex Desktop puts every message in the user slot under
`internal_chat_message_metadata_passthrough`, typed or injected, so the typed-message
reader that took the key as "injected" dropped 12,285 of the owner's 13,065 user-slot
messages over 90 days -- all of Desktop. What tells them apart is the passthrough's
`content_item_kinds`: `user.*` parts for what was typed, named kinds for what the
client added. These fixtures copy the real rollout structure (session_meta, row
`ordinal`, passthrough `turn_id` / `create_time` / `content_item_kinds`, subagent
`source`, imported Claude Code history before the first Desktop turn) with invented
text; the operator's store is never read.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from connectonion.rem.source import SKIPPED, UNFAMILIAR, _codex_message, _codex_meta, collect

NOW = datetime.now(timezone.utc)
EVER = datetime(1970, 1, 1, tzinfo=timezone.utc)
DESKTOP_META = {"id": "t1", "cwd": "/work/demo", "originator": "Codex Desktop", "source": "vscode",
                "cli_version": "0.1", "history_mode": "paginated"}
SPAWNED = {"subagent": {"thread_spawn": {"parent_thread_id": "t0", "depth": 1}}}
REVIEWER = {"subagent": {"other": "guardian"}}


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def desktop(text, kinds=("user.text",), *, parts=None, when=None, ordinal=1):
    """One user-slot row as Codex Desktop writes it."""
    passthrough = {"turn_id": "turn-1", "create_time": 1790000000.5}
    if kinds is not None:
        passthrough["content_item_kinds"] = list(kinds)
    return {"timestamp": when or ago(1), "type": "response_item", "ordinal": ordinal, "payload": {
        "type": "message", "role": "user", "id": "msg-1",
        "content": parts or [{"type": "input_text", "text": text}],
        "internal_chat_message_metadata_passthrough": passthrough}}


def bare(text, when=None):
    """The CLI's typed shape, and the shape of Claude Code history Desktop imported."""
    return {"timestamp": when or ago(1), "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}}


def rollout(path: Path, rows, *, meta=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    first = {"type": "session_meta", "payload": {**DESKTOP_META, "id": path.stem, **(meta or {})}}
    path.write_text("".join(json.dumps(row) + "\n" for row in [first, *rows]), encoding="utf-8")
    return path


def read(row, meta=None):
    return _codex_message(row, EVER, _codex_meta({"type": "session_meta", "payload": {**DESKTOP_META, **(meta or {})}}))


def subscription(path):
    return {"id": "codex", "kind": "codex", "root": str(path), "since": ago(30), "project": None,
            "enabled": True, "consented": True}


# ---- one row at a time ----

def test_a_message_typed_in_codex_desktop_is_read():
    assert read(desktop("把 swell 阈值改成 2m，然后跑测试。"))["text"] == "把 swell 阈值改成 2m，然后跑测试。"


def test_a_pasted_image_with_a_line_about_it_is_read_as_the_line():
    row = desktop("", ("user.text", "user.image", "user.text"), parts=[
        {"type": "input_text", "text": "This button is cut off on mobile."},
        {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
        {"type": "input_text", "text": "Fix the padding."}])
    assert read(row)["text"] == "This button is cut off on mobile.\nFix the padding."


def test_what_the_client_adds_to_the_user_turn_is_skipped():
    for kinds, text in [
        (("agents_md.instructions", "environments.environment_context"), "# AGENTS.md instructions for /w"),
        (("environments.environment_context",), "<environment_context>\n  <cwd>/w</cwd>"),
        (("plugins.recommendations", "environments.environment_context"), "<recommended_plugins>"),
        (("goal.internal_context",), '<codex_internal_context source="goal">Continue.'),
        (("skills.selected_skill_instructions",), "<skill>\nname: ship-feature"),
        (("generic.turn_aborted",), "<turn_aborted>"),
        # A named kind next to a typed part: the message is the client's composition.
        (("user.text", "environments.environment_context"), "Ship it."),
    ]:
        assert read(desktop(text, kinds)) is SKIPPED, kinds


def test_missing_kinds_with_modern_creation_metadata_are_not_guessed_as_typed():
    """Only the observed older turn_id-only native shape has a fallback."""
    assert read(desktop("Continue from where you left off.", kinds=())) is SKIPPED
    assert read(desktop("Continue from where you left off.", kinds=None)) is SKIPPED


def test_a_typed_kind_that_opens_with_a_harness_tag_is_still_not_read():
    """Voice delegation, heartbeats and automation prompts arrive as `user.text`."""
    for text in ["<realtime_delegation>\nThe user asked, by voice, to", "<heartbeat>tick</heartbeat>",
                 "Follow these instructions exactly. They are the skill `ship`"]:
        assert read(desktop(text)) is SKIPPED, text


def test_the_in_app_browser_context_goes_and_what_was_typed_stays():
    text = ("<in-app-browser-context>\nurl: https://example.test/pricing\ntitle: Pricing\n"
            "</in-app-browser-context>\n\nWhy is the annual price missing here?")
    assert read(desktop(text))["text"] == "Why is the annual price missing here?"
    assert read(desktop("<in-app-browser-context>\nurl: x\n</in-app-browser-context>\n")) is SKIPPED


def test_a_subagents_user_slot_is_not_the_person():
    """The approval reviewer is handed the agent's transcript; a spawned worker is handed
    a prompt the agent wrote, or a copy of the parent's messages. Both say `user.text`."""
    typed_looking = desktop("Review the diff in /w and report problems.")
    assert read(typed_looking, {"source": SPAWNED}) is SKIPPED
    assert read(typed_looking, {"source": REVIEWER}) is SKIPPED
    assert read(bare("Find the failing test."), {"source": SPAWNED}) is SKIPPED


def test_claude_code_history_imported_into_desktop_is_not_read_twice():
    """Desktop imports a Claude Code session as bare rows; co rem reads it from Claude Code."""
    assert read(bare("Merge it once CI is green.")) is SKIPPED
    cli = _codex_meta({"type": "session_meta", "payload": {"id": "c", "cwd": "/w", "originator": "codex_cli_rs"}})
    assert _codex_message(bare("Merge it once CI is green."), EVER, cli)["text"] == "Merge it once CI is green."


def test_null_passthrough_without_id_retains_cli_requests_but_not_imports_or_workers(tmp_path):
    def nullable(text):
        row = bare(text)
        row['payload']['internal_chat_message_metadata_passthrough'] = None
        return row

    rollout(tmp_path / 'rollout-cli.jsonl', [nullable('Ask Vern about the revised placement.'),
            nullable('<environment_context>Injected repository context')],
            meta={'originator': 'codex_cli_rs'})
    rollout(tmp_path / 'rollout-import.jsonl', [nullable('Imported Claude history')])
    rollout(tmp_path / 'rollout-worker.jsonl', [nullable('Parent assigned this task')],
            meta={'source': SPAWNED})
    batch = collect(subscription(tmp_path), {}, 20, 100_000)
    assert [item['text'] for item in batch.items] == ['Ask Vern about the revised placement.']
    assert batch.skipped == 3 and batch.unrecognised == 0


def test_desktop_kinds_still_classify_messages_without_optional_id():
    typed, injected = desktop('Keep the investor introduction.'), desktop('Injected', ('goal.internal_context',))
    del typed['payload']['id']
    del injected['payload']['id']
    assert read(typed)['text'] == 'Keep the investor introduction.'
    assert read(injected) is SKIPPED


def test_skill_mentions_missed_by_the_old_optional_id_reader_are_recounted(tmp_path):
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.skill_usage import usage

    row = bare('Use $ship-feature for this release.')
    row['payload']['internal_chat_message_metadata_passthrough'] = None
    path = rollout(tmp_path / 'sessions/rollout-cli.jsonl', [row], meta={'originator': 'codex_cli_rs'})
    root = tmp_path / 'rem'
    stat = path.stat()
    write_json(state_path(root, 'skill-usage.json'), {'version': 2, 'files': {
        str(path): {'stamp': [stat.st_size, stat.st_mtime_ns], 'events': []}}})
    report = usage({'codex': {'kind': 'codex', 'root': str(path.parent), 'enabled': True}},
                   ['ship-feature'], root=root, days=30)
    assert report['counts']['ship-feature']['count'] == 1


def test_old_interactive_cli_turn_metadata_retains_intent_but_not_exec_imports(tmp_path):
    def turn(text):
        row = bare(text)
        row['payload']['internal_chat_message_metadata_passthrough'] = {'turn_id': 'turn-1'}
        return row

    rollout(tmp_path / 'rollout-tui.jsonl', [turn('Ask Vern about the revised placement.'),
            turn('<environment_context>Injected context')], meta={'originator': 'codex-tui', 'source': 'cli'})
    rollout(tmp_path / 'rollout-exec.jsonl', [turn('Agent-generated worker prompt')],
            meta={'originator': 'codex_exec', 'source': 'exec'})
    rollout(tmp_path / 'rollout-import.jsonl', [turn('Imported client input')], meta={'source': 'exec'})
    rollout(tmp_path / 'rollout-worker.jsonl', [turn('Parent-assigned task')],
            meta={'originator': 'codex-tui', 'source': SPAWNED})
    batch = collect(subscription(tmp_path), {}, 20, 100_000)
    assert [item['text'] for item in batch.items] == ['Ask Vern about the revised placement.']
    assert batch.skipped == 4 and batch.unrecognised == 0


def test_a_row_judged_without_its_file_is_read_as_the_cli_would_write_it():
    assert _codex_message(bare("Ship it on Friday."), EVER)["text"] == "Ship it on Friday."
    assert _codex_message(desktop("Ship it on Friday."), EVER)["text"] == "Ship it on Friday."


def test_a_passthrough_in_a_shape_we_do_not_know_is_the_alarm():
    row = desktop("Ship it.")
    row["payload"]["internal_chat_message_metadata_passthrough"]["content_item_kinds"] = "user.text"
    assert read(row) is UNFAMILIAR
    row["payload"]["internal_chat_message_metadata_passthrough"] = ["user.text"]
    assert read(row) is UNFAMILIAR
    row = desktop("Ship it.")
    row["payload"]["provenance"] = {"kind": "typed"}
    assert read(row) is UNFAMILIAR


# ---- a whole Desktop thread through sync's collector ----

def test_sync_reads_a_desktop_thread_as_the_person_wrote_it(tmp_path):
    rollout(tmp_path / "2026/09/28/rollout-desk.jsonl", [
        bare("An imported Claude Code message.", ago(3)),
        desktop("# AGENTS.md instructions for /work/demo", ("agents_md.instructions",), when=ago(2)),
        desktop("<environment_context>\n  <cwd>/work/demo</cwd>", ("environments.environment_context",), when=ago(2)),
        desktop("Warn surfers when the swell passes 2m.", when=ago(2)),
        desktop('<codex_internal_context source="goal">Keep going.', ("goal.internal_context",), when=ago(1)),
        desktop("Now add a test for 1.99m.", when=ago(1)),
    ])
    rollout(tmp_path / "2026/09/28/rollout-review.jsonl", [desktop("Assess this action.", when=ago(1))],
            meta={"source": REVIEWER})
    batch = collect(subscription(tmp_path), {}, 20, 100_000)
    assert [i["text"] for i in batch.items] == ["Warn surfers when the swell passes 2m.", "Now add a test for 1.99m."]
    assert batch.skipped == 5 and batch.unrecognised == 0 and not batch.unreadable


def test_skill_usage_counts_a_mention_the_way_sync_reads_the_message(tmp_path):
    """A skill page's `$name` count reads the same typed messages sync does: Desktop's
    count, and a `$name` a subagent was handed, an imported history carried or the
    client injected does not. A SKILL.md load in a subagent is still a load."""
    from connectonion.rem.skill_usage import usage

    def load(path):
        return {"timestamp": ago(1), "type": "response_item", "payload": {
            "type": "function_call", "name": "exec_command", "arguments": json.dumps({"cmd": f"cat {path}"})}}

    turn = {"type": "turn_context", "payload": {"cwd": "/work/demo"}}
    rollout(tmp_path / "2026/09/28/rollout-desk.jsonl", [
        bare("run $ship-feature (imported from Claude Code)", ago(3)),
        turn, desktop("<skill>\nname: ship-feature\n$ship-feature</skill>", ("skills.selected_skill_instructions",)),
        turn, desktop("Continue with $ship-feature.", kinds=()),
        turn, desktop("用 $ship-feature 发这个版本。"),
    ])
    rollout(tmp_path / "2026/09/28/rollout-worker.jsonl", [
        turn, desktop("Use $ship-feature on the branch."), load("/h/.codex/skills/ship-feature/SKILL.md"),
    ], meta={"source": SPAWNED})
    report = usage({"codex": {"kind": "codex", "root": str(tmp_path), "enabled": True}}, ["ship-feature"],
                   root=tmp_path / "rem", days=30)
    assert report["counts"]["ship-feature"]["count"] == 2  # the typed mention and the worker's load
    cache = json.loads((tmp_path / "rem/.state/skill-usage.json").read_text())
    assert cache["version"] == 4  # counts cached under the old reading are recounted


def test_older_native_desktop_turn_only_inputs_are_read_without_importing_automation():
    row = desktop('Find the workshop registration link.')
    row['payload']['internal_chat_message_metadata_passthrough'] = {'turn_id': 'native-turn'}
    result = read(row)
    assert result['text'] == 'Find the workshop registration link.'
    assert 'content kinds were not recorded' in result['input_scope']
    assert read(row, {'source': 'exec'}) is SKIPPED
    assert read(row, {'source': SPAWNED}) is SKIPPED
    row['payload']['content'][0]['text'] = 'Automation: social review\nAutomation ID: social-review\nReview ten posts.'
    assert read(row) is SKIPPED
    assert read(desktop(row['payload']['content'][0]['text'])) is SKIPPED


def test_native_desktop_voice_reads_only_explicit_input_with_its_scope():
    text = ('<realtime_delegation>\n<input>Keep the original folder unchanged.</input>\n'
            '<transcript_delta>assistant: I moved it.\nuser: Duplicate context.</transcript_delta>\n'
            '</realtime_delegation>')
    result = read(desktop(text))
    assert result['text'] == 'Keep the original folder unchanged.'
    assert 'voice transcription' in result['input_scope']
    assert 'transcript delta omitted' in result['input_scope']
    assert read(desktop(text), {'source': SPAWNED}) is SKIPPED
    assert read(desktop(text), {'source': 'exec'}) is SKIPPED
    assert read(desktop(text), {'originator': 'codex_cli_rs', 'source': 'cli'}) is SKIPPED


def test_voice_tail_flush_and_unknown_wrapper_shapes_are_not_user_input():
    for text in [
        '<realtime_delegation><source>transcript_tail_flush</source><input>The user ended.</input>'
        '<transcript_delta>user: Earlier input</transcript_delta></realtime_delegation>',
        '<realtime_delegation><input>Keep it.</input></realtime_delegation>',
        '<realtime_delegation><input>First.</input><input>Second.</input>'
        '<transcript_delta>mixed</transcript_delta></realtime_delegation>',
        '<realtime_delegation><input> </input><transcript_delta>assistant: generated</transcript_delta>'
        '</realtime_delegation>',
    ]:
        assert read(desktop(text)) is SKIPPED


def test_recovered_input_scope_survives_project_storage_and_investigator_evidence(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.project_material import extract, stored
    from connectonion.rem.project_pages import material
    from connectonion.rem.evidence import write_evidence

    root, sessions = tmp_path / 'rem', tmp_path / 'sessions'
    prepare(root)
    Notebook(root).stub_project('projects/demo.md', 'demo', ['/work/demo'])
    voice = desktop('<realtime_delegation><input>Keep the original folder unchanged.</input>'
                    '<transcript_delta>assistant: Already moved.</transcript_delta></realtime_delegation>')
    old = desktop('Find the workshop registration link.')
    old['payload']['internal_chat_message_metadata_passthrough'] = {'turn_id': 'old-turn'}
    rollout(sessions / 'rollout-inputs.jsonl', [voice, old])
    extract(root, {'codex': subscription(sessions)}, full=True, now=NOW)
    messages = stored(root, 'projects/demo.md')
    assert len(messages) == 2 and all(message['input_scope'] for message in messages)
    assert 'Already moved.' not in '\n'.join(message['text'] for message in messages)
    items, _ = material(root, 'projects/demo.md', now=NOW)
    inputs = [item for item in items if item['role'] == 'user']
    assert {item['input_scope'] for item in inputs} == {message['input_scope'] for message in messages}
    write_evidence(tmp_path / 'evidence', inputs)
    evidence_files = list((tmp_path / 'evidence/codex').glob('*.md'))
    assert len(evidence_files) == 1
    assert all('Input scope:' in path.read_text() for path in evidence_files)
    assert 'Input scope:' in next((root / '.state/projects').rglob('messages.md')).read_text()


def test_reader_preserves_voice_scope_in_source_and_conversation(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import state_path, write_json, atomic_write
    from connectonion.rem.store import refresh
    from connectonion.rem.reader_model import cited_context, cited_conversations
    root = tmp_path / 'rem'
    prepare(root)
    record = 'projects/demo.md'
    folder = state_path(root, 'projects/demo')
    folder.mkdir(parents=True)
    scope = 'Codex Desktop voice transcription; transcript delta omitted'
    source = 'codex:session:100'
    write_json(folder / 'state.json', {'record': record})
    atomic_write(folder / 'messages.jsonl', json.dumps({'source': source, 'tool': 'codex', 'text': 'Keep it unchanged.',
                 'timestamp': ago(1), 'input_scope': scope}) + '\n')
    refresh(root)
    context = cited_context(root, [{'text': '## Sources\n- [1] ' + source}])
    assert context[source]['excerpt'] == 'Keep it unchanged.' and context[source]['input_scope'] == scope
    thread = cited_conversations(root, context)[context[source]['thread']]
    assert thread['messages'][0]['input_scope'] == scope
