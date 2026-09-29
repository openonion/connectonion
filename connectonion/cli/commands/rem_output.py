"""Plain, pipe-friendly co rem output. JSON serialization stays in the command layer."""

import os
import re
import shutil
import sys
from datetime import datetime


class StageProgress:
    """init's progress: one line per stage, not one per step (#1943).

    The owner's own 90-day init printed 15,498 lines -- a `listed gmail mail
    DATE to DATE` for every seven-day window and a `saving mail bodies` every 25
    messages -- and the summary scrolled away under them. A terminal now sees
    each stage as one line rewritten in place; a pipe or a log sees the finished
    line of each stage once. Every step still goes to `log`, a file, for anyone
    diagnosing a slow or partial run.
    """

    def __init__(self, stream=None, log=None, quiet=False):
        self.stream = stream or sys.stderr
        self.tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.quiet, self.log = quiet, log
        self.stage, self.line, self.listed = None, "", {}
        if log:
            # Owner-only like the rest of .state; replaced on every run.
            os.close(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600))

    def __call__(self, message, count=None):
        if self.log:
            with open(self.log, "a", encoding="utf-8") as handle:
                stamp = datetime.now().isoformat(timespec="seconds")
                handle.write(f"{stamp} {message}" + ("" if count is None else f": {count}") + "\n")
        stage, text = self._describe(message, count)
        if stage != self.stage:
            self._finish()
            self.stage = stage
        self.line = "co rem init: " + text
        if self.tty and not self.quiet:
            width = shutil.get_terminal_size((100, 20)).columns - 1
            self.stream.write("\r\033[K" + self.line[:width])
            self.stream.flush()

    def _describe(self, message, count):
        mail = re.match(r"(listed|scanning|scanned) (\w+) mail", message)
        if mail:
            verb, kind = mail.groups()
            if verb == "listed":
                self.listed[kind] = self.listed.get(kind, 0) + (count or 0)
                end = re.search(r" to (\d{4}-\d{2}-\d{2})", message)
                return kind, (f"{kind}: listing mail, {self.listed[kind]:,} so far"
                              + (f" (to {end.group(1)})" if end else ""))
            if verb == "scanning":
                return kind, f"{kind}: listing mail..."
            return kind, f"{kind}: {self.listed.get(kind, 0):,} messages listed, {count or 0:,} correspondents"
        stage = ("mail bodies" if message.startswith("saving mail bodies") else
                 "skills" if "skills" in message else "projects" if "project" in message else message)
        if count is None:
            return stage, message + "..."
        return stage, f"{message}: {count:,}" if isinstance(count, int) else f"{message}: {count}"

    def _finish(self):
        if self.stage is not None and not self.quiet:
            self.stream.write("\n" if self.tty else self.line + "\n")
            self.stream.flush()

    def close(self):
        self._finish()
        self.stage = None

EMPTY = {
    'investigate': 'No pages available to investigate. Run init to build the map first.',
    'list': 'No pages found. Run init to build the map.',
    'unfinished': 'No unfinished pages found. This does not certify content quality.',
    'logs': 'No runs recorded. Initialization alone does not run investigation.',
    'review': 'No review candidates waiting.',
    'people': 'No people mapped. Init can map connected mailboxes.',
    'reflections': 'No reflections recorded.',
    'search': 'No matching pages. Try another phrase or browse the page list.',
    'scan': 'No matching sources found in this window.',
}


def _label(key):
    return str(key).replace('_', ' ').capitalize()


def _scalar(value):
    if value is None:
        return 'Unknown'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    return str(value)


def _lines(value, indent=0, raw_keys=False):
    """Keep every result field, including partial coverage and nested errors."""
    pad = ' ' * indent
    if isinstance(value, dict):
        if not value:
            return [pad + 'None']
        lines = []
        for key, item in value.items():
            if key == 'warning' and item == '':
                continue  # a batch with nothing to warn about printed a bare "Warning: "
            label = str(key) if raw_keys else _label(key)
            if isinstance(item, (dict, list)) and item:
                lines.append(pad + label + ':')
                lines.extend(_lines(item, indent + 2, key in ('by_stage', 'by_model', 'by_source', 'items_by_source', 'sources', 'usage_by_stage')))
            else:
                text = 'None' if isinstance(item, (dict, list)) else _scalar(item)
                lines.append(pad + label + ': ' + text.replace('\n', '\n' + pad + '  '))
        return lines
    if isinstance(value, list):
        lines = []
        for number, item in enumerate(value, 1):
            if isinstance(item, (dict, list)):
                lines.append(pad + f'{number}.')
                lines.extend(_lines(item, indent + 2))
            else:
                lines.append(pad + _scalar(item))
        return lines or [pad + 'None']
    return [pad + _scalar(value)]


def render(value, command: str, *, failed: bool = False) -> str:
    """Render readable results without interpreting source text as terminal markup."""
    if isinstance(value, str):
        text = ('Error: ' if failed else '') + value
    elif command == 'init' and isinstance(value, dict):
        # The complete map is persisted and available through --json. Printing
        # every contact, subject and installed skill made a normal first run
        # thousands of lines long and buried the next action.
        title = 'co rem init' + (' — needs attention' if failed else '')
        skills = value.get('skills') or {}
        skill_count = len(skills.get('skills') or []) if isinstance(skills, dict) else len(skills)
        skill_names = (len({str(row.get('name', '')).casefold() for row in skills.get('skills') or []})
                       if isinstance(skills, dict) else skill_count)
        skills_created = len(skills.get('created') or []) if isinstance(skills, dict) else 0
        text = '\n'.join([
            title, '',
            f"Map: {value.get('phase', 'unknown')} · {value.get('days', '?')} days",
            *(f"{label}: {len(value.get(kind) or [])}"
              for kind, label in (('people', 'People'), ('orgs', 'Organizations'),
                                  ('projects', 'Projects'))),
            f"Skills: {skill_names} names ({skill_count} installed copies)",
            f"New pages: {len(value.get('created') or []) + skills_created}",
            'Detailed map: .state/map.json inside this co rem root (or rerun with --json).',
            *(f"{error.get('source', 'source')}: {error.get('error', 'unavailable')}"
              for error in value.get('errors') or []),
            # The one page with value before any model runs (#1943): print it.
            *(['', f"Your page: {owner['title']}", *(f"  {fact}" for fact in owner['facts']),
               f"  {owner['path']}"] if (owner := value.get('owner_page')) else []),
            *([''] if value.get('confirm_own_addresses') else []),
            *(value.get('confirm_own_addresses') or []),
            *(value.get('tips') or []),
            *([value['people_setup']] if value.get('people_setup') else []),
            *([value['recovery']] if value.get('recovery') else []),
        ])
    else:
        title = 'co rem ' + ('status' if command == 'rem' else command.replace('-', ' '))
        if command in ('status', 'rem') and isinstance(value, dict):
            value = dict(value)
            if str(value.get('state', '')).startswith('Not started'):
                value['state'] = 'Background maintenance has not started. Map building and investigation are separate steps.'
        if failed:
            title += ' — needs attention'
        if value == []:
            text = title + '\n\n' + EMPTY.get(command, 'No results found.')
        else:
            text = title + '\n\n' + '\n'.join(_lines(value, raw_keys=command == 'subscriptions'))
        if command == 'people' and value and not failed:
            text += '\n\nThe Next command lists page paths directly; no extra flags are needed.'
        if command == 'init' and not failed:
            text += '\n\nMap initialized. Investigation has not started; the Next line begins with your own page.'
    return ''.join(char for char in text if char in '\n\t' or (ord(char) >= 32 and not 127 <= ord(char) <= 159))


def guide(next_command) -> str:
    """One workflow shared by the overview and --help, with root-aware commands."""
    paragraphs = [
        "co rem — map first, investigate next",
        "First run: " + next_command(["init"]) +
        ". A script (no model) creates People, Organizations, Projects and Skills from templates and "
        "source metadata and prints your own page; then, in a terminal, it writes your own page with one "
        "model turn, after saying what it will spend (--no-investigate skips that). It starts no background "
        "work. Then read it with " + next_command(["open"]) + " and keep it current with " +
        next_command(["start"]) + ".",
        "Choose a page: Run " + next_command(["investigate"]) +
        " without arguments to list your actual pages; no model runs. Copy its Next command to investigate one page. "
        "Do not invent page paths from examples. An exact title or email may select one unique page; "
        "for multiple matches, use an exact path from the choices. An empty list means initialize the map first.",
        "Check the result: Follow the printed show command, or browse with " + next_command(["open"]) +
        ". Review sources, Unknown sections and partial coverage. Command success alone does not prove factual quality. "
        "Find remaining work with " + next_command(["unfinished"]) + ".",
        "Update later: Preview pending metadata with " + next_command(["sync", "--dry-run"]) +
        ", then use " + next_command(["sync"]) + " once source access is authorized. "
        "Source access is authorized through start, which also installs a background schedule; "
        "do not treat it as an initialization step. Inspect outcomes and failures with " + next_command(["logs"]) + ".",
        "Calling convention: Keep --root before the subcommand in every call. JSON is opt-in: " +
        next_command(["--json", "status"]) + ". Read ok/data/next in JSON mode; otherwise follow the printed Next command. "
        "Exit 1 reports an operation failure; exit 2 is an argument/command error. "
        "Append --help to any command to learn its workflow and options; --help displays instructions and never executes the task.",
    ]
    return "\n\n".join(paragraphs) + "\n"
