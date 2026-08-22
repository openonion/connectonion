"""The version string, on its own, so reading it costs nothing.

`co --version` used to import the whole package — and with it the OpenAI and
Anthropic SDKs, the TUI and every useful_tool — to print six characters. Every
command handler in the CLI is already imported inside its function; this module
is what lets the entry point keep that promise.

Kept in step with pyproject.toml by a test.
"""

__version__ = "1.7.0b10"
