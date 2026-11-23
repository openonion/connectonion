"""A privacy mark that opens a line is written after the words it labels, where the reader reads marks (#3410)."""
from connectonion.rem.page_review import trail_privacy_marks


def test_a_leading_mark_moves_after_its_sentence_and_before_its_sources():
    assert trail_privacy_marks("- [sensitive] Health detail. [1]") == "- Health detail [sensitive]. [1]"
    assert trail_privacy_marks("[personal] Lives near the park [2][3]") == "Lives near the park [personal] [2][3]"
    assert trail_privacy_marks("- ［sensitive］ 身体不适。 [1]") == "- 身体不适 ［sensitive］。 [1]"


def test_a_line_of_several_sentences_keeps_its_leading_mark_so_every_sentence_stays_labelled():
    line = "- [sensitive] First detail. Second detail. [1]"
    assert trail_privacy_marks(line) == line


def test_trailing_marks_and_code_are_left_alone():
    text = "- Already trailing [sensitive]. [1]\n```\n[sensitive] in code\n```\n"
    assert trail_privacy_marks(text) == text
