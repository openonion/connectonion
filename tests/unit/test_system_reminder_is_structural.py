"""A system reminder is context about the turn, not something the user said.

Two sites put reminder text into `messages` where it is indistinguishable from
what the user typed, so it rendered as a user bubble with raw tags showing.

The rule the renderer applies must be structural. Stripping the tags from
content — the approach closed in #144 — cannot tell an injected tag from one the
user typed, so someone asking "why does <system-reminder> show up in my chat?"
gets their own words silently rewritten.
"""

import pytest

from connectonion.network.host.session.ui import session_to_chat_items


def _user(content, **extra):
    return {"role": "user", "content": content, **extra}


class TestNoReminderReachesABubble:
    def test_an_internal_message_produces_no_bubble(self):
        session = {
            "messages": [
                _user("build the thing"),
                _user("<system-reminder>\nbuild context\n</system-reminder>", internal=True),
                {"role": "assistant", "content": "done"},
            ],
            "trace": [{"type": "user_input"}],
        }

        items = session_to_chat_items(session)

        assert [i["type"] for i in items].count("user") == 1
        assert not any("system-reminder" in str(i.get("content", "")) for i in items)

    def test_the_users_own_words_are_never_rewritten(self):
        """The reason this is structural. Someone asking about the tag must see
        their question as they typed it."""
        typed = "why does <system-reminder> show up in my chat?"
        session = {"messages": [_user(typed)], "trace": [{"type": "user_input"}]}

        items = session_to_chat_items(session)

        assert items[0]["content"] == typed


class TestASuppressedBubbleStillOpensItsTurn:
    """Carried over from #144's review: the first cut suppressed the bubble and
    dropped every tool call in that turn from the transcript."""

    def test_the_turns_trace_entries_still_render(self):
        session = {
            "messages": [
                _user("first"),
                _user("<system-reminder>ctx</system-reminder>", internal=True),
                {"role": "assistant", "content": "ok"},
            ],
            "trace": [
                {"type": "user_input"},
                {"type": "tool_result", "name": "read_file", "args": {}, "result": "x",
                 "status": "success", "timing_ms": 1},
                {"type": "user_input"},
                {"type": "tool_result", "name": "bash", "args": {}, "result": "y",
                 "status": "success", "timing_ms": 1},
            ],
        }

        items = session_to_chat_items(session)
        rendered = " ".join(str(i) for i in items)

        assert "read_file" in rendered
        assert "bash" in rendered, "the reminder turn's tool calls were dropped"


class TestOrdinaryMessagesAreUntouched:
    def test_a_normal_user_message_still_renders(self):
        session = {"messages": [_user("hello")], "trace": [{"type": "user_input"}]}

        assert session_to_chat_items(session)[0]["content"] == "hello"

    def test_assistant_messages_still_render(self):
        session = {
            "messages": [_user("hi"), {"role": "assistant", "content": "hey"}],
            "trace": [{"type": "user_input"}],
        }

        assert [i["type"] for i in session_to_chat_items(session)] == ["user", "agent"]


class TestTheInjectionHelperMarksWhatItInjects:
    def test_the_helper_produces_an_internal_message(self):
        from connectonion.useful_plugins.system_reminder import reminder_message

        msg = reminder_message("build context")

        assert msg["internal"] is True
        assert "<system-reminder>" in msg["content"]
        assert "build context" in msg["content"]

    def test_it_leaves_no_stray_blank_lines(self):
        """Also from #144's review — whitespace around the block left the bubble
        with an empty line when it did render."""
        from connectonion.useful_plugins.system_reminder import reminder_message

        content = reminder_message("  padded  ")["content"]

        assert content == content.strip()


class TestTheUploadNoticeIsNotPartOfWhatTheUserSaid:
    """agent.py concatenated it onto `prompt` — the same string that becomes the
    user message, the stored user_prompt, and the user_input trace entry. So the
    tags reached the chat bubble, xray, and the transcript from one assignment."""

    def test_the_notice_does_not_reach_the_user_message_or_the_trace(self):
        import inspect

        from connectonion.core import agent as agent_module

        source = inspect.getsource(agent_module.Agent.input)

        assert "prompt += " not in source, (
            "the upload notice is back on the user's own prompt string"
        )
        assert "reminder_message(upload_notice)" in source

    def test_a_reminder_message_is_still_visible_to_the_llm(self):
        """Suppressing the bubble must not stop the model seeing it — the notice
        exists so the agent knows to read the files."""
        from connectonion.useful_plugins.system_reminder import reminder_message

        msg = reminder_message("The user uploaded: a.pdf")

        assert msg["role"] == "user", "an internal message still goes to the model"
        assert "a.pdf" in msg["content"]
