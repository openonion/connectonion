"""Where the project is.

The directory that owns ``.co/`` is the project, not wherever the process was
started. An agent run from a subdirectory is the same agent, with the same
skills, the same trust lists and the same ``host.yaml``.

This walk was written five times before it had a home — in the dashboard, the
logger, the host config, the trust lists — and each copy was added by a separate
bug where something resolved against the bare cwd instead. Two of those bugs
failed open: a project configured ``trust: strict`` ran as ``careful``, and an
address on the blocklist read back as a stranger.

Nothing here creates a directory. Creating ``.co/`` wherever you happen to be
standing is the other half of the same bug: the walk stops at the *nearest*
``.co/``, so a stray one shadows the project's own for everything that comes
after it.
"""

from pathlib import Path
from typing import Optional, Union


CO_DIR = ".co"


def project_root(start: Optional[Union[str, Path]] = None) -> Path:
    """The directory that owns ``.co/``, found by walking up from ``start``.

    Falls back to ``start`` when there is no ``.co/`` above it — an agent hosted
    outside a project still works, its files just live where it was started.
    """
    start = Path(start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        if (directory / CO_DIR).is_dir():
            return directory
    return start


def project_co_dir(start: Optional[Union[str, Path]] = None) -> Path:
    """The project's ``.co/``. Does not create it."""
    return project_root(start) / CO_DIR


def _configured_agent_name(co_dir):
    """host.yaml's `name`, or None. The same value `co deploy` reads."""
    host_yaml = Path(co_dir) / "host.yaml"
    if not host_yaml.exists():
        return None
    import yaml

    try:
        config = yaml.safe_load(host_yaml.read_text(encoding="utf-8", errors="replace"))
    except yaml.YAMLError:
        # A malformed host.yaml is reported where it is loaded for real; here it
        # only means the name is unknown, and the directory answers instead.
        return None
    if not isinstance(config, dict):
        return None
    name = config.get("name")
    return str(name).strip() or None if name else None


def derived_identity(co_dir=None):
    """This project's own address, derived from the recovery phrase, or None.

    Lives here because "which identity is this project's" is the same question
    as "which directory is this project", and answering it in more than one
    place is what this release has spent itself fixing. Four call sites resolved
    it independently before: the host, the client in connect.py, `co keys`, and
    project_cmd_lib. A host that served a derived address while `co keys`
    printed the inherited one would be #659 again.

    Derived rather than generated (Aaron's call): the twelve words already cover
    it, the same phrase and project name always give the same address, and
    `co keys` can print it before the project has ever run. Not a new scheme --
    `identity_uri` and `slip13_path` already define it and `co server` already
    derives SSH keys the same way.
    """
    from mnemonic import Mnemonic
    from nacl.signing import SigningKey

    from . import address
    from .derive import derive_path, identity_uri, slip13_path

    phrase_file = Path.home() / CO_DIR / "keys" / "recovery.txt"
    if not phrase_file.exists():
        return None
    phrase = phrase_file.read_text(encoding="utf-8", errors="replace").strip()
    if not phrase:
        return None

    # The name `co deploy` derives from, so an agent has one address whether it
    # runs here or on a server. Deploy has derived from host.yaml's `name` since
    # #396; taking the directory instead would give a renamed project two
    # identities and nothing would say which was which.
    co_dir = Path(co_dir or project_co_dir())
    name = _configured_agent_name(co_dir) or co_dir.resolve().parent.name
    if not name:
        return None

    signing_key = SigningKey(
        derive_path(Mnemonic("english").to_seed(phrase), slip13_path(identity_uri(name))))
    hex_address = "0x" + bytes(signing_key.verify_key).hex()
    return address.Identity({
        "address": hex_address,
        "short_address": f"{hex_address[:6]}...{hex_address[-4:]}",
        "email": f"{hex_address[:10]}@mail.openonion.ai",
        "email_active": False,
        # `source` means "the directory this key belongs to", and #688 writes
        # the served-by record into it. A derived key belongs to the project it
        # was derived for -- so that stays a real directory rather than a
        # marker string, which would have made claim_identity silently do
        # nothing and taken #688's collision warning with it.
        #
        # Nothing collides here anyway: two projects deriving from one phrase
        # get two addresses. The record still says who is serving.
        "source": str(Path(co_dir or project_co_dir())),
        "derived": True,
        "signing_key": signing_key,
    })


def project_identity(co_dir=None):
    """The identity this project acts as: its own key, else derived, else the
    global one, else nothing.

    The single answer every caller should use.
    """
    from . import address

    co_dir = Path(co_dir) if co_dir else project_co_dir()
    own = address.load(co_dir)
    if own:
        return own
    derived = derived_identity(co_dir)
    if derived:
        return derived
    return address.load(Path.home() / CO_DIR)
