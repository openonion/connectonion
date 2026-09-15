"""Stage and source are two axes, and composing them is what keeps them apart."""

import pytest

from connectonion.wiki.files import WikiError
from connectonion.wiki.runner import instructions, maintenance_instructions
from connectonion.wiki.extract import extraction_instructions


def test_a_stage_that_reads_a_source_is_handed_that_source():
    """Four sources times four stages would be sixteen files; composing is seven."""
    for stage in ("extract", "maintain", "investigate"):
        alone, composed = instructions(stage), instructions(stage, "codex")
        assert len(composed) > len(alone)
        assert alone in composed                       # the stage is intact
        assert "wiki-source-codex" in composed         # the source was appended


def test_abstract_refuses_a_source_because_its_input_is_pages():
    """The check on whether the split is real: a stage reading pages must not
    know which store they came from."""
    assert instructions("abstract", "codex") == instructions("abstract")
    assert "wiki-source-codex" not in instructions("abstract", "codex")


def test_a_source_nobody_wrote_a_file_for_still_runs_on_the_stage_alone():
    assert instructions("extract", "no-such-source") == instructions("extract")


def test_an_unknown_stage_is_refused_by_name():
    with pytest.raises(WikiError) as caught:
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
    owners = [p.parent.name for p in useful_skills_dir().glob("wiki-*/SKILL.md")
              if any(line.rstrip() == "# A person's page"
                     for line in p.read_text(encoding="utf-8").splitlines())]
    assert owners == ["wiki-page-person"], owners
