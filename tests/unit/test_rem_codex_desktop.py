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
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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


def test_exec_prompts_are_not_collected_as_the_persons_cli_messages(tmp_path):
    for name, meta in [
        ("exec", {"originator": "codex_exec", "source": "exec"}),
        ("exec-originator", {"originator": "codex_exec", "source": "cli"}),
        ("exec-source", {"originator": "codex_cli_rs", "source": "exec"}),
    ]:
        rollout(tmp_path / f"rollout-{name}.jsonl", [
            bare("Investigate Vern and cite this as the user's note."),
            desktop("This program prompt carries user.text metadata."),
        ], meta=meta)
    for originator in ("codex-tui", "codex_cli_rs"):
        rollout(tmp_path / f"rollout-{originator}.jsonl", [bare("Ask Vern about the placement.")],
                meta={"originator": originator, "source": "cli"})

    batch = collect(subscription(tmp_path), {}, 20, 100_000)
    assert [item["text"] for item in batch.items] == ["Ask Vern about the placement."] * 2
    assert batch.skipped == 6 and batch.unrecognised == 0


def test_exec_prompts_do_not_vote_for_the_owners_languages_even_when_cached(tmp_path, monkeypatch):
    from connectonion.rem import investigate
    from connectonion.rem.languages import detect

    sessions, root = tmp_path / "sessions", tmp_path / "rem"
    rollout(sessions / "rollout-exec.jsonl", [bare("请调查这个人的工作经历和项目进展。")],
            meta={"originator": "codex_exec", "source": "exec"})
    rollout(sessions / "rollout-cli.jsonl", [bare("Ask Vern about the placement.")],
            meta={"originator": "codex-tui", "source": "cli"})
    investigate._session_window(subscription(sessions), "sessions", None, root)
    cache = next((root / ".state/session-windows").glob("*.json"))
    saved = json.loads(cache.read_text())
    saved["version"] = 1
    saved["items"].append({"role": "user", "text": "请调查这个人的工作经历和项目进展。",
                           "source": "codex:exec:1", "timestamp": ago(1),
                           "reference": (sessions / "rollout-exec.jsonl").as_uri()})
    cache.write_text(json.dumps(saved))
    assert detect(root, [])["messages"] == 0
    monkeypatch.setattr(investigate, "_WINDOWS", {})
    items, _ = investigate._session_window(subscription(sessions), "sessions", None, root)

    assert [item["text"] for item in items] == ["Ask Vern about the placement."]
    assert detect(root, []) == {"languages": ["en"], "shares": {"en": 1.0}, "messages": 1}


@pytest.mark.parametrize('version,missing_progress', [(1, False), (0, False), (1, True)])
def test_session_window_migrates_v1_without_recollecting_unchanged_files(
        tmp_path, monkeypatch, version, missing_progress):
    from connectonion.rem import investigate, source
    from connectonion.rem.files import state_path, write_json

    sessions, root = tmp_path / 'session files', tmp_path / 'rem'
    interactive = rollout(sessions / 'rollout-cli.jsonl', [bare('Ask Avery Lin about delivery.')],
                          meta={'originator': 'codex-tui', 'source': 'cli'})
    executable = rollout(sessions / 'rollout-exec.jsonl', [bare('Program-written prompt.')],
                         meta={'originator': 'codex_exec', 'source': 'exec'})
    scoped = subscription(sessions)
    batch = collect({**scoped, 'since': ago(800)}, {}, 20, 100_000)
    gone = sessions / 'rollout-gone.jsonl'
    cached = [*batch.items,
              {**batch.items[0], 'text': 'Program-written prompt.', 'reference': executable.as_uri()},
              {**batch.items[0], 'text': 'Previously retained message.', 'reference': gone.as_uri()}]
    if missing_progress:
        batch.progress['rollout-gone.jsonl'] = {'offset': 1}
    identity = json.dumps({key: value for key, value in scoped.items() if key != 'since'},
                          sort_keys=True, default=str)
    cache = state_path(root, f'session-windows/{hashlib.sha256(identity.encode()).hexdigest()[:16]}.json')
    write_json(cache, {'version': version, 'subscription': identity, 'since': ago(800),
                       'items': cached, 'progress': batch.progress, 'unfamiliar': 0})
    calls, metadata_reads = [], []
    original_meta = source.KINDS['codex']['meta']

    def meta(first):
        metadata_reads.append(first['payload']['id'])
        return original_meta(first)

    def collecting(subscription, progress, *limits):
        calls.append(progress)
        return collect(subscription, progress, *limits)

    monkeypatch.setitem(source.KINDS['codex'], 'meta', meta)
    monkeypatch.setattr(investigate, '_WINDOWS', {})
    monkeypatch.setattr(investigate, 'collect', collecting)
    items, _ = investigate._session_window(scoped, 'sessions', None, root)
    saved = json.loads(cache.read_text())
    assert saved['version'] == 2
    if version == 1 and not missing_progress:
        assert calls == [batch.progress]
        assert saved['progress'] == batch.progress
        assert [item['text'] for item in items] == [
            'Ask Avery Lin about delivery.', 'Previously retained message.']
        assert metadata_reads == [interactive.stem, executable.stem]
    else:
        assert calls[0] == {}
        assert [item['text'] for item in items] == ['Ask Avery Lin about delivery.']


def test_project_discovery_turns_exclude_exec_and_subagent_sessions(tmp_path):
    from connectonion.rem.scan import scan_projects

    turn = {"type": "turn_context", "payload": {"cwd": "/work/demo"}}
    for name, source in [("exec", "exec"), ("worker", SPAWNED), ("cli", "cli")]:
        rollout(tmp_path / f"rollout-{name}.jsonl", [turn, bare("Inspect the project.")],
                meta={"originator": "codex_exec" if source == "exec" else "codex-tui",
                      "source": source, "cwd": f"/work/{name}"})

    projects = scan_projects({"codex": subscription(tmp_path)}, 30)
    assert {project["path"]: project["turns"] for project in projects} == {
        "/work/exec": 0, "/work/worker": 0, "/work/cli": 1}


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
    rollout(tmp_path / "2026/09/28/rollout-exec.jsonl", [
        turn, bare("Use $ship-feature on the branch."),
        turn, load("/h/.codex/skills/ship-feature/SKILL.md"),
    ], meta={"originator": "codex_exec", "source": "exec"})
    report = usage({"codex": {"kind": "codex", "root": str(tmp_path), "enabled": True}}, ["ship-feature"],
                   root=tmp_path / "rem", days=30)
    assert report["counts"]["ship-feature"]["count"] == 3  # the typed mention and both workers' loads
    cache = json.loads((tmp_path / "rem/.state/skill-usage.json").read_text())
    assert cache["version"] == 5  # counts cached under the old reading are recounted


def test_exec_skill_mentions_cached_before_the_exclusion_are_recounted(tmp_path):
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.skill_usage import usage

    path = rollout(tmp_path / "sessions/rollout-exec.jsonl", [bare("Use $ship-feature.")],
                   meta={"originator": "codex_exec", "source": "exec"})
    stat = path.stat()
    root = tmp_path / "rem"
    write_json(state_path(root, "skill-usage.json"), {"version": 4, "files": {
        str(path): {"stamp": [stat.st_size, stat.st_mtime_ns],
                    "events": [["ship-feature", ago(1), "codex", "/work/demo"]]}}})
    report = usage({"codex": subscription(path.parent)}, ["ship-feature"], root=root, days=30)
    assert report["counts"]["ship-feature"]["count"] == 0


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


def test_cited_desktop_message_keeps_a_table_cell_after_640_chars(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import state_path, write_json, atomic_write
    from connectonion.rem.reader_model import cited_context
    from connectonion.rem.store import refresh

    prepare(tmp_path)
    folder = state_path(tmp_path, 'projects/demo')
    folder.mkdir(parents=True)
    write_json(folder / 'state.json', {'record': 'projects/demo.md'})
    source = 'codex:session:100'
    message = 'Earlier table rows. ' * 35 + '| Last row | branch only | hard filter |'
    atomic_write(folder / 'messages.jsonl', json.dumps({
        'source': source, 'tool': 'codex', 'text': message,
        'timestamp': ago(1), 'input_scope': 'Owner input only'}) + '\n')
    refresh(tmp_path)

    context = cited_context(tmp_path, [{'text': '## Sources\n- [1] ' + source}])[source]
    assert len(message) > 640
    assert context['excerpt'] == message
    assert not context['truncated']
