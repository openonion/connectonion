"""Keep Codex delegation on the native provider adapter."""

from __future__ import annotations

import os
import re
import shlex
from typing import Iterable

from connectonion.core.events import after_user_input, before_each_tool
from connectonion.useful_plugins.system_reminder import reminder_message

_SHELL_TOOLS = {"bash", "shell", "run", "run_in_dir", "run_background"}
_NEGATED_CODEX = re.compile(
    r"\b(?:do\s+not|don't|dont|never|without)\b[^.\n]{0,40}\bcodex\b",
    re.IGNORECASE,
)
_EXPLICIT_CODEX = re.compile(
    r"(?:"
    r"\b(?:run|use|start|open|launch|invoke)\s+(?:the\s+)?codex\b|"
    r"\b(?:ask|tell)\s+(?:the\s+)?codex\b|"
    r"\b(?:delegate|hand)\b[^.\n]{0,30}\b(?:to\s+)?codex\b|"
    r"(?:打开|启动|运行|使用|用|让|叫|交给)\s*(?:一下)?\s*codex\b"
    r")",
    re.IGNORECASE,
)
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_CODEX_BINARIES = {"codex", "codex.exe", "codex.cmd"}


def is_explicit_codex_request(prompt: str) -> bool:
    """Return true only when the user asked to operate Codex."""
    text = prompt.strip()
    if not text or _NEGATED_CODEX.search(text):
        return False
    if re.match(r"^/codex(?:\s|$)", text, re.IGNORECASE):
        return True
    return bool(_EXPLICIT_CODEX.search(text))


@after_user_input
def route_explicit_codex_request(agent) -> None:
    """Give an explicit Codex request one unambiguous model-visible route."""
    prompt = agent.current_session.get("user_prompt", "")
    if not isinstance(prompt, str) or not is_explicit_codex_request(prompt):
        return
    agent.current_session["provider_route"] = "codex"
    agent.current_session.setdefault("messages", []).append(
        reminder_message(
            "This request explicitly targets Codex. Call `codex()` now; never "
            "launch the Codex CLI through bash, shell, or a background wrapper. "
            "Pass the user's task verbatim when one exists. If the user only "
            "asked to open/start Codex and supplied no task, omit `prompt`; the "
            "native adapter will create or resume the provider session without "
            "inventing or submitting a turn. Preserve the returned `session_id` "
            "and pass it to follow-up `codex()` calls."
        )
    )


@before_each_tool
def reject_raw_codex_launch(agent) -> None:
    """Reject shell execution of Codex before approval or process creation."""
    pending = agent.current_session.get("pending_tool") or {}
    tool_name = str(pending.get("name", "")).lower()
    if tool_name not in _SHELL_TOOLS:
        return
    arguments = pending.get("arguments") or {}
    command = arguments.get("command") or arguments.get("cmd") or ""
    if not isinstance(command, str) or not _contains_codex_launch(command):
        return

    frame = {
        "type": "tool_blocked",
        "tool": tool_name,
        "reason": "native_provider_required",
        "provider": "codex",
        "message": "Use the native codex() adapter instead of a raw CLI launch.",
        "command": command,
    }
    io = getattr(agent, "io", None)
    if io is not None:
        io.send(frame)
    raise ValueError(
        "Raw Codex CLI launch blocked. Call codex() now with the user's task, "
        "cwd, and prior session_id. If the user only asked to open Codex, call "
        "codex() without a prompt. Do not retry through bash, shell, or "
        "run_background."
    )


def _contains_codex_launch(command: str) -> bool:
    try:
        groups = list(_command_word_groups(command))
    except Exception:
        try:
            groups = [shlex.split(command)]
        except ValueError:
            groups = [command.split()]
    return any(_words_launch_codex(words) for words in groups if words)


def _command_word_groups(command: str) -> Iterable[list[str]]:
    import bashlex

    def walk(node):
        if node.kind == "command":
            words = [part.word for part in node.parts if part.kind == "word"]
            if words:
                yield words
        for attr in ("parts", "list"):
            for child in getattr(node, attr, []) or []:
                yield from walk(child)
        for attr in ("command", "output", "input", "heredoc"):
            child = getattr(node, attr, None)
            if child is not None and hasattr(child, "kind"):
                yield from walk(child)

    for tree in bashlex.parse(command):
        yield from walk(tree)


def _words_launch_codex(words: list[str]) -> bool:
    words = _drop_assignments(words)
    if not words:
        return False
    executable = _basename(words[0])
    if executable in _CODEX_BINARIES:
        return True

    if executable == "command":
        if any(flag in ("-v", "-V") for flag in words[1:2]):
            return False
        return _words_launch_codex(_after_options(words[1:], set()))
    if executable == "env":
        rest = _after_options(
            words[1:], {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}
        )
        return _words_launch_codex(_drop_assignments(rest))
    if executable == "sudo":
        return _words_launch_codex(
            _after_options(
                words[1:],
                {"-u", "--user", "-g", "--group", "-h", "--host", "-C", "--close-from"},
            )
        )
    if executable in {"exec", "nohup", "time", "nice"}:
        values = {"-n", "--adjustment"} if executable == "nice" else set()
        return _words_launch_codex(_after_options(words[1:], values))
    if executable in {"bash", "sh", "zsh", "dash", "fish"}:
        script = _shell_script(words[1:])
        return bool(script and _contains_codex_launch(script))
    if executable == "xargs":
        rest = _after_options(
            words[1:],
            {"-a", "--arg-file", "-d", "--delimiter", "-E", "--eof", "-I", "--replace", "-L", "--max-lines", "-n", "--max-args", "-P", "--max-procs", "-s", "--max-chars"},
        )
        return _words_launch_codex(rest)
    if executable in {"npx", "bunx"}:
        package = _first_operand(words[1:])
        return package in {"codex", "@openai/codex"}
    if executable in {"npm", "pnpm", "yarn"}:
        return _package_manager_launches_codex(executable, words[1:])
    if executable == "open" and len(words) >= 3 and words[1] == "-a":
        return words[2].lower() == "codex"
    return False


def _package_manager_launches_codex(executable: str, words: list[str]) -> bool:
    if not words:
        return False
    subcommand = words[0]
    allowed = {"exec"}
    if executable in {"pnpm", "yarn"}:
        allowed.add("dlx")
    if subcommand not in allowed:
        return False
    package = _first_operand(words[1:])
    return package in {"codex", "@openai/codex"}


def _shell_script(words: list[str]) -> str:
    for index, word in enumerate(words):
        if word == "--":
            continue
        if word.startswith("-") and "c" in word[1:] and index + 1 < len(words):
            return words[index + 1]
    return ""


def _first_operand(words: list[str]) -> str:
    rest = _after_options(words, {"-c", "--call", "--package"})
    return rest[0].lower() if rest else ""


def _after_options(words: list[str], options_with_value: set[str]) -> list[str]:
    index = 0
    while index < len(words):
        word = words[index]
        if word == "--":
            return words[index + 1 :]
        option = word.split("=", 1)[0]
        if option in options_with_value:
            index += 1 if "=" in word else 2
            continue
        if word.startswith("-"):
            index += 1
            continue
        break
    return words[index:]


def _drop_assignments(words: list[str]) -> list[str]:
    index = 0
    while index < len(words) and _ASSIGNMENT.match(words[index]):
        index += 1
    return words[index:]


def _basename(word: str) -> str:
    return os.path.basename(word.replace("\\", "/")).lower()


native_coding_agent_routing = [
    route_explicit_codex_request,
    reject_raw_codex_launch,
]

