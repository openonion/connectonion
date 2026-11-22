"""The admin section of the Control Center: who is in, the invite, activity, health, log.

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


def admitted(activity):
    """Everyone on the whitelist or contacts, once, with how and when they got in."""
    joins, rows, seen = _joins(), [], set()
    for level, name in (("whitelist", "whitelist"), ("contact", "contacts")):
        for address in _list_entries(name):
            if address.lower() in seen:
                continue
            seen.add(address.lower())
            when, how = joins.get(address, (None, None))
            rows.append({"address": address, "level": level, "joined": when, "how": how,
                         "last_seen": (activity.get(address) or {}).get("last")})
    return rows


def invite_codes():
    from ...trust.fast_rules import _resolve_codes
    return _resolve_codes(_trust_agent.config.get("onboard", {}).get("invite_code", []))


def _invite_variable():
    """The environment variable the policy reads the code from, or None for a literal."""
    codes = _trust_agent.config.get("onboard", {}).get("invite_code", [])
    codes = [codes] if isinstance(codes, str) else codes or []
    return next((str(c)[1:] for c in codes if str(c).startswith("$")), None)


def health(agent_metadata, runs):
    from .... import __version__
    from ...relay import connection
    failed = next((r for r in runs if r.get("status") in ("failed", "interrupted")), None)
    return {"model": agent_metadata.get("model"), "version": __version__,
            "relay": dict(connection), "started": _started, "last_error": failed}


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
    return address if len(address) <= 18 else f"{address[:10]}…{address[-6:]}"


def _since(timestamp, now):
    from .control_center import _ago
    return _ago(now - timestamp)


def _iso_ago(stamp, now):
    from datetime import datetime
    return _since(datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp(), now)


def render(agent_metadata, runs, fragments):
    """The whole admin card, or "" when this process is not a configured Host."""
    if _trust_agent is None:
        return ""
    now = time.time()
    activity = caller_activity(runs)
    people = admitted(activity)
    blocks = [
        _people_block(people, now, fragments),
        _invite_block(fragments),
        _activity_block(activity, now, fragments),
        _approvals_block(runs, now, fragments),
        _health_block(health(agent_metadata, runs), now, fragments),
        _log_block(fragments),
    ]
    return fragments["admin"].safe_substitute(
        count=f"{len(people)} admitted",
        blocks="\n".join(block for block in blocks if block)).strip()


def _button(fragments, action, label, target="", tone=""):
    return fragments["admin_button"].safe_substitute(
        action=action, target=escape(target, quote=True), label=label, tone=tone).strip()


def _row(fragments, what, meta, actions="", mono=""):
    return fragments["admin_row"].safe_substitute(
        what=escape(what), meta=escape(meta), actions=actions, mono=mono).strip()


def _block(fragments, title, rows):
    return fragments["admin_block"].safe_substitute(title=title, rows="\n".join(rows)).strip()


def _people_block(people, now, fragments):
    if not people:
        return _block(fragments, "Admitted", [_row(fragments, "Nobody has joined yet", "")])
    rows = []
    for person in people:
        meta = [person["level"]]
        if person["how"]:
            meta.append(person["how"])
        if person["joined"]:
            meta.append(f"joined {_iso_ago(person['joined'], now)}")
        meta.append(f"seen {_since(person['last_seen'], now)}" if person["last_seen"] else "not seen")
        actions = (_button(fragments, "remove", "Remove", person["address"])
                   + _button(fragments, "block", "Block", person["address"], "danger"))
        rows.append(_row(fragments, person["address"], " · ".join(meta), actions, "mono"))
    return _block(fragments, f"Admitted · {len(people)}", rows)


def _invite_block(fragments):
    variable = _invite_variable()
    if variable is None:
        return ""
    codes = invite_codes()
    if codes:
        actions = (_button(fragments, "rotate_invite", "Rotate")
                   + _button(fragments, "invite_off", "Turn off", tone="danger"))
        row = _row(fragments, codes[0], "On · give it only to people you let in", actions, "mono")
    else:
        row = _row(fragments, "Off", "Nobody can join with a code",
                   _button(fragments, "rotate_invite", "Turn on"))
    return _block(fragments, "Invite code", [row])


def _activity_block(activity, now, fragments):
    if not activity:
        return ""
    rows = []
    for owner, row in activity.items():
        meta = f"{row['turns']} turn{'s' if row['turns'] != 1 else ''}"
        if row["failed"]:
            meta += f" · {row['failed']} failed"
        if row["last"]:
            meta += f" · {_since(row['last'], now)}"
        rows.append(_row(fragments, _short(owner), meta, mono="mono"))
    return _block(fragments, "Activity by caller", rows)


def _approvals_block(runs, now, fragments):
    from .control_center import _run_owner
    waiting = [r for r in runs if r.get("status") == "waiting_approval"]
    if not waiting:
        return ""
    rows = [_row(fragments, _short(_run_owner(r) or "local"),
                 f"asked {_since(float(r.get('created') or now), now)} · answer it in that chat",
                 mono="mono") for r in waiting]
    return _block(fragments, "Waiting for approval", rows)


def _health_block(facts, now, fragments):
    relay = facts["relay"]
    if relay["state"] == "never":
        relay_text = "not connected"
    else:
        relay_text = f"{relay['state']} · {_since(relay['since'], now)}"
    failed = facts["last_error"]
    last_error = "none recent"
    if failed:
        last_error = f"{failed.get('status')} · {_since(float(failed.get('created') or now), now)}"
    rows = [("Model", facts["model"] or "unknown"), ("Version", facts["version"]),
            ("Relay", relay_text),
            ("Up", _since(facts["started"], now).replace(" ago", "") if facts["started"] else "unknown"),
            ("Last error", last_error)]
    return _block(fragments, "Health", [
        fragments["diag"].safe_substitute(label=label, value=escape(str(value)), **{"class": ""}).strip()
        for label, value in rows])


def _log_block(fragments):
    lines = log_tail()
    if lines is None:
        return _block(fragments, "Log", [_row(fragments, "This Host keeps no log file",
                                              "its service writes the console output")])
    return fragments["admin_log"].safe_substitute(
        count=f"last {len(lines)} lines", text=escape("\n".join(lines))).strip()
