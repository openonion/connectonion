"""Agent configuration and mutable Logger state can have separate roots."""

from connectonion import Agent
from tests.utils.mock_helpers import MockLLM


def test_state_dir_redirects_logger_without_moving_agent_configuration(tmp_path):
    config_dir = tmp_path / "config"
    state_dir = tmp_path / "state"

    agent = Agent(
        name="isolated",
        llm=MockLLM(),
        log=False,
        co_dir=config_dir,
        state_dir=state_dir,
    )

    assert agent.co_dir == config_dir
    assert agent.logger.co_dir == state_dir
    assert agent.logger.log_file_path == state_dir / "logs" / "isolated.log"
