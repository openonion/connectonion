"""Copyable next commands retain the explicitly selected account in every shell."""

import re
from ...environment import explicit_env_file, selected_command


def selected_tip(message: str) -> str:
    """Apply the selector to CLI-authored tips, never to provider text or content."""
    if explicit_env_file() is None:
        return message
    prefix = selected_command("co placeholder").removesuffix("placeholder")
    return re.sub(r"(?<![\w-])co (?!\-\-env-file\b)", lambda _: prefix, message)


def print_tip(message: str) -> None:
    """Print a plain, unwrapped tip; markup in a user-supplied path stays literal."""
    message = re.sub(r"\[/?(?:bold|dim|yellow|cyan|red|green)(?: [a-z]+)?\]", "", message)
    print(selected_tip(message))
