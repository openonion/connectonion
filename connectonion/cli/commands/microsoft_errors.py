"""Sanitized, non-zero Outlook failures with credential-layer recovery."""

from functools import wraps

import httpx
import typer
from rich.console import Console

from ...credentials import AmbientCredentialError
from ...environment import EnvironmentError
from ...provider_credentials import ProviderCredentialError


def microsoft_errors(next_command: str):
    def decorate(handler):
        @wraps(handler)
        def guarded(*args, **kwargs):
            recovery = next_command
            try:
                return handler(*args, **kwargs)
            except ProviderCredentialError as error:
                cause = str(error).split("\nNext:", 1)[0]
                recovery = error.next_command
            except AmbientCredentialError as error:
                cause, recovery = str(error), "co auth"
            except EnvironmentError as error:
                cause, recovery = str(error), "co --help"
            except (httpx.HTTPError, OSError):
                cause = "Microsoft connection or local I/O failed; inspect state before retrying a write."
            except ValueError:
                cause = "Invalid input or Microsoft request failed; check the command arguments."
            from ...environment import selected_command
            recovery = selected_command(recovery)
            Console().print(f"Error: {cause}\nNext: {recovery}", markup=False, highlight=False, soft_wrap=True)
            raise typer.Exit(1) from None
        return guarded
    return decorate
