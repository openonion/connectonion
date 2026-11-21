"""Selected-scope configuration for external read-only OneNote imports."""
from datetime import datetime, timezone
from pathlib import Path
import yaml
from .._version import __version__


def source_config(source_dir: Path, account: str, scope: dict, command: str, *, daily: bool = False) -> dict:
    """Build source.yaml content, preserving existing account/scope ownership."""
    config = source_dir / "source.yaml"
    registration = "external_import_only"
    if config.exists():
        saved = yaml.safe_load(config.read_text(encoding="utf-8"))
        previous = saved.get("scope") if isinstance(saved, dict) else None
        if isinstance(saved, dict) and saved.get("registration") == "rem_remote":
            registration = "rem_remote"
        same_scope = previous == scope or (daily and isinstance(previous, dict) and
                                           all(previous.get(key) == scope[key] for key in ("notebook", "section")))
        if not same_scope or saved.get("account") != account or saved.get("driver") != "onenote":
            raise ValueError("This source directory belongs to another account or scope. Use a separate --output directory.")
        if daily and (not isinstance(previous.get("pages"), list) or
                      any(not isinstance(page, str) for page in previous["pages"])):
            raise ValueError("Existing source scope is malformed. Preserve it and choose a separate --output directory.")
        if daily:
            scope = {**scope, "pages": sorted(set(previous.get("pages", [])) | set(scope["pages"]))}
    now = datetime.now(timezone.utc).isoformat()
    doc = {"driver": "onenote", "account": account, "scope": scope, "retention": "90d",
           "media_policy": "metadata_only", "read_only": True,
           "validated_with": {"connectonion_version": __version__, "command": command,
                              "path": str(config.resolve()), "timestamp": now},
           "registration": registration}
    return doc
