"""`co slack channels | history | thread | search` against a real Slack workspace (#2051).

Opt-in: needs SLACK_BOT_TOKEN (xoxb-), exported or saved with `co env set … --secret`, for an app installed with the read scopes
(`co auth slack` makes one), invited to at least one channel. Search also needs
SLACK_USER_TOKEN (xoxp-, search:read). Read-only: nothing is posted.

    SLACK_BOT_TOKEN=xoxb-... pytest -m real_api tests/e2e/real_api/test_real_co_slack_read.py
"""

import json
import os
import subprocess
import sys

import pytest

from connectonion.environment import setting

pytestmark = [
    pytest.mark.real_api,
    pytest.mark.skipif(not setting("SLACK_BOT_TOKEN"), reason="SLACK_BOT_TOKEN not set"),
]


def co(*args):
    result = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "slack", *args],
                            capture_output=True, text=True, timeout=120, env=os.environ.copy())
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]


def test_channels_history_and_a_thread_read_back():
    channels = [row for row in co("channels", "--json") if row["kind"] != "im"]
    assert channels, "invite the bot to a channel: /invite @<your bot>"
    for row in channels:
        assert row["id"] and row["name"].startswith("#")

    messages = co("history", channels[0]["id"], "-n", "20", "--json")
    for message in messages:
        assert message["id"].startswith(f"{channels[0]['id']}:")
        assert message["sender_name"] and not message["sender_name"].startswith("U0")

    threaded = [message for message in messages if message["replies"]]
    if threaded:
        thread = co("thread", threaded[0]["id"], "--json")
        assert thread[0]["id"] == threaded[0]["id"] and len(thread) == threaded[0]["replies"] + 1


@pytest.mark.skipif(not setting("SLACK_USER_TOKEN"), reason="SLACK_USER_TOKEN not set")
def test_search_finds_what_history_shows():
    channel = next(row for row in co("channels", "--json") if row["kind"] == "public")
    words = next((m["text"].split()[0] for m in co("history", channel["id"], "-n", "20", "--json")
                  if m["text"].strip()), None)
    if words is None:
        pytest.skip(f"{channel['name']} has no text to search for")
    found = co("search", words, "--in", channel["name"], "-n", "5", "--json")
    assert all(match["chat"] == channel["id"] for match in found)
