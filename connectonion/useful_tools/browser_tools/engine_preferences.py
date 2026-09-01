"""Persistent user choice between WTFbrowser and Chrome compatibility mode."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from . import engine


class BrowserEnginePreferenceError(RuntimeError):
    pass


def preference_path(home: Path | None = None) -> Path:
    return Path(home or Path.home()) / ".co" / "browser-engine"


def load_default_engine(home: Path | None = None) -> str:
    path = preference_path(home)
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return engine.WTF
    except OSError as exc:
        raise BrowserEnginePreferenceError(
            f"Could not read browser engine preference at {path}."
        ) from exc
    if value not in (engine.WTF, engine.CHROME):
        raise BrowserEnginePreferenceError(
            f"Invalid browser engine preference at {path}; run `co browser "
            "config set engine wtf` or `co browser config set engine chrome`."
        )
    return value


def save_default_engine(value: str, home: Path | None = None) -> Path:
    value = engine.normalize_mode(value)
    path = preference_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".browser-engine-",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(value + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise BrowserEnginePreferenceError(
            f"Could not save browser engine preference at {path}."
        ) from exc
    return path
