"""Which agent loop runs the task — our own, or a native coding agent's.

`--model` answers "who supplies the tokens". It was also answering "who runs
the loop", which is a different question with different answers: Ollama is a
provider with no loop of its own, while Codex and Claude Code are loops that
come with their own tools, sandbox and approval vocabulary. One flag cannot
carry both, and conflating them is why the only way to reach Codex was to pay
for a full turn of our own model first, just to have it decide to delegate.

So: `--harness` picks the loop, `--model` picks the tokens. For a delegated
harness the model name is the provider's own (`gpt-5.6-luna`), because the
delegate is talking to its own account, not through ours.

What each harness does NOT share is normalised here rather than at every call
site, so a caller — the wiki runner, a script, CI — only ever speaks one
protocol: `co ai --json --harness X /skill args` in, one envelope out.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

OURS = "ours"
DELEGATED = ("codex", "claude-code")
HARNESSES = (OURS, *DELEGATED)

# A delegated harness reaches its own account and knows only its own catalogue.
# `co/gemini-3.8-flash` names nothing there; passing it through would surface as
# the delegate's own opaque model error, several seconds and one process later.
OUR_MODEL_PREFIXES = ("co/", "ollama/", "groq/", "openrouter/", "grok/", "mistral/")

# Measured 2026-09-12 against codex-cli 0.147.x, verified on disk rather than
# taken from the model's own report: `workspace-write` reads ANYWHERE (it opened
# ~/.co/keys.env), writes only inside cwd and TMPDIR ($HOME and ~/projects were
# both refused with "operation not permitted"), and has no network. So the level
# is not the broad guard it sounds like — it scopes writes, nothing else.
SANDBOXES = ("read-only", "workspace-write", "danger-full-access")
DEFAULT_SANDBOX = "workspace-write"


def validate_sandbox(harness: str, sandbox: str) -> str | None:
    """Codex is the only delegate that takes a sandbox level from us."""
    if sandbox == DEFAULT_SANDBOX:
        return None
    if sandbox not in SANDBOXES:
        return f"Unknown sandbox {sandbox!r}. Use one of: {', '.join(SANDBOXES)}."
    if harness != "codex":
        return (f"--sandbox is a Codex setting; --harness {harness} manages its own "
                f"permissions. Drop --sandbox.")
    return None


def validate(harness: str, model: str | None) -> str | None:
    """The reason this combination cannot run, or None.

    `model` is None when the flag was not given — a real sentinel, not a
    comparison against our default: typing `--model co/gemini-3.8-flash`
    produces the same string our default does, so a comparison reads an
    explicit choice as silence and forwards nothing.
    """
    if harness not in HARNESSES:
        return f"Unknown harness {harness!r}. Use one of: {', '.join(HARNESSES)}."
    if harness == OURS or model is None:
        return None
    if model.startswith(OUR_MODEL_PREFIXES):
        example = {"codex": "gpt-5.6-luna, gpt-5.3-codex-spark",
                   "claude-code": "opus, sonnet"}[harness]
        return (
            f"--model {model} is one of our providers, but --harness {harness} runs on "
            f"its own subscription and its own model catalogue. Drop --model to use its "
            f"default, or name one of its models ({example})."
        )
    return None


def expand_skill(prompt: str) -> str:
    """Turn a leading `/name args` into the skill's own instructions, inline.

    A delegated harness cannot resolve `/name` itself: `.co/skills/` is
    ConnectOnion's convention and nothing registers it with Codex or Claude
    Code. Handing over the name alone hands over nothing.

    So the body travels in the prompt. The directory travels with it because a
    skill may reference a sibling script, and reads outside cwd are permitted
    (measured — see SANDBOXES above), so naming the directory is enough for the
    delegate to open what sits beside the SKILL.md.
    """
    if not prompt.startswith("/"):
        return prompt

    from ...skill_preflight import format_preflight_report, preflight_skills
    from .skills.loader import SKILLS_REGISTRY, get_skill, load_skills

    name, _, args = prompt[1:].partition(" ")
    if not SKILLS_REGISTRY:
        load_skills()
    info = get_skill(name)
    if not info:
        available = ", ".join(sorted(SKILLS_REGISTRY)) or "none are installed"
        raise ValueError(f"Skill '{name}' not found. Available: {available}")

    report = preflight_skills([(info.name, info.requirements)])
    if report.missing_required:
        raise ValueError(format_preflight_report(report) + "\nSkill did not start.")

    directory = Path(info.path).parent
    body = (
        f"Follow these instructions exactly. They are the skill `{info.name}`, "
        f"installed at {directory} — read sibling files there if the instructions "
        f"reference them.\n\n{info.load_content()}"
    )
    return f"{body}\n\n---\n## Arguments\n{args.strip()}" if args.strip() else body


def run(harness: str, prompt: str, model: str, *, cwd: str = "", timeout: int = 600,
        sandbox: str = DEFAULT_SANDBOX) -> dict:
    """Hand the task to a native coding agent; return our envelope's fields.

    Each delegate answers in its own JSON shape and with its own idea of what
    "finished" means — Codex reports `exit_code`, Claude Code does not, and
    neither uses our `natural` / `max_iterations` vocabulary. Translating here
    is what lets one caller read one envelope whichever harness ran.
    """
    cwd = cwd or str(Path.cwd())
    text = expand_skill(prompt)

    if harness == "codex":
        from ...useful_tools.codex import codex
        # approval="auto": nothing is watching a delegated one-shot, and the
        # tool fails closed on an unexpected approval callback rather than
        # hanging on a prompt nobody will answer.
        raw = codex(prompt=text, cwd=cwd, sandbox=sandbox, model=model,
                    timeout=timeout, approval="auto")
    else:
        from ...useful_tools.claude_code import _run_claude_code
        raw = _run_claude_code(prompt=text, cwd=cwd, model=model, timeout=timeout)

    try:
        answer = json.loads(raw)
        if not isinstance(answer, dict):
            raise ValueError("Delegate result is not an object")
    except (TypeError, ValueError):
        # A delegate that did not answer in its own format is a failure to
        # report, not a result to parse: keep what it did say.
        return {"result": None, "outcome": "error", "error": str(raw)[:2000], "usage": None}

    error = answer.get("error")
    exit_code = answer.get("exit_code")
    failed = bool(error) or (isinstance(exit_code, int) and exit_code != 0)
    usage = dict(answer["usage"]) if isinstance(answer.get("usage"), dict) else {}
    cost = answer.get("total_cost_usd")
    if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0:
        usage["cost"] = cost
    return {
        "result": answer.get("last_message") if harness == "codex" else answer.get("result"),
        "outcome": "error" if failed else "natural",
        "error": error or (f"{harness} exited {exit_code}" if failed else None),
        # An empty usage means the delegate reported nothing, which is what
        # `null` says. Passing `{}` on lets a caller read "no tokens" out of it.
        "usage": usage or None,
        "session_id": answer.get("session_id"),
    }
