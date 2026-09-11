"""
LLM-Note: Tests for connectonion.inbox.settings — which channels an agent
listens to, read from .co/host.yaml so that `co ai` starts with no flags, and
the flags that override it for one run.
"""

import pytest

from connectonion.inbox.settings import Channel, channels_from, configured_channels
from connectonion.inbox.store import Message


def host_yaml(tmp_path, body: str):
    co = tmp_path / ".co"
    co.mkdir(exist_ok=True)
    (co / "host.yaml").write_text(body, encoding="utf-8")
    return co


def message(chat="c1", mentioned=True):
    return Message(id="m1", chat=chat, sender="s1", text="hi",
                   at="2026-09-11T00:00:00Z", mentioned=mentioned)


class TestReadingTheFile:
    def test_the_file_alone_is_enough_to_start(self, tmp_path):
        co = host_yaml(tmp_path, "name: oo\ntrust: open\nlisten:\n  feishu: {}\n")
        assert configured_channels(co) == [Channel(provider="feishu")]

    def test_several_channels_keep_their_order(self, tmp_path):
        co = host_yaml(tmp_path, "listen:\n  feishu: {}\n  lark: {}\n")
        assert [c.provider for c in configured_channels(co)] == ["feishu", "lark"]

    def test_a_channel_may_name_the_chats_it_answers(self, tmp_path):
        co = host_yaml(tmp_path, "listen:\n  feishu:\n    chats: [oc_a, oc_b]\n")
        assert configured_channels(co)[0].chats == ("oc_a", "oc_b")

    def test_a_bare_name_is_a_channel_with_defaults(self, tmp_path):
        # `listen: [feishu]` is what someone writes before they need options.
        co = host_yaml(tmp_path, "listen:\n  - feishu\n")
        assert configured_channels(co) == [Channel(provider="feishu")]

    def test_no_listen_section_means_no_channels(self, tmp_path):
        co = host_yaml(tmp_path, "name: oo\n")
        assert configured_channels(co) == []

    def test_no_file_at_all_means_no_channels(self, tmp_path):
        assert configured_channels(tmp_path / ".co") == []

    def test_an_unknown_channel_names_the_ones_that_exist(self, tmp_path):
        co = host_yaml(tmp_path, "listen:\n  slack: {}\n")
        with pytest.raises(ValueError) as raised:
            configured_channels(co)
        assert "slack" in str(raised.value) and "feishu" in str(raised.value)

    def test_a_broken_file_says_so_rather_than_listening_to_nothing(self, tmp_path):
        # Silently starting with no channels is the failure that looks like
        # success: the agent runs, and nobody can reach it.
        co = host_yaml(tmp_path, "listen:\n  feishu: [unclosed\n")
        with pytest.raises(ValueError) as raised:
            configured_channels(co)
        assert "host.yaml" in str(raised.value)


class TestTheCommandLineOverrides:
    def test_no_flag_uses_the_file(self, tmp_path):
        co = host_yaml(tmp_path, "listen:\n  feishu: {}\n")
        assert [c.provider for c in configured_channels(co, override=None)] == ["feishu"]

    def test_a_flag_replaces_the_list(self, tmp_path):
        co = host_yaml(tmp_path, "listen:\n  feishu: {}\n")
        assert [c.provider for c in configured_channels(co, override=["lark"])] == ["lark"]

    def test_an_overridden_channel_keeps_its_settings_from_the_file(self, tmp_path):
        # --listen picks which channels run, not what they are configured like.
        co = host_yaml(tmp_path, "listen:\n  feishu:\n    chats: [oc_a]\n  lark: {}\n")
        picked = configured_channels(co, override=["feishu"])
        assert picked == [Channel(provider="feishu", chats=("oc_a",))]

    def test_an_empty_override_turns_listening_off(self, tmp_path):
        co = host_yaml(tmp_path, "listen:\n  feishu: {}\n")
        assert configured_channels(co, override=[]) == []


class TestTheGate:
    def test_a_message_addressed_to_the_bot_is_answered(self):
        assert Channel("feishu").answers(message(mentioned=True))

    def test_a_group_message_that_did_not_address_the_bot_is_not(self):
        # Everything else in the group is other people talking to each other.
        assert not Channel("feishu").answers(message(mentioned=False))

    def test_mention_only_can_be_turned_off_for_a_quiet_channel(self):
        assert Channel("feishu", mention_only=False).answers(message(mentioned=False))

    def test_a_named_chat_list_excludes_every_other_chat(self):
        channel = Channel("feishu", chats=("oc_a",))
        assert channel.answers(message(chat="oc_a"))
        assert not channel.answers(message(chat="oc_b"))

    def test_an_empty_chat_list_means_every_chat(self):
        assert Channel("feishu").answers(message(chat="anything"))
