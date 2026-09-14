"""Opt-in runtime acceptance; never downloads models or falls back to cloud.

OLLAMA_TEST_MODEL=ollama/qwen3.5:2b pytest -m real_api \
    tests/e2e/real_api/test_real_ollama.py -v
Set OLLAMA_BASE_URL if the daemon is not on localhost:11434.
For tool validation, additionally set OLLAMA_TEST_TOOL_MODEL to a verified
model/template (it may be the same model). Record exact runtime/quantization.
"""
import os

import pytest
from pydantic import BaseModel

from connectonion import Agent, llm_do

pytestmark = [pytest.mark.real_api, pytest.mark.local_api, pytest.mark.timeout(600)]


@pytest.fixture
def model():
    name = os.getenv('OLLAMA_TEST_MODEL')
    if not name:
        pytest.skip('Set OLLAMA_TEST_MODEL to opt into local model inference')
    return name


def test_real_summary(model):
    text = llm_do('用中文简述：[s1] 日志修复完成，测试通过。部署尚未执行。',
                  model=model, max_tokens=1024, reasoning_effort="none")
    assert text and '部署' in text


def test_real_structured_note(model):
    class Note(BaseModel):
        completed_source_ids: list[str]
        pending_source_ids: list[str]
        current_database: str

    result = llm_do(
        '[s1] Command failed. [s2] Retry passed all tests. '
        '[s3] Proposed migration to Redis, not executed. '
        '[s4] Correction: keep SQLite. [s5] Deploy tomorrow, not done. '
        'Extract completed/pending source IDs without brackets and current_database.',
        model=model, output=Note, max_tokens=2048, reasoning_effort="none",
    )
    assert result.current_database.lower() == 'sqlite'
    assert 's2' in result.completed_source_ids
    assert 's3' not in result.completed_source_ids
    assert 's5' not in result.completed_source_ids
    assert 's5' in result.pending_source_ids


def test_real_tool_round_trip(tmp_path):
    model = os.getenv('OLLAMA_TEST_TOOL_MODEL')
    if not model:
        pytest.skip('Set OLLAMA_TEST_TOOL_MODEL to test runtime tool parsing')
    called = []

    def lookup_code() -> str:
        """Return the code. You must call this tool to discover it."""
        called.append(True)
        return 'LOCAL-5837'

    agent = Agent('ollama-test', model=model, tools=[lookup_code],
                  quiet=True, log=False, co_dir=tmp_path, max_iterations=3)
    answer = agent.input('Call lookup_code and return its exact result.')
    assert called, 'No tool executed; text resembling a call is not sufficient'
    assert 'LOCAL-5837' in answer
