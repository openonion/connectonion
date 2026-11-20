"""Optional remote collectors inside the existing REM lifecycle.

Adapters are shipped with their source feature. Connecting records metadata and a
choice, never consent to read bodies. Collection runs under REM's existing lock;
adapters must use their lock-held storage entry points, never invoke a CLI.
"""
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
import os
import shlex

import yaml

from .. import environment
from .files import RemError, maintenance_lock, _file_lock, read_json, state_path, write_json

KINDS = ("onenote",)


def require_saved(*names):
    """Diagnose a background-readable file/store without trusting shell exports."""
    from ..secret_store import get, stored_names
    values = environment.read_env_file(environment.selected_env_file())
    stored = stored_names(environment.global_config_dir())
    for name in names:
        value = values.get(name)
        if not value and name.lower() in stored:
            value = get(environment.global_config_dir(), name)
        if not value and name.startswith("MICROSOFT_"):
            raise RemError("Saved Microsoft authorization is missing. Reconnect with co auth microsoft; never hand-set OAuth fields")
        if not value:
            raise RemError(f"Background credential {name} is missing from saved configuration. "
                           f"In a local terminal: {environment.selected_command(f'co env set {name} --secret --prompt')}; then reconnect")


def recovery(kind, source=None):
    command = "co onenote source verify" if kind == "onenote" else f"co {kind} verify"
    path = (source or {}).get("remote", {}).get("credential_file")
    return f"co --env-file {shlex.quote(path)} {command[3:]}" if path else command


def adapter(kind):
    if kind not in KINDS:
        raise RemError("Remote connections support onenote")
    module = f"connectonion.rem.{kind}_remote"
    try:
        return import_module(module)
    except ModuleNotFoundError as error:
        if error.name != module:
            raise
        raise RemError(f"This installation does not include remote {kind}; install its source feature") from None


def directory(root, kind):
    path = root.resolve() / "docs" / kind
    if path.resolve() != path:
        raise RemError("Remote source paths must stay inside the notebook without symlinks")
    return path


@contextmanager
def credentials(source):
    """Select the original credential file, never copy it into a notebook/job."""
    previous = environment.explicit_env_file()
    selected = source["remote"].get("credential_file")
    names = adapter(source["kind"]).CREDENTIALS
    explicit = environment.process_environment()
    inherited = {name: explicit[name] for name in names if name in explicit}
    previous_home = os.environ.get("AGENT_CONFIG_PATH")
    try:
        for name in names:
            os.environ.pop(name, None)
        if source["remote"].get("credential_home"):
            os.environ["AGENT_CONFIG_PATH"] = source["remote"]["credential_home"]
        environment.select_env_file(Path(selected) if selected else None)
        yield
    finally:
        # A provider may have refreshed its managed record. Reload that record
        # rather than restoring stale values as if the shell had exported them.
        for name in names:
            os.environ.pop(name, None)
        if previous_home is None:
            os.environ.pop("AGENT_CONFIG_PATH", None)
        else:
            os.environ["AGENT_CONFIG_PATH"] = previous_home
        environment.select_env_file(previous)
        os.environ.update(inherited)


def selection(path):
    try:
        result = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        raise RemError("Cannot read scope configuration; see co rem sources connect --help") from None
    if not isinstance(result, dict):
        raise RemError("Scope configuration must be a mapping, containing no credentials")
    return result


def connect(root, kind, config=None):
    """Metadata-only setup; source/model/schedule approval remains init/start's."""
    from .config import prepare
    from .service import subscriptions
    provider = adapter(kind)
    try:
        if config is None:
            from .remote_wizard import select_scope
            value = select_scope(kind)
        else:
            value = selection(config)
        chosen = provider.validate(value)
    except RemError:
        raise
    except (ValueError, TypeError):
        raise RemError("Invalid scope configuration; see co rem sources connect --help") from None
    with maintenance_lock(root):
        prepare(root)
        directory(root, kind)
        sources = subscriptions(root)
        env_file = str(environment.selected_env_file())
        credential_home = str(environment.global_config_dir())
        try:
            with _file_lock(directory(root, kind), 0), credentials({"kind": kind, "remote": {
                    "credential_file": env_file, "credential_home": credential_home}}):
                declared = provider.configure(root, chosen)
        except RemError:
            raise
        except (ValueError, OSError, RuntimeError, yaml.YAMLError) as error:
            raise RemError(f"{kind.title()} connection failed ({type(error).__name__}); "
                           f"check {environment.selected_command(recovery(kind))} and retry connect") from None
        sources[kind] = {**sources.get(kind, {}), "id": kind, "kind": kind,
                         "root": str(directory(root, kind)), "enabled": True,
                         "unsubscribed": False, "consented": False, "adapter": "available",
                         "since": None, "import_identity": declared,
                         "remote": {"selection": chosen,
                                    "credential_file": env_file, "credential_home": credential_home}}
        write_json(state_path(root, "subscriptions.json"), sources)
    return {"source": kind, "state": "configured; awaiting source/model approval",
            "body_reads": False, "remote_polling": True}


def refresh(root, source):
    """Caller owns the maintenance lock; leave REM progress untouched."""
    from .service import now, summary_fingerprint
    if source.get("remote") is None or not source.get("enabled") or not source.get("consented"):
        return None
    definition = source["remote"]
    if (not isinstance(definition, dict) or not isinstance(definition.get("selection"), dict)
            or any(definition.get(key) is not None and not isinstance(definition[key], str)
                   for key in ("credential_file", "credential_home"))):
        raise RemError("Invalid remote connection state; preserve it and reconnect the selected source")
    approval = read_json(state_path(root, "consent.json"), {})
    if not isinstance(approval, dict) or approval.get("summary") != summary_fingerprint(root, mail=approval.get("summary_mail", ())):
        raise RemError("Remote source/model configuration changed; review and approve co rem init or start")
    kind = source["kind"]
    directory(root, kind)
    provider = adapter(kind)
    try:
        chosen = provider.validate(source["remote"].get("selection"))
    except RemError:
        raise
    except (ValueError, TypeError):
        raise RemError("Invalid saved remote scope; reconnect the selected source") from None
    # A changed declaration is rejected before any body is requested.
    imports = import_module(f"connectonion.rem.{kind}_imports")
    if imports.identity(root) != source.get("import_identity"):
        raise RemError("Remote source declaration changed; reconnect and approve the selected scope")
    try:
        with _file_lock(directory(root, kind), 0):
            if imports.identity(root) != source.get("import_identity"):
                raise RemError("Remote source declaration changed; reconnect and approve the selected scope")
            imports.snapshot_rows(root, source)
            with credentials(source):
                report = provider.refresh(root, source, chosen)
    except (ValueError, OSError, RuntimeError, yaml.YAMLError) as error:
        # Provider exceptions may contain source text or credentials. Keep only
        # the class in the receipt and a normal recovery command in the error.
        report = {"complete": False, "written": 0, "error_type": type(error).__name__}
    receipt = {"at": now().isoformat(), "complete": report.get("complete") is True,
               "written": report.get("written", 0),
               **({"error_type": report["error_type"]} if report.get("error_type") else {})}
    reads = read_json(state_path(root, "remote_reads.json"), {})
    if not isinstance(reads, dict):
        raise RemError("Invalid remote read receipts; preserve them for diagnosis")
    write_json(state_path(root, "remote_reads.json"), {**reads, kind: receipt})
    if not receipt["complete"]:
        raise RemError(f"Remote {kind} read incomplete; valid local versions retained. "
                       f"Check {recovery(kind, source)} and co rem sources; retry "
                       f"co rem --root {shlex.quote(str(root))} sync --source {kind}")
    return receipt


def refresh_initial(root, sources):
    """The map consumes imports only after successful approved remote reads."""
    reports = {}
    with maintenance_lock(root):
        for name, source in sources.items():
            report = refresh(root, source)
            if report is not None:
                reports[name] = report
    return reports
