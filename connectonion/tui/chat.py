"""
Purpose: Terminal chat interface using Textual framework for interactive agent conversations
LLM-Note:
  Dependencies: imports from [textual App/Screen/Widget, rich, core/agent.py, tui/input.py, tui/status_bar.py, tui/providers.py] | imported by [cli/commands/, examples/] | tested by [tests/tui/test_chat.py]
  Data flow: Chat.run() starts Textual app → renders status bar + chat messages → Input widget captures user input → on_submit sends to agent.input() → agent response appended to message log → UI updates | supports slash command triggers with autocomplete providers
  State/Effects: maintains message history in MessageLog widget | modifies terminal (clears screen, moves cursor) | restores terminal on exit | saves chat state in self.messages
  Integration: exposes Chat(agent, title, triggers, welcome, hints, status_segments, input_placeholder) with run() method | CommandItem dataclass for slash commands | uses Textual's reactive system for live updates | integrates with Agent for LLM interactions
  Performance: Textual async rendering (smooth) | message log scrolls efficiently | minimal re-renders via reactive
  Errors: catches agent errors and displays in chat | restores terminal on crash | validates command triggers
Chat - Terminal chat interface using Textual.

A simple, clean chat UI that works with the terminal medium rather than
fighting it. No fake "bubbles" - just clean text with color differentiation.

Usage:
    from connectonion.tui import Chat, CommandItem

    chat = Chat(
        agent=agent,
        title="My Chat",
        triggers={"/": [CommandItem(main="/help", prefix="?", id="/help")]},
        welcome="Welcome!",
        hints=["/ commands", "Enter send"],
        status_segments=[("🤖", "Agent", "cyan")],
    )
    chat.run()
"""

from typing import Callable

from rich.text import Text

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll
from textual.geometry import Offset
from textual.reactive import reactive
from textual.widgets import Input, Markdown, Static
from textual_autocomplete import AutoComplete, DropdownItem

from connectonion import before_each_tool


# --- Widgets ---

class ChatStatusBar(Static):
    """Status bar with left/center/right layout showing agent info, status, and model."""

    DEFAULT_CSS = """
    ChatStatusBar {
        width: 100%;
        height: 1;
        background: $surface;
    }
    """

    status = reactive("Ready")
    tokens = reactive(0)
    cost = reactive(0.0)

    def __init__(
        self,
        agent_name: str = "Agent",
        model: str = "",
        segments: list[tuple[str, str, str]] = None,  # Legacy support
    ):
        super().__init__()
        self.agent_name = agent_name
        self.model = model
        # Legacy: if segments provided, extract info
        if segments and not agent_name:
            self.agent_name = segments[0][1] if segments else "Agent"

    def render(self) -> Text:
        # Calculate available width (approximate)
        width = self.size.width if self.size.width > 0 else 80

        # Left: Agent name
        left = Text()
        left.append("🤖 ", style="bold cyan")
        left.append(self.agent_name, style="cyan")

        # Center: Status with icon based on state
        center = Text()
        if self.status == "Ready":
            center.append("● ", style="green")
            center.append("Ready", style="dim")
        elif self.status.startswith("Thinking"):
            center.append("◐ ", style="yellow")
            center.append(self.status, style="yellow italic")
        elif "(" in self.status and "/" in self.status:
            # Tool call with iteration: "tool_name (1/10)"
            center.append("⚡ ", style="yellow")
            center.append(self.status, style="yellow")
        else:
            center.append(self.status, style="dim")

        # Right: Model + tokens/cost
        right = Text()
        if self.model:
            right.append(self.model, style="dim")
        if self.tokens > 0:
            right.append(f"  {self.tokens:,} tok", style="dim")
        if self.cost > 0:
            right.append(f"  ${self.cost:.4f}", style="dim")

        # Compose with spacing
        left_str = left.plain
        center_str = center.plain
        right_str = right.plain

        # Calculate padding
        total_content = len(left_str) + len(center_str) + len(right_str)
        remaining = max(0, width - total_content)
        left_pad = remaining // 2
        right_pad = remaining - left_pad

        # Build final text
        result = Text()
        result.append_text(left)
        result.append(" " * left_pad)
        result.append_text(center)
        result.append(" " * right_pad)
        result.append_text(right)

        return result


class HintsFooter(Static):
    """Single-line hints bar."""

    DEFAULT_CSS = """
    HintsFooter {
        width: 100%;
        height: 1;
        background: $surface;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self, hints: list[str] = None):
        super().__init__()
        self.hints = hints or []

    def render(self) -> Text:
        return Text("  •  ".join(self.hints), style="dim")


class WelcomeMessage(Static):
    """Welcome message - compact centered box."""

    DEFAULT_CSS = """
    WelcomeMessage {
        margin: 1 2;
        padding: 0 1;
        background: $surface;
        border: round $primary-darken-2;
        height: auto;
    }

    WelcomeMessage Markdown {
        margin: 0;
        padding: 0;
    }
    """

    def __init__(self, content: str):
        super().__init__()
        self._content = content

    def compose(self) -> ComposeResult:
        yield Markdown(self._content)


class UserMessageContainer(Container):
    """Container to right-align user messages."""

    DEFAULT_CSS = """
    UserMessageContainer {
        width: 100%;
        height: auto;
        align: right middle;
    }
    """


class UserMessage(Static):
    """User message - compact right-aligned bubble."""

    DEFAULT_CSS = """
    UserMessage {
        background: $primary 20%;
        border: round $primary 50%;
        padding: 0 2;
        width: auto;
        max-width: 80%;
    }
    """

    def __init__(self, content: str) -> None:
        super().__init__()
        self.content = content

    def render(self) -> Text:
        text = Text()
        text.append("You: ", style="bold cyan")
        text.append(self.content)
        return text


class AssistantMessage(Static):
    """Assistant message - left-aligned with success border."""

    DEFAULT_CSS = """
    AssistantMessage {
        border-left: wide $success;
        background: $success 10%;
        margin: 1 2 1 1;
        padding: 0 1;
        height: auto;
    }

    AssistantMessage Markdown {
        margin: 0;
        padding: 0;
    }
    """

    def __init__(self, content: str):
        super().__init__()
        self._content = content

    def compose(self) -> ComposeResult:
        yield Markdown(self._content)


class ThinkingIndicator(Static):
    """Animated thinking indicator with elapsed time tracking."""

    DEFAULT_CSS = """
    ThinkingIndicator {
        color: $success;
        text-style: italic;
        background: $success 10%;
        border-left: wide $success;
        margin: 1 2 1 1;
        padding: 0 2;
        height: auto;
    }
    """

    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    frame_no = reactive(0)
    message = reactive("Thinking...")
    function_call = reactive("")  # e.g., search_emails("aaron")
    elapsed = reactive(0)  # Elapsed seconds
    show_elapsed = reactive(True)  # Show elapsed time for LLM thinking

    def __init__(self, message: str = "Thinking...", show_elapsed: bool = True):
        super().__init__()
        self.message = message
        self.show_elapsed = show_elapsed
        self._elapsed_timer = None

    def on_mount(self):
        self.set_interval(0.1, self._advance_frame)
        self._elapsed_timer = self.set_interval(1.0, self._advance_elapsed)

    def _advance_frame(self):
        self.frame_no += 1

    def _advance_elapsed(self):
        self.elapsed += 1

    def reset_elapsed(self):
        """Reset elapsed timer (called when switching between thinking/tool)."""
        self.elapsed = 0

    def render(self) -> str:
        frame = self.frames[self.frame_no % len(self.frames)]

        # Build main line
        if self.show_elapsed and self.elapsed > 0:
            hint = " (usually 3-10s)" if "Thinking" in self.message else ""
            main_line = f"{frame} {self.message} {self.elapsed}s{hint}"
        else:
            main_line = f"{frame} {self.message}"

        # Add function call on second line with tree connector
        if self.function_call:
            return f"{main_line}\n  └─ {self.function_call}"
        return main_line

    def watch_function_call(self, new_value: str) -> None:
        """Force layout refresh when function_call changes (for height resize)."""
        self.refresh(layout=True)


# --- Autocomplete ---

class TriggerAutoComplete(AutoComplete):
    """AutoComplete that activates on a trigger character (like / or @)."""

    def __init__(self, target: Input, trigger: str, candidates: list[DropdownItem]):
        super().__init__(target, candidates=candidates)
        self.trigger = trigger
        self._candidates = candidates

    def _find_trigger_position(self, text: str) -> int:
        return text.rfind(self.trigger)

    def get_search_string(self, target_state) -> str:
        text = target_state.text
        pos = self._find_trigger_position(text)
        if pos == -1:
            return ""
        return text[pos + 1:]

    def get_candidates(self, target_state) -> list[DropdownItem]:
        text = target_state.text
        if self._find_trigger_position(text) == -1:
            return []
        return self._candidates

    def should_show_dropdown(self, search_string: str) -> bool:
        """Show dropdown when trigger is present, even with empty search string."""
        option_list = self.option_list
        if option_list.option_count == 0:
            return False
        # Check if trigger exists in current text
        target_state = self._get_target_state()
        return self._find_trigger_position(target_state.text) != -1

    def _align_to_target(self) -> None:
        """Position dropdown ABOVE the input (for bottom-docked inputs)."""
        x, y = self.target.cursor_screen_offset
        dropdown = self.option_list
        _width, height = dropdown.outer_size
        # Position above cursor instead of below
        self.absolute_offset = Offset(x - 1, y - height)

    def apply_completion(self, value: str, target_state) -> str:
        text = target_state.text
        pos = self._find_trigger_position(text)
        if pos == -1:
            return text

        completion = value
        for item in self._candidates:
            item_value = item.main if isinstance(item.main, str) else item.main.plain
            if item_value == value and item.id:
                completion = item.id
                break

        return text[:pos] + completion


# --- Main Chat App ---

class Chat(App):
    """Clean terminal chat interface."""

    CSS = """
    Screen {
        background: $background;
    }

    ChatStatusBar {
        dock: top;
    }

    HintsFooter {
        dock: bottom;
    }

    #messages {
        scrollbar-gutter: stable;
    }

    #input-container {
        dock: bottom;
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
        background: $surface;
    }

    #input-container Input {
        width: 100%;
        border: round $primary-darken-1;
        padding: 0 1;
    }

    #input-container Input:focus {
        border: round $primary;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+d", "quit", "Quit"),
    ]

    def __init__(
        self,
        agent=None,
        handler: Callable[[str], str] = None,
        title: str = "Chat",
        subtitle: str = None,
        on_error: Callable[[Exception], str] = None,
        triggers: dict[str, list[DropdownItem]] = None,
        welcome: str = None,
        hints: list[str] = None,
        status_segments: list[tuple[str, str, str]] = None,
    ):
        super().__init__()
        self.agent = agent
        self.handler = handler or (agent.input if agent else lambda x: x)
        self._title = title
        self._subtitle = subtitle or (f"co/{agent.llm.model}" if agent else "")
        self._commands: dict[str, Callable[[str], str]] = {}
        self._thinking_widget: ThinkingIndicator | None = None
        self._processing = False  # Prevent multiple simultaneous requests
        self._on_error = on_error
        self._triggers = triggers or {}
        self._welcome = welcome
        self._hints = hints or ["Enter send", "Ctrl+D quit"]
        self._status_segments = status_segments

        # Extract agent info for status bar
        self._agent_name = agent.name if agent else title
        self._model = agent.llm.model if agent else ""

        # Register event handlers for status updates
        if self.agent:
            from connectonion import before_llm, after_llm, on_complete
            chat = self  # Capture for closure

            @before_llm
            def _show_llm_thinking(agent):
                iteration = agent.current_session.get('iteration', 1)
                max_iter = agent.max_iterations
                chat.call_from_thread(chat._update_status, f"Thinking ({iteration}/{max_iter})")
                chat.call_from_thread(chat._update_thinking, "Thinking...", show_elapsed=True, reset=True, function_call="")

            @before_each_tool
            def _show_tool_progress(agent):
                tool_info = agent.current_session.get('pending_tool', {})
                tool_name = tool_info.get('name', 'tool')
                description = tool_info.get('description', '')
                arguments = tool_info.get('arguments', {})
                iteration = agent.current_session.get('iteration', 1)
                max_iter = agent.max_iterations
                chat.call_from_thread(chat._update_status, f"{tool_name} ({iteration}/{max_iter})")

                # Format function call: search_emails("aaron") or Bash("ps -ef")
                def _truncate(v, max_len=30):
                    s = f'"{v}"' if isinstance(v, str) else str(v)
                    return s[:max_len] + "..." if len(s) > max_len else s

                if arguments:
                    args_str = ", ".join(_truncate(v) for v in arguments.values())
                    fn_call = f"{tool_name}({args_str})"
                else:
                    fn_call = f"{tool_name}()"

                # Line 1: description, Line 2: function call
                msg = description if description else f"Calling {tool_name}"
                chat.call_from_thread(chat._update_thinking, msg, show_elapsed=False, function_call=fn_call)

            @after_llm
            def _update_tokens(agent):
                if agent.last_usage:
                    total_tokens = agent.last_usage.input_tokens + agent.last_usage.output_tokens
                    chat.call_from_thread(chat._update_tokens, total_tokens, agent.total_cost)

            @on_complete
            def _on_done(agent):
                chat.call_from_thread(chat._update_status, "Ready")

            self.agent._register_event(_show_llm_thinking)
            self.agent._register_event(_show_tool_progress)
            self.agent._register_event(_update_tokens)
            self.agent._register_event(_on_done)

    def compose(self) -> ComposeResult:
        # Always show status bar with agent info
        yield ChatStatusBar(
            agent_name=self._agent_name,
            model=self._model,
            segments=self._status_segments,  # Legacy support
        )

        yield VerticalScroll(id="messages")

        with Container(id="input-container"):
            text_input = Input(placeholder="Type a message... (/ for commands)", id="input")
            yield text_input
            for trigger, items in self._triggers.items():
                yield TriggerAutoComplete(text_input, trigger, items)

        if self._hints:
            yield HintsFooter(self._hints)

    def on_mount(self) -> None:
        self.title = self._title
        self.sub_title = self._subtitle
        self.query_one(Input).focus()

        if self._welcome:
            messages = self.query_one("#messages", VerticalScroll)
            messages.mount(WelcomeMessage(self._welcome))

    def command(self, name: str, handler: Callable[[str], str]):
        """Register a slash command handler."""
        self._commands[name.lower()] = handler

    def _find_command(self, text: str) -> tuple[str, Callable[[str], str]] | None:
        cmd_lower = text.lower()
        for cmd_name, handler in self._commands.items():
            if cmd_lower.startswith(cmd_name):
                if cmd_lower == cmd_name or cmd_lower[len(cmd_name):].startswith(" "):
                    return cmd_name, handler
        return None

    def _scroll_to_bottom(self) -> None:
        messages = self.query_one("#messages", VerticalScroll)
        messages.scroll_end(animate=False)

    def _update_thinking(self, message: str, show_elapsed: bool = True, reset: bool = False, function_call: str = "") -> None:
        """Update thinking indicator message (called from worker thread)."""
        if self._thinking_widget:
            self._thinking_widget.message = message
            self._thinking_widget.function_call = function_call
            self._thinking_widget.show_elapsed = show_elapsed
            if reset:
                self._thinking_widget.reset_elapsed()

    def _update_status(self, status: str) -> None:
        """Update status bar status (called from worker thread)."""
        status_bar = self.query_one(ChatStatusBar)
        status_bar.status = status

    def _update_tokens(self, tokens: int, cost: float) -> None:
        """Update status bar token/cost display (called from worker thread)."""
        status_bar = self.query_one(ChatStatusBar)
        status_bar.tokens = tokens
        status_bar.cost = cost

    def _set_input_enabled(self, enabled: bool) -> None:
        """Enable or disable input while processing."""
        input_widget = self.query_one("#input", Input)
        input_widget.disabled = not enabled
        if enabled:
            input_widget.placeholder = "Type a message... (/ for commands)"
            input_widget.focus()
        else:
            input_widget.placeholder = "Waiting for response..."

    @on(Input.Submitted)
    async def handle_input(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text or self._processing:
            return

        event.input.clear()

        messages = self.query_one("#messages", VerticalScroll)
        user_container = UserMessageContainer(UserMessage(text))
        await messages.mount(user_container)
        self.call_later(self._scroll_to_bottom)

        cmd_lower = text.lower()
        if cmd_lower in ("/quit", "/exit", "/q"):
            self.exit()
            return

        cmd_match = self._find_command(text)
        if cmd_match:
            _, handler = cmd_match
            self._processing = True
            self._set_input_enabled(False)
            self._thinking_widget = ThinkingIndicator("Processing...")
            self._update_status("Processing...")
            await messages.mount(self._thinking_widget)
            self.call_later(self._scroll_to_bottom)
            self.run_command(handler, text)
            return

        if text.startswith("/"):
            await messages.mount(AssistantMessage(f"Unknown command: `{text.split()[0]}`. Try `/help`."))
            self.call_later(self._scroll_to_bottom)
            return

        self._processing = True
        self._set_input_enabled(False)
        self._thinking_widget = ThinkingIndicator()
        self._update_status("Thinking...")
        await messages.mount(self._thinking_widget)
        self.call_later(self._scroll_to_bottom)
        self.process_message(text)

    @work(thread=True)
    def run_command(self, handler: Callable[[str], str], text: str) -> None:
        try:
            result = handler(text)
            self.call_from_thread(self._show_response, result)
        except Exception as e:
            self.call_from_thread(self._show_error, e)

    @work(thread=True)
    def process_message(self, text: str) -> None:
        try:
            response = self.handler(text)
            self.call_from_thread(self._show_response, response)
        except Exception as e:
            self.call_from_thread(self._show_error, e)

    def _show_response(self, response: str) -> None:
        messages = self.query_one("#messages", VerticalScroll)

        if self._thinking_widget:
            self._thinking_widget.remove()
            self._thinking_widget = None

        messages.mount(AssistantMessage(response))
        self.call_later(self._scroll_to_bottom)

        # Re-enable input
        self._processing = False
        self._set_input_enabled(True)
        self._update_status("Ready")

    def _show_error(self, error: Exception) -> None:
        messages = self.query_one("#messages", VerticalScroll)

        if self._thinking_widget:
            self._thinking_widget.remove()
            self._thinking_widget = None

        if self._on_error:
            error_msg = self._on_error(error)
            messages.mount(AssistantMessage(f"**Error**\n\n{error_msg}"))
        else:
            self.notify(str(error), title="Error", severity="error", timeout=10)

        self.call_later(self._scroll_to_bottom)

        # Re-enable input
        self._processing = False
        self._set_input_enabled(True)
        self._update_status("Ready")

    def action_quit(self) -> None:
        self.exit()
