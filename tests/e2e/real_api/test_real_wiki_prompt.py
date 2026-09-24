"""The prompt-evaluation scenarios as opt-in tests, on the default model.

`wiki_prompt_eval.py` is the same thing as a scorecard across models; this
makes each scenario an individually selectable test so a prompt change can be
checked against one behaviour at a time:

    pytest tests/e2e/real_api/test_real_wiki_prompt.py -m real_api -k decision_vs_proposal
"""

import pytest

from tests.e2e.real_api.wiki_prompt_eval import SCENARIOS, run_scenario

pytestmark = [pytest.mark.real_api, pytest.mark.provider_cli, pytest.mark.timeout(600)]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_prompt_scenario_on_default_model(scenario, tmp_path):
    from connectonion.wiki.config import default_config
    result = run_scenario(scenario, default_config()["model"], tmp_path)
    assert result["passed"], "\n".join(result["failures"]) + f"\nnotebook: {result['root']}"
