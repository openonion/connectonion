"""Private sentences out of a handoff before the sender sees the preview (#2500).

Masking takes out what has a shape: addresses, numbers, names co rem knows. Health, visa and family
details have no shape, and on 2026-10-14 they reached students and a colleague in the AI's replies, which had read the sender's mail and co rem pages. A model reads every sentence that
would leave, the sender's and the AI's, and each private one is replaced by "[removed: <why>]". It
errs towards removing: a work sentence lost costs the reader a little, a private one kept goes to
someone it should not. The sender sees where in the preview and can put any back with --edit.
"""

import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

# The sender's own coding agent reads it, on their own plan: the session came from it, so it is there
# and signed in (Aaron, 2026-10-14). ConnectOnion's default model only when neither is installed.
READERS = {"codex": "Codex", "claude-code": "Claude Code", "co": "ConnectOnion's default model"}
BATCH_CHARS = 40_000
TIMEOUT = 900   # seconds for one batch
CATEGORIES = ("health", "family and relationships", "travel and home", "money", "legal and immigration",
              "about someone else")

PROMPT = """The text below is about to be handed to a colleague so they can continue the work. Find
every sentence that tells something private about a person: the sender, the AI's user, or anyone else.

Categories:
- health: illness, tests, appointments, sleep, dentist, therapy, medication
- family and relationships: relatives, partners, friends, who is related to whom
- travel and home: personal trips, flights, where someone lives or stays, private schedules
- money: personal finances, salary, debts, personal invoices, fundraising, investors, deal terms, equity
- legal and immigration: visas, residency, lawyers, disputes
- about someone else: a third party's own private details: their personal life, situation or plans,
  what they confided, their contact details

When unsure, include it: a work sentence removed by mistake costs the reader little; a private one
kept goes to someone it should not.

Not private, leave these:
- the work itself: code, products, tests, bugs, releases, the price of software, API costs, usage
  quotas of the tools being used
- a person named only as the subject of the work: "Kim's page failed in round 5", "the phone rule
  put Sam's number on Alex's page" is about the software (names are masked separately)
- someone's role in the work ("the student team lead", "the events coordinator")
- the work between {keep} and the people they work with: what was sent, asked or agreed about the work
  (their private matters are still private)
- a category named only as a category ("labels for health, visa and family" in a design)

Also list every personal name in the text of someone other than {keep}, as written, people only
(not products, companies or AI models).

Each sentence is numbered [N]; answer with the numbers, as JSON only, in this shape:
{{"private": [{{"id": 12, "categories": ["health"]}}], "names": ["…"]}}

{text}"""


class Hit(BaseModel):
    id: int
    categories: list[str] = Field(description=f"One or more of: {', '.join(CATEGORIES)}")


class Found(BaseModel):
    private: list[Hit] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list, description="Personal names of third parties, as written")


SPLIT = re.compile(r"(?<=[。！？；!?])|(?<=[.!?])\s+(?=\S)")


def sentences(text: str) -> list[str]:
    """Each line, cut after a sentence's end: the unit one person would take out."""
    return [s.strip() for line in text.split("\n") for s in SPLIT.split(line) if s.strip()]


def reader(agent: str = "") -> str:
    """The agent the session came from when it is installed, else the other, else ConnectOnion's model."""
    from ..useful_tools.claude_code import _claude_command
    from ..useful_tools.codex import _base_command
    installed = {"codex": bool(_base_command()), "claude-code": bool(_claude_command()[0])}
    first = "claude-code" if agent == "claude" else "codex"
    return next((r for r in (first, *installed) if installed[r]), "co")


def find(texts: dict, keep=(), agent: str = "") -> tuple[dict, list[str]]:
    """{key: text} → ({key: [[sentence, categories], …]}, names). Sentences without a letter are not asked about."""
    units = [(key, s) for key, text in texts.items() for s in sentences(text) if re.search(r"[^\W\d_]", s)]
    batches, size = [[]], 0
    for n, unit in enumerate(units):
        if size > BATCH_CHARS:
            batches, size = batches + [[]], 0
        batches[-1].append((n, unit))
        size += len(unit[1])
    by = reader(agent)
    with ThreadPoolExecutor(max_workers=4) as pool:
        answers = list(pool.map(lambda batch: _ask(batch, keep, by), [b for b in batches if b]))
    found, names = {}, []
    for answer in answers:
        names += answer.names
        for hit in answer.private:
            if 0 <= hit.id < len(units):
                key, sentence = units[hit.id]
                found.setdefault(key, []).append([sentence, [c for c in hit.categories if c in CATEGORIES] or ["private"]])
    return found, sorted(set(names) - set(keep), key=len, reverse=True)


def _ask(batch: list, keep, by: str) -> Found:
    lines, last = [], None
    for n, (key, sentence) in batch:
        if key != last:
            lines.append(f"--- {_label(key)}")
            last = key
        lines.append(f"[{n}] {sentence}")
    prompt = PROMPT.format(keep=", ".join(k for k in keep if k) or "the sender", text="\n".join(lines))
    if by == "co":
        from ..llm_do import llm_do
        return llm_do(prompt, output=Found)
    return Found.model_validate_json(_json_in(_agent_answer(prompt, by)))


def _agent_answer(prompt: str, by: str) -> str:
    """One turn of Codex or Claude Code in an empty folder, with nothing it may change or run."""
    from ..useful_tools.claude_code import _run_claude_code
    from ..useful_tools.codex import codex
    with tempfile.TemporaryDirectory() as empty:
        if by == "codex":
            answer = json.loads(codex(prompt, cwd=empty, sandbox="read-only", approval="deny", timeout=TIMEOUT))
            text = answer.get("last_message")
        else:
            answer = json.loads(_run_claude_code(prompt=prompt, session_id="", cwd=empty, permission_mode="default",
                                                 model="", timeout=TIMEOUT, agent=None, workspace=None))
            text = answer.get("result")
    if answer.get("error") or not text:
        raise RuntimeError(f"{READERS[by]} could not read the handoff for private sentences: "
                           f"{answer.get('error') or 'no answer'}")
    return text


def _json_in(text: str) -> str:
    return text[text.index("{"):text.rindex("}") + 1]


def _label(key: tuple) -> str:
    if isinstance(key[0], int):
        return f"message {key[0] + 1}, {'the sender' if key[1] == 'user' else 'the AI'}"
    return f"the report on top, {key[0].replace('_', ' ')}"


def remove(text: str, found: list) -> str:
    for sentence, categories in found:
        text = text.replace(sentence, f"[removed: {', '.join(categories)}]")
    return text
