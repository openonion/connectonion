"""Two people pages that may be one person (#2724): code finds them, a model decides."""

import json

import pytest

from connectonion.rem import same_person
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, read_json, state_path, write_json


def _person(notebook, record, name, address, written=""):
    notebook.stub_person(record, name, [address], email=address)
    page = notebook.read(record).replace("not investigated yet", "investigated 2026-10-10")
    notebook.write(record, page.replace("## Insight\n", "## Insight\n" + written, 1) if written else page)


@pytest.fixture
def root(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    _person(notebook, "people/robin.md", "Robin", "robin@mail.example")
    _person(notebook, "people/robin-hale.md", "Robin Hale", "rhale@work.example", "- Builds sensor kits [1].\n")
    _person(notebook, "people/sam.md", "Sam Ito", "sam@team.example")
    write_json(state_path(tmp_path, "map.json"), {"people": [
        {"record": "people/robin.md", "addresses": ["robin@mail.example"]},
        {"record": "people/robin-hale.md", "addresses": ["rhale@work.example"]},
        {"record": "people/sam.md", "addresses": ["sam@team.example"]}]})
    return tmp_path


def _answer(same, role="their own"):
    def run(workspace, prompt, config, stage):
        assert stage == "same-person" and "Robin Hale" in prompt and "# Are these two pages one person?" in prompt
        return {"result": json.dumps({"same": same, "address_role": role, "reason": "Signs both [1]."}),
                "usage": {"input_tokens": 10}}
    return run


def test_pages_whose_names_are_alike_are_candidates_and_others_are_not(root):
    pairs = same_person.candidates(root)
    assert [pair["pages"] for pair in pairs] == [["people/robin-hale.md", "people/robin.md"]]
    assert pairs[0]["why"] == "one name inside the other"


def test_a_page_listing_the_address_another_was_made_from_is_a_candidate_whatever_the_names(root):
    notebook = Notebook(root)
    page = notebook.read("people/sam.md")
    notebook.write("people/sam.md", page.replace("- Email: sam@team.example",
                                                 "- Email: sam@team.example; robin@mail.example [2]"))
    pages = [pair["pages"] for pair in same_person.candidates(root)]
    assert ["people/robin.md", "people/sam.md"] in pages


def test_yes_folds_the_less_written_page_into_the_more_written_one(root):
    rows = same_person.judge(root, {}, run=_answer(True))
    assert rows[0]["kept"] == "people/robin-hale.md"
    assert Notebook(root).list("people") == ["people/robin-hale.md", "people/sam.md"]
    assert (root / ".state/archived/people/robin.md").is_file()          # moved, never deleted
    assert read_json(state_path(root, "same-person.json"), {})["people/robin-hale.md|people/robin.md"]["same"]


def test_no_keeps_both_pages_and_the_pair_is_not_asked_again(root):
    rows = same_person.judge(root, {}, run=_answer(False, "assistant or delegate"))
    assert "kept" not in rows[0]
    assert len(Notebook(root).list("people")) == 3
    verdict = read_json(state_path(root, "same-person.json"), {})["people/robin-hale.md|people/robin.md"]
    assert (verdict["same"], verdict["address_role"]) == (False, "assistant or delegate")
    assert same_person.judge(root, {}, run=lambda *a: pytest.fail("already judged")) == []


def test_an_answer_outside_the_schema_merges_nothing(root):
    from connectonion.rem.runner import RunFailed
    with pytest.raises(RunFailed):
        same_person.judge(root, {}, run=lambda *a: {"result": json.dumps({"same": "yes"})})
    assert len(Notebook(root).list("people")) == 3
    assert read_json(state_path(root, "same-person.json"), {}) == {}


def test_an_answer_in_a_json_fence_is_read(root):
    """A Claude Code turn returned its JSON inside ```json ... ``` (2026-11-03 trial)."""
    answer = json.dumps({"same": False, "address_role": "unclear", "reason": "Different threads."})
    rows = same_person.judge(root, {}, run=lambda *a: {"result": f"Checked both pages.\n```json\n{answer}\n```"})
    assert rows[0]["same"] is False


def test_a_page_folded_by_one_answer_is_not_asked_about_again(root):
    """2026-11-03 trial: after the first fold, the next pair named the archived page and the run stopped."""
    _person(Notebook(root), "people/robin-h.md", "Robin H", "robin.h@mail.example")
    asked = []

    def run(workspace, prompt, config, stage):
        asked.append(prompt)
        return {"result": json.dumps({"same": True, "address_role": "their own", "reason": "Same threads."})}
    rows = same_person.judge(root, {}, run=run, limit=9)
    assert all("kept" in row for row in rows) and len(Notebook(root).list("people")) == 2
