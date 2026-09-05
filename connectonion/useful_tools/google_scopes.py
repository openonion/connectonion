"""Normalize Google's URL scopes and the local comma-separated representation."""
import os
import re


def granted_scopes() -> set[str]:
    return {scope.removeprefix("https://www.googleapis.com/auth/")
            for scope in re.split(r"[,\s]+", os.getenv("GOOGLE_SCOPES", "")) if scope}
