"""
Purpose: Read one interactive terminal line without an unkillable worker thread.
LLM-Note:
  Dependencies: asyncio, sys, os, and msvcrt on Windows | imported by [_async_browser.py] | tested by [tests/unit/test_async_terminal.py, tests/unit/test_async_browser_core.py]
  Data flow: prompt → POSIX event-loop file-descriptor readiness or awaited Windows console polling → normalized line without newline
  State/Effects: temporarily registers one POSIX stdin reader or polls/echoes Windows console characters | always unregisters POSIX reader on success/error/cancellation
  Integration: AsyncBrowserCore serializes manual-login prompts runtime-wide before calling read_line
  Errors: EOF returns an empty line | Ctrl-C preserves KeyboardInterrupt | cancellation removes the reader and leaves no input worker behind
"""

import asyncio
import os
import sys


async def read_line(prompt: str) -> str:
    """Prompt and read a cancellable terminal line on POSIX and Windows."""
    print(prompt, end="", flush=True)
    if os.name == "nt":
        import msvcrt

        return await _read_windows_line(msvcrt)
    return await _read_posix_line(sys.stdin)


async def _read_posix_line(stream) -> str:
    loop = asyncio.get_running_loop()
    descriptor = stream.fileno()
    result = loop.create_future()

    def ready() -> None:
        if result.done():
            return
        try:
            result.set_result(stream.readline().rstrip("\r\n"))
        except BaseException as exc:
            result.set_exception(exc)

    loop.add_reader(descriptor, ready)
    try:
        return await result
    finally:
        loop.remove_reader(descriptor)


async def _read_windows_line(console) -> str:
    characters = []
    while True:
        if not console.kbhit():
            await asyncio.sleep(0.05)
            continue
        character = console.getwch()
        if character == "\x03":
            raise KeyboardInterrupt
        if character in {"\r", "\n"}:
            print()
            return "".join(characters)
        if character == "\b":
            if characters:
                characters.pop()
                print("\b \b", end="", flush=True)
            continue
        if character in {"\x00", "\xe0"}:
            console.getwch()
            continue
        characters.append(character)
        print(character, end="", flush=True)
