"""Synthetic regressions for quote retention, not semantic/source verification."""

import pytest

from connectonion.rem.page_review import dropped, restore_dropped


def page(line, sources='- [1] outlook:synthetic-1', lead=False):
    body = line if lead else '## Open threads\n' + line
    return f'# Nora\n\n{body}\n\n## Uncertainties\nUnknown\n\n## Sources\n{sources}\n'


@pytest.mark.parametrize('extension', ['.', ' before leaving', '。'])
@pytest.mark.parametrize('cite', ['[1]', '(2026-10-20) [personal] [1]'])
def test_extended_quote_keeps_exact_payload_at_same_cited_original(extension, cite):
    before = page('Nora received a promise: “I will reply after Friday” [1].', lead=True)
    after = page(f'- The user promised “I will reply after Friday{extension}” {cite}.')
    assert dropped(before, after) == []
    assert restore_dropped(before, after) == after


def test_extended_quote_resolves_renumbered_citation_and_markdown_link():
    before = page('“Send [Nora](../people/nora.md) the pilot price” [1].')
    after = page('“Send Nora the pilot price.” [7].', '- [7] outlook:synthetic-1')
    assert dropped(before, after) == []
    assert restore_dropped(before, after) == after


@pytest.mark.parametrize('old,new', [
    ('able to pay', 'unable to pay'),
    ('reply', 'replying'),
    ('reply after Friday', 'replyafter Friday'),
    ('reply only if approved', 'reply'),
    ('reply after Friday', 'Reply after Friday'),
])
def test_extension_never_erases_word_boundaries_spacing_case_or_qualifications(old, new):
    before = page(f'“{old}” [1].')
    after = page(f'“{new}” [1].')
    assert f'Dropped quote the page had: “{old}”' in dropped(before, after)
    result = restore_dropped(before, after)
    assert f'“{old}”' in result and f'“{new}”' in result
    assert dropped(before, result) == []


def test_separate_quotes_cannot_jointly_preserve_a_payload():
    before = page('“Send Nora the pilot price” [1].')
    after = page('“Send Nora” [1], then “the pilot price.” [1].')
    assert dropped(before, after)
    assert '“Send Nora the pilot price”' in restore_dropped(before, after)


@pytest.mark.parametrize('line,sources', [
    ('“Send Nora the pilot price.” [2].', '- [1] outlook:synthetic-1\n- [2] outlook:synthetic-2'),
    ('“Send Nora the pilot price.” [1].', '- [1] outlook:synthetic-2\n- [7] outlook:synthetic-1'),
    ('“Send Nora the pilot price.”', '- [1] outlook:synthetic-1'),
    ('“Send Nora the pilot price.” [2].', '- [1] outlook:synthetic-1'),
    ('“Send Nora the pilot price.” [1].', '- [1] outlook:synthetic-1\n- [1] outlook:synthetic-2'),
])
def test_source_identity_elsewhere_does_not_bind_the_extended_quote(line, sources):
    before = page('“Send Nora the pilot price” [1].')
    after = page(line, sources)
    assert 'Dropped quote the page had: “Send Nora the pilot price”' in dropped(before, after)
    assert '“Send Nora the pilot price”' in restore_dropped(before, after)


def test_missing_original_definition_cannot_authorize_extension():
    before = page('“Send Nora the pilot price” [2].')
    after = page('“Send Nora the pilot price.” [1].')
    assert dropped(before, after)


def test_placeholder_is_not_an_original_identity_for_quote_extension():
    before = page('“Send Nora the pilot price” [1].', '- [1] Unknown')
    after = page('“Send Nora the pilot price.” [1].', '- [1] Unknown')
    assert dropped(before, after)


def test_each_old_quote_occurrence_needs_its_original_identity():
    before = page('“Send Nora the pilot price” [1].\n“Send Nora the pilot price” [2].',
                  '- [1] outlook:synthetic-1\n- [2] outlook:synthetic-2')
    after = page('“Send Nora the pilot price.” [1].',
                 '- [1] outlook:synthetic-1\n- [2] outlook:synthetic-2')
    assert dropped(before, after)


def test_another_quote_citation_on_same_line_cannot_supply_continuity():
    before = page('“Send Nora the pilot price” [1].')
    after = page('“Send Nora the pilot price.” [2]. “A separate instruction” [1].',
                 '- [1] outlook:synthetic-1\n- [2] outlook:synthetic-2')
    assert dropped(before, after)


def test_genuinely_lost_lead_is_restored_before_content_sections():
    before = page('Nora received a promise: “I will reply after Friday” [1].', lead=True)
    after = page('- Await a response [1].')
    restored = restore_dropped(before, after)
    assert restored.index('Nora received a promise') < restored.index('## Open threads')
    assert '## Uncertainties\nUnknown\nNora received' not in restored
    assert '- Await a response [1].' in restored
    assert dropped(before, restored) == []
    assert restore_dropped(before, restored) == restored


def test_unchanged_quote_and_explicit_exemption_keep_existing_behavior():
    before = page('“Send Nora the pilot price” [1].')
    assert dropped(before, before) == []
    assert restore_dropped(before, before) == before
    after = page('- Await a response [1].')
    assert dropped(before, after, {'Send Nora the pilot price'}) == []
    assert restore_dropped(before, after, {'Send Nora the pilot price'}) == after
