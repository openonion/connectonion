"""The admin part of the Control Center: People (who is in, their activity), the invite, log.

An operator hosting an agent for other people opened its Control Center and
could manage nothing there (#3263). Who joined with the invite code, removing
one of them, rotating the code, the log: all of it was the host machine's shell.

Two rules hold it together:

- It is rendered into the starter Home only for a socket whose verified address
  is in admins.txt (``viewer["is_admin"]``, decided at CONNECT by the trust
  agent). A non-admin socket is sent none of it -- there is no hidden markup to
  unhide. A custom ``control_center.html`` cannot do this: one file is served the same
  to every admitted caller.
- Its buttons only *ask*. ``run`` re-checks the caller against admins.txt when
  the signed command arrives and acts through the trust agent, the same calls
  ``co trust`` and the ADMIN_* frames make.
"""

import time
from html import escape
from pathlib import Path

from .... import approvals

ACTIONS = ("admin.remove", "admin.block", "admin.rotate_invite", "admin.invite_off")
INVITE_VARIABLE = "CO_INVITE_CODE"
LOG_LINES = 40

# Set once by the Host that serves this page (configure); None means "not a
# running Host" -- tests, tooling -- and then there is no admin section at all.
_trust_agent = None
_log_path = None
_started = None


def configure(trust_agent, log_path=None):
    """Called by host()/create_app() once the trust agent exists."""
    global _trust_agent, _log_path, _started
    _trust_agent, _log_path, _started = trust_agent, log_path, time.time()


# ---------------------------------------------------------------- data

def _list_entries(name):
    from ...trust.tools import list_file
    path = list_file(name, _trust_agent._co_dir)
    if not path.is_file():
        return []
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    # A wildcard is a rule, not a person; it cannot be removed as one.
    return [line for line in lines if line and not line.startswith("#") and "*" not in line]


def _joins():
    """address -> (when, how) of the latest add to contacts or whitelist."""
    joins = {}
    for entry in approvals.read(_trust_agent._co_dir, last=5000):
        tool = str(entry.get("tool", ""))
        if entry.get("path") == "trust" and (tool.startswith("add to ") or tool == "joined"):
            address = str(entry.get("subject", "")).removeprefix("key:")
            # "joined" follows its "add to contacts" and says how (invite code, payment).
            joins[address] = (entry.get("ts"), entry.get("reason") or "added")
    return joins


def caller_activity(runs):
    """Per verified caller: turns, failures, latest time. Never the prompt text."""
    from .control_center import _run_owner
    callers = {}
    for run in runs:
        owner = _run_owner(run) or "local"
        row = callers.setdefault(owner, {"turns": 0, "failed": 0, "last": 0})
        row["turns"] += 1
        row["failed"] += run.get("status") in ("failed", "interrupted")
        row["last"] = max(row["last"], float(run.get("created") or 0))
    return dict(sorted(callers.items(), key=lambda item: -item[1]["last"]))


def _admins():
    """admins.txt, without the agent's own address: that one is the agent, not a person."""
    from ...trust.tools import load_admins
    me = _trust_agent.get_self_address()
    return sorted(a for a in load_admins(_trust_agent._co_dir) if a != me and "*" not in a)


def known_names():
    """address -> the name the operator saved for it with ``co handoff``.

    The only per-address name on a Host today: trust lists hold bare addresses,
    and CONNECT carries no profile name. The book stores names lowercased as
    lookup keys, so an all-lowercase one is shown title-cased. A name that is
    itself an address (an agent met through its mailbox) is no name.
    """
    from ....handoff.transport import contacts
    names = {}
    for name, entry in contacts().items():
        if entry.get("agent") and not name.startswith("0x"):
            names[entry["agent"].lower()] = name.title() if name.islower() else name
    return names


def admitted(activity):
    """Everyone in, once, at their highest level: admin, then whitelist, then contact.

    An admin is often on contacts.txt too (they joined before they were made
    admin); listing the first file that held them called the owner a contact.
    """
    joins, names, rows, seen = _joins(), known_names(), [], set()
    for level, addresses in (("admin", _admins()), ("whitelist", _list_entries("whitelist")),
                             ("contact", _list_entries("contacts"))):
        for address in addresses:
            if address.lower() in seen:
                continue
            seen.add(address.lower())
            when, how = joins.get(address, (None, None))
            act = activity.get(address) or {}
            rows.append({"address": address, "level": level, "joined": when, "how": how,
                         "name": names.get(address.lower()), "turns": act.get("turns", 0),
                         "failed": act.get("failed", 0), "last_seen": act.get("last")})
    return rows


def invite_codes():
    from ...trust.fast_rules import _resolve_codes
    return _resolve_codes(_trust_agent.config.get("onboard", {}).get("invite_code", []))


def _invite_variable():
    """The environment variable the policy reads the code from, or None for a literal."""
    codes = _trust_agent.config.get("onboard", {}).get("invite_code", [])
    codes = [codes] if isinstance(codes, str) else codes or []
    return next((str(c)[1:] for c in codes if str(c).startswith("$")), None)


def health_facts(runs):
    """What an admin's health line adds: uptime and the last failure, any caller's."""
    if _trust_agent is None:
        return []
    now = time.time()
    failed = next((r for r in runs if r.get("status") in ("failed", "interrupted")), None)
    last = (f"last {failed.get('status')} {_since(float(failed.get('created') or now), now)}"
            if failed else "no recent failures")
    return [f"up {_since(_started, now).removesuffix(' ago')}", last]


def log_tail(lines=LOG_LINES):
    if not _log_path or not Path(_log_path).is_file():
        return None
    from .control_center import _tail_lines
    return [raw.decode("utf-8", "replace") for raw in reversed(_tail_lines(Path(_log_path), lines))]


# ---------------------------------------------------------------- commands

def run(action, payload, caller):
    """One admin command from a verified caller. Raises PermissionError for anyone else."""
    if _trust_agent is None or not _trust_agent.is_admin(caller):
        raise PermissionError("Only an admin of this Host may do that")
    if action in ("admin.remove", "admin.block"):
        return _change_person(action, str(payload.get("client_id") or "").strip())
    return _set_invite(action == "admin.rotate_invite")


def _change_person(action, client_id):
    if not client_id.startswith("0x"):
        raise ValueError("client_id must be an address")
    if _trust_agent.is_admin(client_id):
        raise ValueError("An admin is managed in admins.txt, not from here")
    if action == "admin.block":
        return {"message": _trust_agent.block(client_id, "Control Center"),
                "level": _trust_agent.get_level(client_id)}
    return {"message": _trust_agent.demote_to_stranger(client_id),
            "level": _trust_agent.get_level(client_id)}


def _set_invite(rotate):
    """Write the new code where the Host reads it, and apply it to this process.

    The policy resolves ``$CO_INVITE_CODE`` on every onboarding attempt, so
    setting it in ``os.environ`` is the whole of "applied without a restart".
    The file is so the next start agrees. Turning it off writes an empty value,
    which resolves to no code: a closed door (#561).
    """
    from ....cli.commands.project_cmd_lib import mint_invite_code
    from ....env_file import upsert_env
    from ....environment import process_environment, publish_values

    variable = _invite_variable()
    if variable is None:
        raise ValueError("This policy writes its invite code literally; edit the policy instead")
    inherited = variable in process_environment()
    code = mint_invite_code() if rotate else ""
    path = _invite_env_file(variable)
    upsert_env(path, {variable: code})
    publish_values({variable: code})
    return {"invite_code": code or None, "file": str(path),
            # A service environment (systemd EnvironmentFile, a shell export)
            # outranks every file on the next start.
            "survives_restart": not inherited}


def _invite_env_file(variable):
    """The project's .env when it holds the code, else keys.env when that does, else .env."""
    from ....environment import read_env_file, selected_env_file
    project_env = _trust_agent._co_dir.parent / ".env"
    if variable in read_env_file(project_env):
        return project_env
    if variable in read_env_file(selected_env_file()):
        return selected_env_file()
    return project_env


# ---------------------------------------------------------------- render

def _short(address):
    """``0x48a0…fbee``: enough to tell two people apart, short enough for a row."""
    return address if len(address) <= 14 else f"{address[:6]}…{address[-4:]}"


def _since(timestamp, now):
    from .control_center import _ago
    return _ago(now - timestamp)


def _iso_ago(stamp, now):
    from datetime import datetime
    return _since(datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp(), now)


def render(agent_metadata, runs, fragments):
    """``(People card, people count)``, or ``("", 0)`` when this is not a configured Host."""
    if _trust_agent is None:
        return "", 0
    now = time.time()
    people = admitted(caller_activity(runs))
    names = {p["address"]: p["name"] for p in people if p["name"]}
    rows = [_person(person, now, fragments) for person in people] or [
        _person({"address": "", "name": "Nobody has joined yet", "level": ""}, now, fragments)]
    extras = [_invite(fragments), _waiting(runs, names, now, fragments)]
    html = fragments["admin"].safe_substitute(
        count=f"{len(people)} {'person' if len(people) == 1 else 'people'}",
        rows="\n".join(rows), extras="\n".join(e for e in extras if e)).strip()
    return "    " + html, len(people)


def _button(fragments, action, label, target="", tone=""):
    return fragments["admin_button"].safe_substitute(
        action=action, target=escape(target, quote=True), label=label, tone=tone).strip()


def _sub(fragments, label, value, actions="", mono=""):
    return fragments["admin_sub"].safe_substitute(
        label=label, value=escape(value), actions=actions, mono=mono).strip()


def _person(person, now, fragments):
    """One row: name or short address, role, and what they have been doing."""
    address, level = person["address"], person["level"]
    actions = ""
    if level in ("whitelist", "contact"):
        actions = (_button(fragments, "remove", "Remove", address)
                   + _button(fragments, "block", "Block", address, "danger"))
    return fragments["person"].safe_substitute(
        what=escape(person["name"] or _short(address)), mono="" if person["name"] else "mono",
        role=level, meta=escape(" · ".join(_person_meta(person, now))), actions=actions).strip()


def _person_meta(person, now):
    meta = [_short(person["address"])] if person["name"] and person["address"] else []
    turns = person.get("turns")
    if turns:
        meta.append(f"{turns} turn{'s' if turns != 1 else ''}")
    if person.get("failed"):
        meta.append(f"{person['failed']} failed")
    if person.get("last_seen"):
        meta.append(f"seen {_since(person['last_seen'], now)}")
    elif person["level"] in ("whitelist", "contact"):
        meta.append("not seen yet")
        if person.get("joined"):
            meta.append(f"joined {_iso_ago(person['joined'], now)}")
    # "added" is the record's word for "no reason given": it says nothing.
    if person.get("how") not in (None, "added") and person["level"] != "admin":
        meta.append(person["how"])
    return meta


def _invite(fragments):
    if _invite_variable() is None:
        return ""
    codes = invite_codes()
    if codes:
        actions = (_button(fragments, "rotate_invite", "New code")
                   + _button(fragments, "invite_off", "Turn off", tone="danger"))
        return _sub(fragments, "Invite code", codes[0], actions, "mono")
    return _sub(fragments, "Invite code", "Off · nobody can join with a code",
                _button(fragments, "rotate_invite", "Turn on", tone="primary"))


def _waiting(runs, names, now, fragments):
    """Runs any caller left waiting for an admin's approval, by who and when."""
    from .control_center import _run_owner
    waiting = [r for r in runs if r.get("status") == "waiting_approval"]
    if not waiting:
        return ""
    who = ", ".join(names.get(_run_owner(r) or "", _short(_run_owner(r) or "local")) for r in waiting)
    oldest = min(float(r.get("created") or now) for r in waiting)
    return _sub(fragments, f"Waiting for approval · asked {_since(oldest, now)} · answer it in that chat", who)


def render_log(fragments):
    """The log tail behind one disclosure: forty lines do not fit on one."""
    if _trust_agent is None:
        return ""
    lines = log_tail()
    if lines is None:
        return '<p>No log file here: the service manager keeps the console output.</p>'
    return fragments["admin_log"].safe_substitute(
        count=f"last {len(lines)} lines", text=escape("\n".join(lines))).strip()
