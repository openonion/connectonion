"""Prompt evaluation for the wiki-maintain Skill: scenarios × models → scorecard.

Each scenario is a small synthetic session (or two) with a known right answer
about what the notebook should say afterwards, checked deterministically. It is
run through the real maintainer (`run_sync` with no injected runner), so what is
measured is the Skill's judgement on a given model, not the orchestration.

    python -m tests.e2e.real_api.wiki_prompt_eval --models gpt-5.3-codex-spark,gpt-5.6-luna
    python -m tests.e2e.real_api.wiki_prompt_eval --only decision_vs_proposal --models gpt-5.5

Prints one row per (model, scenario) and writes the scorecard as JSON next to
the notebooks so a failing page can be read. Costs real model calls (opt-in).
"""

import argparse
import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from connectonion.wiki import service
from connectonion.wiki.config import prepare, set_config
from connectonion.wiki.files import Notebook

STAMP = datetime(2026, 9, 7, 5, tzinfo=timezone.utc)


def rollout(path: Path, messages, *, project="/work/demo", minutes_apart=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "session_meta", "payload": {"id": path.stem, "cwd": project, "originator": "codex_cli_rs"}}]
    for index, (role, text) in enumerate(messages):
        when = (STAMP + timedelta(minutes=index * minutes_apart)).isoformat().replace("+00:00", "Z")
        rows.append({"timestamp": when, "type": "response_item",
                     "payload": {"type": "message", "role": role,
                                 "content": [{"type": "input_text" if role == "user" else "output_text",
                                              "text": text}]}})
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


@dataclass
class Scenario:
    name: str
    passes: list          # each pass: list of (session_name, messages); one run_sync per pass
    check: object         # check(notebook) -> list of failure strings
    seed: dict = field(default_factory=dict)  # pages to write before the first pass


def pages(notebook, category=""):
    return {record: notebook.read(record) for record in notebook.list(category)}


def all_text(notebook):
    return "\n".join(pages(notebook).values()).lower()


def structure_failures(notebook):
    failures = []
    for record, text in pages(notebook).items():
        if not text.lstrip().startswith("#"):
            failures.append(f"{record}: no title line")
        if "sources" not in text.lower():
            failures.append(f"{record}: no Sources line")
    return failures


def check_people_and_agenda(nb):
    f = structure_failures(nb)
    people = pages(nb, "people")
    if not any("alice" in r for r in people):
        f.append("no people page for Alice")
    elif not any("email" in t.lower() for t in people.values()):
        f.append("Alice's stated email preference not recorded")
    agenda = pages(nb, "agenda")
    if not any("proposal" in t.lower() and ("2026-09-11" in t or "friday" in t.lower()) for t in agenda.values()):
        f.append("promise to send the proposal by Friday not on the agenda")
    if any("alice" in t.lower() and ("introvert" in t.lower() or "personality" in t.lower()) for t in people.values()):
        f.append("invented a personality trait")
    return f


def check_decision_vs_proposal(nb):
    f = structure_failures(nb)
    decisions = pages(nb, "decisions")
    if not any("postgres" in t.lower() for t in decisions.values()):
        f.append("Postgres decision missing")
    for record, text in decisions.items():
        title = text.splitlines()[0].lower() if text else ""
        if "redis" in title:
            f.append(f"{record}: an undecided suggestion (Redis) became a decision")
    text = all_text(nb)
    if "redis" in text and not any(word in text for word in ("not decided", "undecided", "suggest", "not adopted",
                                                               "open", "proposed", "not now", "deferred")):
        f.append("Redis mentioned without marking it as merely suggested")
    return f


def check_question_is_not_maintenance(nb):
    f = structure_failures(nb)
    decisions = pages(nb, "decisions")
    if len(decisions) != 1:
        f.append(f"expected the one seeded decision page, found {sorted(decisions)}")
    text = all_text(nb)
    if "markdown" not in text:
        f.append("the seeded Markdown decision was lost")
    if "sqlite" in text and not any(word in text for word in ("not", "guess", "incorrect", "wrong", "alternative")):
        f.append("the assistant's wrong guess (SQLite) was recorded as fact")
    return f


def check_chinese(nb):
    f = structure_failures(nb)
    text = "\n".join(pages(nb).values())
    if "Emma" not in text and "emma" not in text.lower():
        f.append("Emma not recorded")
    if "355" not in text:
        f.append("floor price 355 not recorded")
    if not any(word in text for word in ("不再", "自己改价", "自己定价", "自行定价", "自行改价", "手动", "Emma 自")):
        f.append("the rule that Emma prices herself now is missing")
    if "清洁" not in text and "cleaning" not in text.lower():
        f.append("the 'net of cleaning fee' qualification was dropped")
    # The user wrote Chinese; the notebook must answer in Chinese, names untranslated.
    chinese = sum(1 for ch in text if "一" <= ch <= "鿿")
    if chinese < 20:
        f.append("the page was written in English for a Chinese source")
    return f


def check_dedupe(nb):
    f = structure_failures(nb)
    people = {r: t for r, t in pages(nb, "people").items() if "alice" in r}
    if len(people) != 1:
        f.append(f"expected one Alice page, found {sorted(people)}")
    text = "\n".join(people.values()).lower()
    if "email" not in text or "singapore" not in text:
        f.append("facts from the two sessions were not merged into one page")
    return f


def check_principle_vs_preference(nb):
    f = structure_failures(nb)
    principles = pages(nb, "principles")
    if not any("blog" in t.lower() for t in principles.values()):
        f.append("the explicitly adopted rule (every release gets a blog post) is not a principle")
    if any("dark mode" in t.lower() for t in principles.values()):
        f.append("a passing preference (dark mode) became a principle")
    return f


def check_noise(nb):
    f = structure_failures(nb)
    text = all_text(nb)
    if not ("wiki" in text and "lore" in text):
        f.append("the one real decision (wiki, not lore) is missing")
    if len(pages(nb)) > 3:
        f.append(f"{len(pages(nb))} pages from a session with one fact: noise became content")
    if "42 passed" in text or "running tests" in text:
        f.append("tool chatter was written down")
    return f


def check_correction(nb):
    f = structure_failures(nb)
    text = all_text(nb)
    if "inspectab" not in text:
        f.append("the correction (inspectability) was not adopted")
    aurora = [r for r in pages(nb, "decisions") if "aurora" in r]
    if len(aurora) > 1:
        f.append(f"the correction produced a second Aurora decision page: {aurora}")
    return f


SCENARIOS = [
    Scenario("people_and_agenda", [[("s1", [
        ("user", "Met Alice Chen today, product lead at Example Co. She told me she prefers email over calls. "
                 "I promised to send her the Aurora storage proposal by Friday 2026-09-11."),
        ("assistant", "Noted: Alice Chen prefers email; proposal due Friday 2026-09-11.")])]], check_people_and_agenda),
    Scenario("decision_vs_proposal", [[("s1", [
        ("user", "For Beacon we're choosing Postgres for the ledger. Bob suggested we could also try Redis for "
                 "caching, but we haven't decided that."),
        ("assistant", "Understood. Should I set up Redis for caching now as well?"),
        ("user", "No, not now.")])]], check_decision_vs_proposal),
    Scenario("question_is_not_maintenance", [[("s1", [
        ("user", "What did we decide about Aurora's storage?"),
        ("assistant", "I think you went with SQLite for Aurora, if I remember correctly.")])]],
             check_question_is_not_maintenance,
             seed={"decisions/aurora-storage.md": "# Aurora stores notes as Markdown, not SQLite\n\n"
                                                  "Decided 2026-09-02 for inspectability.\n\nSources: codex:seed:0 (2026-09-02)\n"}),
    Scenario("chinese", [[("s1", [
        ("user", "客户 Emma 的 6 Portman 房源，我们定的地板价是每晚 355 澳元，这是净额，不含清洁费。"
                 "她从 9 月 7 日起自己改价，我们不再主动调价，只按她拍板的执行。"),
        ("assistant", "记下了：地板价 355 澳元/晚（净额），9 月 7 日起 Emma 自己定价。")])]], check_chinese),
    Scenario("dedupe_across_sessions", [
        [("s1", [("user", "Alice Chen from Example Co prefers email over calls, she said so."),
                 ("assistant", "Noted.")])],
        [("s2", [("user", "By the way Alice Chen is based in Singapore, so mornings here are her afternoons."),
                 ("assistant", "Noted.")])]], check_dedupe),
    Scenario("principle_vs_preference", [[("s1", [
        ("user", "From now on every release gets a blog post, no exceptions. That's a rule for us."),
        ("assistant", "Understood, adopted as a rule."),
        ("user", "Also I'd rather use dark mode in the editor today."),
        ("assistant", "Sure.")])]], check_principle_vs_preference),
    Scenario("noise_and_tool_chatter", [[("s1", [
        ("user", "run the tests"),
        ("assistant", "Running tests... 42 passed in 3.2s. Let me check the lint next."),
        ("assistant", "Lint is clean. I also reformatted two files."),
        ("user", "ok. by the way, we decided the product is named wiki, not lore — that's final."),
        ("assistant", "Noted: wiki, not lore."),
        ("user", "now bump the version"),
        ("assistant", "Bumped to 1.8.4 in pyproject and _version.py.")])]], check_noise),
    Scenario("correction_supersedes", [
        [("s1", [("user", "For Aurora we chose Markdown over SQLite because portability matters most."),
                 ("assistant", "Noted.")])],
        [("s2", [("user", "Correction: Aurora's reason is inspectability, not portability. Keep Markdown; "
                          "SQLite was never adopted."),
                 ("assistant", "Noted.")])]], check_correction),
]


def run_scenario(scenario: Scenario, model: str, workdir: Path) -> dict:
    root, sessions = workdir / "wiki", workdir / "sessions"
    prepare(root)
    set_config(root, ["model", model])
    original = service.codex_sessions_root, service.claude_projects_root
    service.codex_sessions_root = lambda: sessions
    service.claude_projects_root = lambda: workdir / "no-claude"  # never the operator's own transcripts
    try:
        service.approve_sources(root)
        notebook = Notebook(root)
        for record, text in scenario.seed.items():
            notebook.write(record, text)
        records, started = [], time.monotonic()
        for index, batch in enumerate(scenario.passes):
            for session, messages in batch:
                rollout(sessions / f"2026/09/07/rollout-{session}.jsonl", messages)
            records.append(service.run_sync(root))
        seconds = round(time.monotonic() - started, 1)
        failures = scenario.check(notebook)
        for record in records:
            if record["outcome"] != "completed":
                failures.append(f"run {record['outcome']}: {record.get('error')}")
            for refusal in record.get("refusals", []):
                failures.append(f"refused: {refusal}")
            if failures and record.get("report"):
                failures.append(f"model said: {record['report'][:300]!r}")
        usage = {k: sum((r.get("usage") or {}).get(k, 0) for r in records)
                 for k in ("input_tokens", "output_tokens")}
        return {"model": model, "scenario": scenario.name, "passed": not failures, "failures": failures,
                "pages": notebook.list(), "seconds": seconds, "usage": usage, "root": str(root)}
    finally:
        service.codex_sessions_root, service.claude_projects_root = original


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="gpt-5.3-codex-spark")
    parser.add_argument("--only", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="co-wiki-prompt-eval-"))
    results = []
    for model in args.models.split(","):
        for scenario in SCENARIOS:
            if args.only and scenario.name not in args.only.split(","):
                continue
            result = run_scenario(scenario, model, out / model / scenario.name)
            results.append(result)
            mark = "PASS" if result["passed"] else "FAIL"
            print(f"{mark} {model:22} {scenario.name:28} {result['seconds']:6.1f}s "
                  f"in={result['usage']['input_tokens']:>7} out={result['usage']['output_tokens']:>5} "
                  f"pages={len(result['pages'])}", flush=True)
            for failure in result["failures"]:
                print(f"       - {failure}", flush=True)
    (out / "scorecard.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} passed; notebooks and scorecard under {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
