"""Keys (#3137, owner 2026-11-19: «类似于 LastPass 或者 1Password 那种，管理密钥或者管理密码的»).

A ``keys/<slug>.md`` page says what a secret is; ``vault`` keeps its value. Adding a key writes both, reading
one goes through the vault's prompt, and importing a password manager's CSV export files every row the same
way. Nothing here ever writes a secret into a page, a log or a reply; ``key_shape_errors`` refuses a keys page
that carries one, so even a model's draft cannot put it there.
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

from . import vault
from .files import KEY_SHAPES, Notebook, RemError

FIELDS = ("Service", "Account", "Purpose", "Who else has it", "Used in", "Created", "Rotated", "Expires", "Link", "Vault")
# Column names the common exports use, lower-cased: 1Password, LastPass, Bitwarden, Chrome/Safari.
COLUMNS = {
    "service": ("title", "name", "service"),
    "account": ("username", "login_username", "user name", "login", "email"),
    "secret": ("password", "login_password", "secret"),
    "link": ("url", "website", "login_uri", "uri"),
    "notes": ("notes", "extra", "note", "notesplain"),
}


def slug(service: str, account: str = "") -> str:
    words = re.sub(r"[^a-z0-9]+", "-", f"{service} {account}".lower()).strip("-")[:80].strip("-")
    if not words:
        raise RemError("A key needs a service name")
    return words


def page(service: str, account: str, *, purpose: str = "", link: str = "", created: str = "", key: str) -> str:
    """The page for one key: its facts and a note on where the value is. Never the value."""
    values = {"Service": service, "Account": account or "Unknown", "Purpose": purpose or "Unknown",
              "Who else has it": "Unknown", "Used in": "Unknown", "Created": created or date.today().isoformat(),
              "Rotated": "Unknown", "Expires": "Unknown", "Link": link or "Unknown",
              "Vault": f"macOS Keychain ({vault.service_name(key)})"}
    facts = "\n".join(f"- {field}: {values[field]}" for field in FIELDS)
    return (f"# {service}\n\n## Facts\n{facts}\n\n## Notes\nThe secret is in this Mac's Keychain, not in this notebook. "
            "Copy it from the reader on this Mac.\n")


def add(root, service: str, account: str, secret: str, *, purpose: str = "", link: str = "") -> str:
    """File one key: the value to the vault first, then its page. Returns the page's record path."""
    service, account = service.strip(), account.strip()
    if not service:
        raise RemError("A key needs a service name")
    key = slug(service, account)
    record = f"keys/{key}.md"
    vault.put(key, account, secret)
    book = Notebook(Path(root))
    if not book.path(record).exists():
        book.write(record, page(service, account, purpose=purpose, link=_link(link), key=key))
    return record


def _link(value: str) -> str:
    """A login URL keeps its site, never a query (some exports carry tokens in it)."""
    return re.sub(r"[?#].*$", "", (value or "").strip())


def reveal(root, record: str) -> str:
    """The secret behind one keys page, through the vault's own prompt."""
    if not re.fullmatch(r"keys/[a-z0-9][a-z0-9-]*\.md", record or "") or not Notebook(Path(root)).path(record).exists():
        raise RemError("No such key page")
    return vault.get(record[len("keys/"):-len(".md")])


def _column(header: list[str], kind: str) -> int | None:
    names = [name.strip().lower() for name in header]
    return next((names.index(name) for name in COLUMNS[kind] if name in names), None)


def import_csv(root, text: str) -> dict:
    """Every row of a password manager's CSV export: the value to the vault, a page per key.

    Returns counts only (filed, skipped), never names or values, so the reply can be shown or logged safely."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise RemError("The file is empty")
    header, body = rows[0], rows[1:]
    where = {kind: _column(header, kind) for kind in COLUMNS}
    if where["service"] is None and where["link"] is None or where["secret"] is None:
        raise RemError("This does not look like a password export: it needs a name or URL column and a password column")
    filed = skipped = 0
    for row in body:
        cell = lambda kind: row[where[kind]].strip() if where[kind] is not None and where[kind] < len(row) else ""  # noqa: E731
        service = cell("service") or re.sub(r"^https?://(www\.)?|/.*$", "", cell("link"))
        if not service or not cell("secret"):
            skipped += 1
            continue
        add(root, service, cell("account"), cell("secret"), link=cell("link"))
        filed += 1
    return {"filed": filed, "skipped": skipped}


class KeyImportError(RemError):
    """An import that could not run, with a `code` the reader turns into what to do (#3305)."""

    def __init__(self, message: str, code: str = "failed"):
        super().__init__(message)
        self.code = code


NO_GUI = ("REM's Host is running outside your login session (it was restarted by a background process), so macOS "
          "cannot show the Keychain prompt. Run `co rem open` in this Mac's Terminal, then import again.")


def _need_prompt() -> None:
    """Refuse before reading anything when this Host cannot show the system prompt: it would only fail."""
    from .live_host import launch_session
    if launch_session() not in ("Aqua", ""):
        raise KeyImportError(NO_GUI, "no_gui")


def _site(url: str) -> str:
    return re.sub(r"^https?://(www\.)?|/.*$", "", url) or url


def _file_logins(root, logins) -> dict:
    """Each login's value to the vault and a page per key; the reply names sites, never an account or value."""
    filed = skipped = 0
    sites = []
    for login in logins:
        service = _site(login["url"])
        if not service or not login["password"]:
            skipped += 1
            continue
        add(root, service, login["username"], login["password"], link=login["url"])
        filed += 1
        sites.append(service)
    return {"filed": filed, "skipped": skipped, "sites": sorted(set(sites))}


def import_browser(root, browser: str = "chrome") -> dict:
    """Every saved login in a browser's vault (Chrome/Edge/Brave): the value to the OS vault, a page per key.

    Returns counts and site names only, never an account or value, so the reply is safe to show.
    """
    from ..useful_tools import chrome_passwords, macos_keychain
    _need_prompt()
    try:
        logins = chrome_passwords.all_logins(browser)
    except chrome_passwords.ChromeError as error:
        raise KeyImportError(str(error), "no_data")
    except macos_keychain.KeychainError as error:
        raise KeyImportError(NO_GUI if error.code == "no_gui" else str(error), error.code)
    return _file_logins(root, logins)


def import_keychain(root) -> dict:
    """The login keychain's internet passwords: listing asks nothing, and macOS asks once per value read.

    A declined or unanswered prompt stops the import there; what was filed stays filed and the reply says so.
    """
    from ..useful_tools import macos_keychain
    _need_prompt()
    try:
        items = macos_keychain.internet_passwords()
    except macos_keychain.KeychainError as error:
        raise KeyImportError(str(error), error.code)
    logins, stopped = [], ""
    for item in items:
        try:
            secret = macos_keychain.internet_password(item["server"], item["account"])
        except macos_keychain.KeychainError as error:
            if error.code == "not_found":
                continue
            if error.code == "no_gui" and not logins:
                raise KeyImportError(NO_GUI, "no_gui")
            stopped = error.code
            break
        logins.append({"url": item["server"], "username": item["account"], "password": secret})
    result = _file_logins(root, logins)
    return {**result, "stopped": stopped} if stopped else result


def env_names(path: Path | None = None) -> dict:
    """The names of co's own credentials in keys.env and where that file is: never a value (#3305)."""
    from ..environment import EnvironmentError as EnvFileError, display_path, parse_env_file, selected_env_file
    path = path or selected_env_file()
    if not path.exists():
        return {"where": display_path(path), "names": []}
    try:
        bindings = parse_env_file(path)
    except EnvFileError as error:  # its message names the line, never a value
        return {"where": display_path(path), "names": [], "error": str(error)}
    names = [item.key for item in bindings if item.key and item.key != "AGENT_CONFIG_PATH"]
    names = sorted(dict.fromkeys(names))
    return {"where": display_path(path), "names": names, **env_groups(names)}


# What counts as a credential in keys.env (#3326): a name that ENDS in a secret word. GOOGLE_ACCESS_TOKEN and
# OPENAI_API_KEY are credentials; GOOGLE_TOKEN_EXPIRES_AT, GOOGLE_SCOPES, IS_EMAIL_ACTIVE, CO_BROWSER_ENGINE and
# AGENT_ADDRESS are settings. The owner read 29 raw variable names as "29 keys" next to "you have no keys".
SECRET_NAME = re.compile(r"(?:^|_)(?:API_KEY|KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|PAT|CREDENTIALS?)$")
# The service a variable belongs to, by its first word; anything unlisted is named after that word.
SERVICES = {"GOOGLE": "Google", "GMAIL": "Google", "GEMINI": "Google", "YOUTUBE": "Google", "GDRIVE": "Google",
            "MICROSOFT": "Microsoft", "OUTLOOK": "Microsoft", "MS": "Microsoft", "AZURE": "Microsoft",
            "LARK": "Lark", "FEISHU": "Lark", "OPENAI": "OpenAI", "ANTHROPIC": "Anthropic", "CLAUDE": "Anthropic",
            "OPENONION": "OpenOnion", "CO": "OpenOnion", "GITHUB": "GitHub", "GH": "GitHub", "SLACK": "Slack",
            "DISCORD": "Discord", "TELEGRAM": "Telegram", "WHATSAPP": "WhatsApp", "LINEAR": "Linear",
            "ASANA": "Asana", "CANNY": "Canny", "NOTION": "Notion", "SYNO": "Synology", "SYNOLOGY": "Synology",
            "FREESOUND": "Freesound", "STRIPE": "Stripe", "AWS": "AWS", "DEEPSEEK": "DeepSeek"}


def env_groups(names: list[str]) -> dict:
    """Credentials grouped by service with a count, and the settings apart: names only, never a value."""
    services: dict[str, int] = {}
    settings = []
    for name in names:
        if not SECRET_NAME.search(name):
            settings.append(name)
            continue
        word = name.split("_", 1)[0]
        service = SERVICES.get(word, word.title())
        services[service] = services.get(service, 0) + 1
    return {"services": [{"service": name, "count": count} for name, count in sorted(services.items())],
            "settings": settings}


def _entropy(token: str) -> float:
    counts = Counter(token)
    return -sum(n / len(token) * math.log2(n / len(token)) for n in counts.values())


def key_shape_errors(record: str, candidate: str) -> list[str]:
    """A page may not carry a secret: known key shapes anywhere; on a keys page, any long random-looking token
    outside its Sources, since a password copied into Facts or Notes reads like one. Says where, never what."""
    errors = []
    if KEY_SHAPES.search(candidate):
        errors.append("The page carries something shaped like a key or token; keep secrets in the vault, never in a page")
    if record.startswith("keys/"):
        body = re.split(r"\n## Sources\b", candidate, maxsplit=1)[0]
        for token in re.findall(r"(?<![\w/.:@-])[A-Za-z0-9+/=_!$%*#-]{16,}(?![\w/.:@-])", body):
            classes = sum(bool(re.search(p, token)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
            if classes >= 3 and _entropy(token) >= 3.5:
                errors.append("A keys page carries a random-looking string (a password?); the value belongs in the vault")
                break
    return errors
