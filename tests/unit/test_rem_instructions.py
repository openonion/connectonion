"""Stage and source are two axes, and composing them is what keeps them apart."""

import pytest

from connectonion.rem.files import RemError
from connectonion.rem.runner import instructions, maintenance_instructions
from connectonion.rem.extract import extraction_instructions


def test_a_stage_that_reads_a_source_is_handed_that_source():
    """Four sources times four stages would be sixteen files; composing is seven."""
    for stage in ("extract", "maintain", "investigate"):
        alone, composed = instructions(stage), instructions(stage, "codex")
        assert len(composed) > len(alone)
        assert alone in composed                       # the stage is intact
        assert "rem-source-codex" in composed         # the source was appended


def test_abstract_refuses_a_source_because_its_input_is_pages():
    """The check on whether the split is real: a stage reading pages must not
    know which store they came from."""
    assert instructions("abstract", "codex") == instructions("abstract")
    assert "rem-source-codex" not in instructions("abstract", "codex")


def test_a_source_nobody_wrote_a_file_for_still_runs_on_the_stage_alone():
    assert instructions("extract", "no-such-source") == instructions("extract")


def test_an_unknown_stage_is_refused_by_name():
    with pytest.raises(RemError) as caught:
        instructions("summarise")
    assert "summarise" in str(caught.value)
    for stage in ("extract", "maintain", "investigate", "abstract"):
        assert stage in str(caught.value)


def test_both_passes_of_a_batch_read_the_same_source_file():
    """The digest and the page-writer see the same lessons; only the stage differs."""
    codex_only = instructions("extract", "codex").split("---\n\n")[-1]
    assert codex_only and codex_only in maintenance_instructions("codex")
    assert codex_only in extraction_instructions("codex")


def test_a_page_shape_is_defined_once_and_reaches_every_stage_that_writes_one():
    """It lived inside one stage, was copied into a second, and they drifted
    within a day -- one renaming the headings the roster reads back."""
    for stage in ("maintain", "investigate"):
        text = instructions(stage)
        assert "\n# A person's page\n" in text
        for heading in ("## Contact", "## Open threads", "## Uncertainties"):
            assert heading in text, (stage, heading)
        for label in ("Email:", "Also known as:", "Signing entity:"):
            assert label in text, (stage, label)


def test_a_stage_that_writes_no_page_is_not_given_a_page_shape():
    for stage in ("extract", "abstract"):
        assert "\n# A person's page\n" not in instructions(stage)


def test_no_stage_carries_its_own_second_copy_of_the_person_shape():
    """Two definitions is how the drift happened; one is the fix."""
    from connectonion.skills_catalog import useful_skills_dir

    # The definition is the `#` heading; a `##` pointer to it is fine and wanted.
    owners = [p.parent.name for p in useful_skills_dir().glob("rem-*/SKILL.md")
              if any(line.rstrip() == "# A person's page"
                     for line in p.read_text(encoding="utf-8").splitlines())]
    assert owners == ["rem-page-person"], owners


def test_every_page_category_has_its_own_page_shape():
    """An org page used to get every page shape and the CLI reference, 63.7k
    characters, because the record-to-kind map had no `orgs`."""
    from connectonion.skills_catalog import useful_skills_dir
    from connectonion.rem.queue import CATEGORIES
    from connectonion.rem.runner import page_kind_of

    for category, prefix in CATEGORIES.items():
        kind = page_kind_of(prefix + "example.md")
        assert kind, category
        assert (useful_skills_dir() / f"rem-page-{kind}/SKILL.md").is_file(), category


def test_an_org_page_turn_carries_only_the_org_shape(tmp_path):
    from connectonion.rem.runner import task_prompt

    task_prompt(tmp_path, [{"role": "page", "record": "orgs/acme.md", "text": "# Acme"}], "investigate")
    given = (tmp_path / "instructions.md").read_text(encoding="utf-8")

    assert given == instructions("investigate", page_kind="org")
    assert len(given) < len(instructions("investigate")) - 10_000


@pytest.mark.parametrize("kind", ["person", "project", "org", "skill"])
def test_a_one_page_turn_is_not_told_to_read_the_cli_reference_up_front(kind):
    """#1960: "read the CLI reference first" was obeyed on every run, a 12.6k
    `cat` that made a 14.8k turn carry ~27k. Only a turn that runs `co` needs it."""
    text = instructions("investigate", page_kind=kind)
    assert "CLI.md" not in text and "CLI reference" not in text
    assert "`co rem <command> --help`" in text


def test_an_investigation_carries_only_its_own_kind_s_steps():
    """Owner, 2026-09-30: a person turn carried a project's Paths rules and a web
    lookup it could never run. Each kind now gets the core plus its own steps."""
    person, project = instructions("investigate", page_kind="person"), instructions("investigate", page_kind="project")

    assert "# Investigating a person" in person and "# Investigating a project" not in person
    assert "# Investigating a project" in project and "Signature block first" not in project
    for text in (person, project):
        assert "co browser" not in text                       # offline: the web block is not runtime text
        assert "A field the material does not answer stays `Unknown`" in text
        assert "## Only what is new" in text


@pytest.mark.parametrize("stage", ["investigate", "maintain"])
@pytest.mark.parametrize("kind", ["person", "project", "org", "skill"])
def test_a_one_page_turn_stays_within_15k_characters_of_instructions(stage, kind):
    """#1851: the Skill text is re-sent on every tool round. It was 30.6k for an
    investigation and 22.9k for maintenance; rationale now lives in
    docs/rem-skills/, and a rule that makes a turn heavier has to pay for it."""
    assert len(instructions(stage, page_kind=kind)) <= 15_000


def test_every_runtime_skill_names_where_its_rationale_lives():
    from connectonion.skills_catalog import useful_skills_dir
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    for name in ("rem-investigate", "rem-maintain", "rem-extract", "rem-abstract", "rem-page-person",
                 "rem-page-org", "rem-page-project", "rem-page-skill", "rem-source-codex",
                 "rem-source-whatsapp"):
        text = (useful_skills_dir() / name / "SKILL.md").read_text(encoding="utf-8")
        assert f"Why these rules: docs/rem-skills/{name}.md" in text, name
        assert (repo / "docs" / "rem-skills" / f"{name}.md").is_file(), name


def test_project_and_skill_templates_match_created_skeletons(tmp_path):
    """A model must receive the same exact headings that mapping created."""
    import re
    from connectonion.rem.files import Notebook
    from connectonion.skills_catalog import useful_skills_dir

    notebook = Notebook(tmp_path)
    notebook.stub_project('projects/example.md', 'Example', paths=['/example'])
    notebook.stub_skill('skills/catalog/example.md', 'Example', '/example/SKILL.md')
    for kind, record in [('project', 'projects/example.md'),
                         ('skill', 'skills/catalog/example.md')]:
        template = (useful_skills_dir() / f'rem-page-{kind}/SKILL.md').read_text()
        headings = re.findall(r'^## .+$', template, re.MULTILINE)
        assert headings == re.findall(r'^## .+$', notebook.read(record), re.MULTILINE)
        for stage in ('init', 'maintain', 'investigate'):
            assert template in instructions(stage)


def test_maintenance_is_told_what_is_still_open_and_how_large_a_page_may_grow():
    """#1956: four batches grew one page from 26.5k to 53.7k characters, re-adding
    week-old items as open threads."""
    text = instructions("maintain", page_kind="project")
    assert "Only what is still open is an open thread" in text
    assert "about 15k characters" in text


# ------------------------------------------- your own page has its own spec (#2008)


def test_only_the_owners_investigation_carries_the_owner_page_spec_and_it_stays_under_15k():
    """A real owner page took "Partner at OpenOnion, running marketing" from a mail
    where the owner listed Ody's roles, and followed the person template."""
    owner = instructions("investigate", page_kind="person", owner=True)
    person = instructions("investigate", page_kind="person")
    assert "# Your own page" in owner and "# Your own page" not in person
    assert "# Your own page" not in instructions("maintain") and "# Your own page" not in instructions("init")
    assert len(owner) <= 15_000
    for text in (owner, person):   # the role rule is for every person, the owner included
        assert "A role in a list the user writes about someone else is that person's" in text
    for rule in ("what they are working on now", "coding", "Open threads", "not history",
                 "**the user states them about"):
        assert rule in owner, rule


def test_the_owner_flag_on_the_page_item_is_what_composes_it(tmp_path):
    from connectonion.rem.runner import task_prompt
    page = {"role": "page", "record": "people/aaron.md", "text": "# Aaron", "owner": True}
    task_prompt(tmp_path, [page], "investigate")
    assert "# Your own page" in (tmp_path / "instructions.md").read_text()
    task_prompt(tmp_path, [{**page, "owner": False}], "investigate")
    assert "# Your own page" not in (tmp_path / "instructions.md").read_text()
