"""Provider-safe recovery for the Gmail and Drive command surfaces."""

from functools import wraps
import json

import typer
from rich.console import Console


def google_errors(next_command: str):
    """Keep provider bodies out of errors and name one concrete recovery step.

    Write commands use an inspection command: a lost response does not prove
    that the provider rejected the write, so blindly retrying can duplicate it.
    """
    def decorate(handler):
        @wraps(handler)
        def guarded(*args, **kwargs):
            from googleapiclient.errors import HttpError
            from google.auth.exceptions import GoogleAuthError
            from httplib2 import HttpLib2Error
            from requests import RequestException

            from ...provider_credentials import ProviderCredentialError
            from ...credentials import AmbientCredentialError
            from .gmail_listings import ListingError

            recovery = next_command
            try:
                return handler(*args, **kwargs)
            except ProviderCredentialError as exc:
                cause = str(exc).split("\nNext:", 1)[0]
                recovery = exc.next_command
            except AmbientCredentialError as exc:
                cause = str(exc)
                recovery = "co auth"
            except ListingError as exc:
                cause = str(exc)
            except json.JSONDecodeError:
                cause = "Saved listing numbers are unreadable; refresh the listing."
            except HttpError as exc:
                status = getattr(exc.resp, "status", None)
                cause = f"Google request failed (HTTP {status}). Inspect state before retrying a write."
                if status in (401, 403):
                    recovery = "co auth google"
            except GoogleAuthError:
                cause = "Google authorization failed."
                recovery = "co auth google"
            except (RequestException, HttpLib2Error, OSError):
                cause = "Local I/O or Google connection failed. A write may have completed; inspect state before retrying."
            except ValueError:
                cause = "Invalid input or unsupported file. Check the command arguments."
            from ...environment import selected_command
            recovery = selected_command(recovery)
            Console().print(f"Error: {cause}\nNext: {recovery}", markup=False, highlight=False, soft_wrap=True)
            raise typer.Exit(1)
        return guarded
    return decorate
