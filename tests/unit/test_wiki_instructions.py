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
