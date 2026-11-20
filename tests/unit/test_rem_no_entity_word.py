"""The owner's naming decision (docs/cli/rem-naming.md, #3140): REM's pages never call a thing an
"entity". Org pages said "针对该实体的义务" 12 times on 5 pages (rc36 hunt, #3165) because the writer
skills said "the entity" throughout and the translator rendered it as 实体. The `Legal entity` and
`Signing entity` Facts labels are data keys code reads, so they stay; prose never says it."""
import re
from pathlib import Path

from connectonion.rem.runner import language_rules

SKILLS = Path(__file__).resolve().parents[2] / "connectonion" / "useful_skills"
LABELS = re.compile(r"`?(Legal|Signing) entity`?:?", re.I)
BAN = re.compile(r"never 实体|\"the entity\" in prose|entity in prose", re.I)


def _prose_uses(text: str) -> list[str]:
    hits = []
    for line in text.splitlines():
        if BAN.search(line):
            continue
        line = LABELS.sub("", line)
        if re.search(r"\bentit(y|ies)\b|实体", line, re.I):
            hits.append(line.strip())
    return hits


def test_writer_skills_never_ask_for_the_word_entity():
    hits = {p.parent.name: _prose_uses(p.read_text(encoding="utf-8"))
            for p in SKILLS.glob("rem*/SKILL.md")}
    assert {name: lines for name, lines in hits.items() if lines} == {}


def test_every_writer_and_the_translator_are_told_never_to_write_it():
    rules = language_rules()
    assert "never 实体" in rules
    assert "Legal entity" in rules  # the label is named as the exception, so it isn't translated away


def test_the_org_skill_names_what_to_write_instead():
    text = (SKILLS / "rem-page-org" / "SKILL.md").read_text(encoding="utf-8")
    assert "这家公司" in text and "该组织" in text
