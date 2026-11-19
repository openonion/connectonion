"""Tagging in the night: a share between portions, a closing pass that drains, status, and the reader's data (#3093).

Invented data only.
"""
import json

from connectonion.rem import catchup, native_round, stages, tag_stage, tags
from connectonion.rem.config import default_config, read_config, set_config
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.reader_model import graph_snapshot
from tests.unit.test_rem_night_shares import cursor_of, notebook, person, serve  # noqa: F401
from tests.unit.test_rem_tags import PERSON


def people(root, count):
    book = Notebook(root)
    for n in range(count):
        book.write(f"people/p{n:02}.md", f"# P{n}\n\n## Facts\n- Role: Student in COMP9900 [1]\n")
    return [f"people/p{n:02}.md" for n in range(count)]


def night(root, cursor):
    """The stages a round serves until it is done; each tag batch is accepted as `advance` settles it."""
    directory = root / "task"
    directory.mkdir(exist_ok=True)
    served = []
    while (task := native_round.prepare_task(root, cursor, read_config(root), directory)) is not None:
        served.append(task["stage"])
        if task["stage"] == "tag":
            ids = task["task"]["ids"]
            value = {"pages": [{"id": page, "tags": [{"tag": "student", "evidence": "Student in COMP9900"}]}
                               for page in ids], "new_tags": [{"tag": "student", "label": "student", "kind": "role"}]}
            result = native_round.check_task(root, task, {"result": json.dumps(value)})
            native_round.advance(root, cursor, {**task, "directory": str(directory)}, result)
        elif task["stage"] == "investigate":
            cursor["investigation_left"] -= 1
            cursor.update(job_index=cursor["job_index"] + 1, current=None)
    return served


def test_the_closing_pass_tags_every_waiting_page_in_batches_of_twenty(notebook):
    pages = people(notebook, 45)
    cursor = cursor_of(notebook, [])
    assert night(notebook, cursor) == ["tag"] * 3
    assert cursor["tagged"] == 45 and cursor["done"] and "tags_waiting" not in cursor
    assert all(tags.page_tags(Notebook(notebook).read(page)) == ["student"] for page in pages)
    assert tag_stage.candidates(notebook) == []


def test_a_round_tags_at_most_its_bound_and_says_how_many_wait(notebook):
    people(notebook, 30)
    set_config(notebook, ["limits.tags_per_round", "25"])
    cursor = cursor_of(notebook, [])
    assert night(notebook, cursor) == ["tag", "tag"]
    assert cursor["tagged"] == 25 and cursor["tags_waiting"] == 5


def test_a_refused_batch_is_not_offered_again_in_the_same_round(notebook):
    people(notebook, 3)
    cursor = cursor_of(notebook, [])
    directory = notebook / "task"
    directory.mkdir()
    first = native_round.prepare_task(notebook, cursor, read_config(notebook), directory)
    assert first["stage"] == "tag" and len(first["task"]["records"]) == 3
    # Its reply was refused: the pages still wait, and the round ends instead of asking again.
    assert native_round.prepare_task(notebook, cursor, read_config(notebook), directory) is None
    assert len(tag_stage.candidates(notebook)) == 3


def test_one_tag_turn_comes_between_two_portions_of_investigation(notebook, monkeypatch):
    serve(monkeypatch)
    people(notebook, 25)
    cursor = cursor_of(notebook, [person(name) for name in ("ivy", "wren", "fern")])
    assert night(notebook, cursor) == ["investigate", "investigate", "tag", "investigate", "tag"]


def test_the_bound_is_a_round_limit_with_a_high_default():
    assert default_config()["limits"]["tags_per_round"] == 400
    from connectonion.rem import native
    assert "tags_per_round" in native.RUN_LIMITS


def test_status_has_a_tag_line(notebook):
    people(notebook, 3)
    row = next(row for row in stages.status(notebook, read_config(notebook), []) if row["name"] == "Tag")
    assert row["text"] == "Tag: 3 untagged pages waiting; last ran never; a round tags up to 400"
    run = {"id": "run_t", "phase": "tag", "outcome": "completed", "started_at": "2026-09-07T10:00:00+00:00"}
    write_json(state_path(notebook, "runs/run_t.json"), run)
    for page in tag_stage.candidates(notebook):
        Notebook(notebook).write(page, tags.with_tags(Notebook(notebook).read(page), [{"tag": "student"}]))
    write_json(state_path(notebook, tag_stage.MARKS),
               {page: tag_stage.digest(Notebook(notebook).read(page)) for page in Notebook(notebook).list("people")})
    row = next(row for row in stages.status(notebook, read_config(notebook), [run]) if row["name"] == "Tag")
    assert row["text"] == "Tag: 0 untagged pages waiting; last ran 2026-09-07"


def test_the_nights_counts_carry_the_pages_tagged_and_what_the_bound_left(notebook):
    with catchup.scope(notebook, 2):
        write_json(state_path(notebook, "round.json"),
                   cursor_of(notebook, [], catchup_night=2, tagged=40, tags_waiting=3))
    counts = catchup._counts(notebook, 2)
    assert (counts["tagged"], counts["tags_waiting"]) == (40, 3)
    # A night that only tagged produced something.
    assert catchup._stop({"outcome": "done", "reason": "round done"},
                         {"written": 0, "translated": 0, "drafts": 0, "tagged": 40}, 1) == ("", False)


def test_tagging_a_page_leaves_its_translation_current(notebook):
    from connectonion.rem import translate
    book = Notebook(notebook)
    book.write("people/mira-osei.md", PERSON)
    task = translate.prepare(notebook, "people/mira-osei.md", "zh", directory=notebook)
    translate.check(task, {"result": PERSON.split("## Sources")[0].replace("Presents", "介绍")})
    assert translate.cached(notebook, "people/mira-osei.md", "zh") is not None
    book.write("people/mira-osei.md", tags.with_tags(PERSON, [{"tag": "9900", "citation": "3"}]))
    assert translate.cached(notebook, "people/mira-osei.md", "zh") is not None
    # Nor does the line make a Chinese page "mixed".
    chinese = "# 米拉\n\n## Facts\n- Company: 港湾大学 [1]\n- Tags: student, harbour-university\n"
    assert translate.foreign_lines(chinese, "zh") == []


def test_graph_tag_layer_has_a_node_per_tag_and_an_edge_per_tagged_record():
    records = [{"path": "people/mira-osei.md", "category": "people", "title": "Mira Osei",
                "text": tags.with_tags(PERSON, [{"tag": "9900", "citation": "3"}, {"tag": "student"}])},
               {"path": "orgs/harbour-university.md", "category": "orgs", "title": "Harbour University",
                "text": "# Harbour University\n\n## Facts\n- Tags: 9900\n"},
               {"path": "people/hidden.md", "category": "people", "title": "Hidden", "private": True,
                "text": "# Hidden\n\n## Facts\n- Tags: secret-topic\n"}]
    vocabulary = {"9900": {"label": "COMP9900", "kind": "course", "aliases": [], "count": 2}}
    graph = graph_snapshot(records, links={}, vocabulary=vocabulary)
    assert {node["kind"] for node in graph["nodes"]} == {"people", "orgs"}, "the current reader's nodes are unchanged"
    assert graph["tags"]["nodes"] == [
        {"id": "tag:9900", "kind": "tag", "label": "COMP9900", "tag_kind": "course", "count": 2},
        {"id": "tag:student", "kind": "tag", "label": "student", "tag_kind": "topic", "count": 1}]
    assert {"source": "orgs/harbour-university.md", "target": "tag:9900", "kind": "tagged"} in graph["tags"]["edges"]
    assert all(edge["source"] != "people/hidden.md" for edge in graph["tags"]["edges"])


def test_open_items_in_the_today_queue_carry_their_tags(notebook):
    from connectonion.rem import today
    book = Notebook(notebook)
    page = tags.with_tags(PERSON, [{"tag": "9900", "citation": "3"}]).replace(
        "## Sources", "## Open threads\n- You owe Mira feedback on the F13 demo [3]\n\n## Sources")
    book.write("people/mira-osei.md", page)
    rows = today.queue(notebook)
    assert rows and all(row["tags"] == ["9900"] for row in rows if row["record"] == "people/mira-osei.md")
