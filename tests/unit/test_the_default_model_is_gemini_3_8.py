"""The 1.8.2 product default is Gemini 3.8 everywhere it can be omitted.

The managed gateway, direct-Gemini client, Agent, llm_do, transcription, and
`co ai` must agree. Explicit OpenAI and Gemini 3.7 selections stay untouched:
3.7 is a selectable rollback model, never an implicit fallback.
"""

import inspect
import re
from pathlib import Path

from connectonion import Agent, llm_do, transcribe
from connectonion.cli.co_ai.agents.registry import SUBAGENTS
from connectonion.cli.co_ai.agent import create_agent
from connectonion.cli.commands.project_cmd_lib import configure_env_for_provider
from connectonion.core.llm import GeminiLLM
from connectonion.core.usage import (
    DEFAULT_DIRECT_GEMINI_MODEL,
    DEFAULT_MODEL,
    FREE_MANAGED_MODELS,
)


MANAGED_DEFAULT = "co/gemini-3.8-flash"
DIRECT_DEFAULT = "gemini-3.8-flash"
ROLLBACK = "co/gemini-3.7-flash"
ROOT = Path(__file__).resolve().parents[2]


def _model_default(fn):
    return inspect.signature(fn).parameters["model"].default


class TestOmittedModelSelectsGemini38:

    def test_the_shared_constants(self):
        assert DEFAULT_MODEL == MANAGED_DEFAULT
        assert DEFAULT_DIRECT_GEMINI_MODEL == DIRECT_DEFAULT

    def test_agent(self):
        assert _model_default(Agent.__init__) == MANAGED_DEFAULT

    def test_llm_do(self):
        assert _model_default(llm_do) == MANAGED_DEFAULT

    def test_co_ai(self):
        assert _model_default(create_agent) == MANAGED_DEFAULT

    def test_transcribe(self):
        assert _model_default(transcribe) == MANAGED_DEFAULT

    def test_direct_gemini(self):
        assert _model_default(GeminiLLM.__init__) == DIRECT_DEFAULT

    def test_every_entry_point_agrees(self):
        assert {
            _model_default(Agent.__init__),
            _model_default(llm_do),
            _model_default(create_agent),
            _model_default(transcribe),
            f"co/{_model_default(GeminiLLM.__init__)}",
        } == {MANAGED_DEFAULT}

    def test_model_picker_puts_the_default_first(self):
        assert FREE_MANAGED_MODELS[0] == MANAGED_DEFAULT

    def test_generated_managed_configuration_uses_the_default(self):
        generated = configure_env_for_provider("connectonion", "managed")
        assert f"MODEL={MANAGED_DEFAULT}" in generated

    def test_built_in_auto_clients_use_the_default(self):
        assert {config["model"] for config in SUBAGENTS.values()} == {MANAGED_DEFAULT}


class TestExplicitModelsStayExplicit:

    def test_openai_is_still_selectable(self):
        agent = Agent("t", api_key="fake_key", model="o4-mini")
        assert agent.llm.model == "o4-mini"

    def test_gemini_37_is_still_a_rollback(self):
        agent = Agent("t", api_key="fake_key", model=ROLLBACK)
        assert agent.llm.model == "gemini-3.7-flash"

    def test_default_and_rollback_are_advertised(self):
        assert MANAGED_DEFAULT in FREE_MANAGED_MODELS
        assert ROLLBACK in FREE_MANAGED_MODELS


class TestNoGemini37DefaultRemains:
    """Guard the supported source/docs surface without rewriting history."""

    def test_no_source_literal_assigns_37_as_a_model_default(self):
        assignment = re.compile(
            r"model\s*(?::\s*str\s*)?=\s*['\"](?:co/)?gemini-3\.7-flash"
        )
        offenders = []
        for path in (ROOT / "connectonion").rglob("*"):
            if path.suffix not in {".py", ".md"}:
                continue
            if "design-decisions" in path.parts:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if assignment.search(line) and "rollback" not in line.lower():
                    offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
        assert offenders == []

    def test_active_docs_do_not_call_37_the_default(self):
        descriptions = []
        paths = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
        for path in paths:
            relative = path.relative_to(ROOT)
            if relative.parts[:2] in {("docs", "blog"), ("docs", "design-decisions")}:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                lower = line.lower()
                if (
                    "gemini-3.7-flash" in lower
                    and "default" in lower
                    and "rollback" not in lower
                ):
                    descriptions.append(f"{relative}:{number}: {line.strip()}")
        assert descriptions == []
