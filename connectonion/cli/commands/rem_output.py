"""Plain, pipe-friendly co rem output. JSON serialization stays in the command layer."""

import os
import re
import sys
from datetime import datetime

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .. import style


def _terminal(stream) -> Console:
    """A console on `stream` in the shared palette; only built for a stream that is a terminal."""
    return Console(file=stream, theme=style.THEME, highlight=False, soft_wrap=True, force_terminal=True)


class StageProgress:
    """init's progress: one line per stage, not one per step (#1943).

    The owner's own 90-day init printed 15,498 lines -- a `listed gmail mail
    DATE to DATE` for every seven-day window and a `saving mail bodies` every 25
    messages -- and the summary scrolled away under them. A pipe or a log sees
    the finished line of each stage once. A terminal sees each stage drawn
    live (#1996): a bar when its size is known -- the seven-day mail windows,
    message bodies i/N, session files, skills -- a spinner when not, and the
    stage's finished line kept above it. Every step still goes to `log`, a
    file, for anyone diagnosing a slow or partial run.
    """

    def __init__(self, stream=None, log=None, quiet=False, days=None):
        self.stream = stream or sys.stderr
        self.tty = bool(getattr(self.stream, "isatty", lambda: False)())
        self.quiet, self.log = quiet, log
        self.stage, self.line, self.listed, self.windows = None, "", {}, {}
        self.window_total = -(-days // 7) if days else None   # init lists mail seven days at a time
        self.bar, self.task = None, None
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
        # A finished stage is ✓ and what it found, in a pipe as in a terminal
        # (1.9.0a9); "co rem init: " before every line was the program's name
        # said six times over its own output.
        self.line = "✓ " + text
        if self.tty and not self.quiet:
            self._draw(text, *self._size(message, count))

    def _describe(self, message, count):
        mail = re.match(r"(listed|scanning|scanned) (\w+) mail", message)
        if mail:
            verb, kind = mail.groups()
            if verb == "listed":
                self.listed[kind] = self.listed.get(kind, 0) + (count or 0)
                self.windows[kind] = self.windows.get(kind, 0) + 1
                end = re.search(r" to (\d{4}-\d{2}-\d{2})", message)
                return kind, (f"{kind}: listing mail, {self.listed[kind]:,} so far"
                              + (f" (to {end.group(1)})" if end else ""))
            if verb == "scanning":
                return kind, f"{kind}: listing mail..."
            listed, count = self.listed.get(kind, 0), count or 0
            return kind, (f"{kind}: {listed:,} message{'' if listed == 1 else 's'} listed, "
                          f"{count:,} correspondent{'' if count == 1 else 's'}")
        stage = ("mail bodies" if message.startswith("saving mail bodies") else
                 "skills" if "skills" in message else "projects" if "project" in message else message)
        if count is None:
            return stage, message + "..."
        return stage, f"{message}: {count:,}" if isinstance(count, int) else f"{message}: {count}"

    def _size(self, message, count):
        """(done, total) for a bar, or (None, None) for a spinner."""
        mail = re.match(r"(listed|scanning|scanned) (\w+) mail", message)
        if mail and self.window_total:
            return min(self.windows.get(mail.group(2), 0), self.window_total), self.window_total
        steps = re.fullmatch(r"(\d+)/(\d+)", str(count))
        if steps:
            return int(steps.group(1)), int(steps.group(2))
        return (count, count) if isinstance(count, int) and count else (None, None)   # a stage's result: done

    def _draw(self, text, done, total):
        if self.bar is None:
            self.bar = style.progress(_terminal(self.stream))
            self.bar.start()
        if self.task is None:
            self.task = self.bar.add_task(text, total=total)
        self.bar.update(self.task, description=text, completed=done, total=total, refresh=True)

    def _finish(self):
        if self.stage is None or self.quiet:
            return
        if not self.tty:
            self.stream.write(self.line + "\n")
            self.stream.flush()
        elif self.bar is not None:
            from .rem_look import highlight
            self.bar.remove_task(self.task)
            self.task = None
            self.bar.console.print(style.ok(self.line[:1]) + " " + highlight(self.line[2:], counts=True), emoji=False)

    def close(self):
        self._finish()
        self.stage = None
        if self.bar is not None:
            self.bar.stop()
            self.bar = None


class Turn:
    """One model turn, which can take ten minutes: in a terminal a spinner with the time so far
    ("Writing your page… 3:12", #1996); anywhere else one line per stage, as before."""

    def __init__(self, label, stream=None):
        self.label, self.stream = label, stream or sys.stderr
        self.bar = None
        if getattr(self.stream, "isatty", lambda: False)():
            self.bar = Progress(SpinnerColumn(), TextColumn("{task.description}"),
                                TimeElapsedColumn(), console=_terminal(self.stream), transient=True)

    def __enter__(self):
        if self.bar is not None:
            from . import rem_look
            self.bar.start()
            self.task = self.bar.add_task(self.label)
            rem_look.LIVE = self.bar.console   # progress lines print above the spinner, not over it
        return self

    def stage(self, text):
        if self.bar is None:
            # A stage once, not once per count: "gathering codex sessions: 40
            # scanned" printed about 25 times with nothing new (#2044).
            name = re.sub(r"[:(]\s*[\d,/]+.*$", "", text).strip()
            if name != getattr(self, "said", None):
                self.said = name
                typer.echo(f"Investigation: {text}", err=True)
        else:
            self.bar.update(self.task, description=f"{self.label} {style.muted('(' + text + ')')}")

    def __exit__(self, *exc):
        if self.bar is not None:
            from . import rem_look
            rem_look.LIVE = None
            self.bar.stop()

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


def _init_text(value: dict, failed: bool) -> str:
    """init's map in status's layout (1.9.0a9): a label in the margin, counts right-aligned at one column.

    The complete map is persisted and available through --json. Printing every
    contact, subject and installed skill made a normal first run thousands of
    lines long and buried the next action.
    """
    from .rem_look import BROKEN, COLUMN
    skills = value.get('skills') or {}
    skill_count = len(skills.get('skills') or []) if isinstance(skills, dict) else len(skills)
    skill_names = (len({str(row.get('name', '')).casefold() for row in skills.get('skills') or []})
                   if isinstance(skills, dict) else skill_count)
    skills_created = len(skills.get('created') or []) if isinstance(skills, dict) else 0
    counts = [('People', len(value.get('people') or []), ''),
              ('Organizations', len(value.get('orgs') or []), ''),
              ('Projects', len(value.get('projects') or []), ''),
              ('Skills', skill_names, f" names · {skill_count:,} installed copies"),
              ('New pages', len(value.get('created') or []) + skills_created, '')]
    wide = max(len(f"{number:,}") for _, number, _ in counts)

    def labelled(label, text):
        return label + ' ' * (COLUMN - len(label)) + text
    title = 'co rem init' + (' — needs attention' if failed else
                             f" · {value.get('phase', 'unknown')} · {value.get('days', '?')} days")
    lines = [title, '', *(labelled(label, f"{number:,}".rjust(wide) + tail) for label, number, tail in counts),
             labelled('Detailed map', '.state/map.json in this notebook, or rerun with --json')]
    for error in value.get('errors') or []:
        source = str(error.get('source', 'source'))
        lines.append(f"  {BROKEN} {source}" + ' ' * max(1, COLUMN - 4 - len(source)) + str(error.get('error', 'unavailable')))
    owner = value.get('owner_page')
    if owner:
        # The one page with value before any model runs (#1943): print it.
        lines += ['', labelled('Your page', owner['title']),
                  *(' ' * COLUMN + fact for fact in owner['facts']), ' ' * COLUMN + owner['path']]
    lines += [*([''] if value.get('confirm_own_addresses') else []), *(value.get('confirm_own_addresses') or []),
              *(value.get('tips') or []), *([value['people_setup']] if value.get('people_setup') else []),
              *([value['recovery']] if value.get('recovery') else [])]
    return '\n'.join(lines)


def render(value, command: str, *, failed: bool = False) -> str:
    """Render readable results without interpreting source text as terminal markup."""
    if isinstance(value, str):
        text = ('Error: ' if failed else '') + value
    elif command == 'init' and isinstance(value, dict):
        text = _init_text(value, failed)
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
    return printable(text)


def printable(text: str) -> str:
    """No control characters from page or source text reach the terminal."""
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


# Why a daily round started no page, in words (the record keeps the code).
NO_PAGE = {'nothing_unfinished': 'every page is written', 'nothing_new': 'nothing new since the last run',
           'no_page_fits_budget': 'no page fit what was left of the day\'s calls'}


def _tokens(*usages) -> str:
    total = {}
    for usage in usages:
        for key in ('input_tokens', 'output_tokens'):
            if isinstance((usage or {}).get(key), (int, float)):
                total[key] = total.get(key, 0) + usage[key]
    if not total:
        return ''
    from .rem_look import compact
    return f"{compact(total.get('input_tokens', 0))} in · {compact(total.get('output_tokens', 0))} out"


def _archive_line(archive) -> str:
    if not isinstance(archive, dict) or 'target' not in archive:
        return ''
    have = archive.get('saved', 0) + archive.get('reused', 0)
    return f"{have:,} of {archive['target']:,} mail bodies saved · {archive.get('phase', 'unknown')}"


def _store_lines(store, said, spell) -> list:
    """The index the table view reads (#2067), in status's layout: its size, or ✗ and what rebuilds it."""
    from . import rem_look
    if not isinstance(store, dict):
        return []
    if store.get('skipped'):
        return [rem_look.section('Index', style.warn(rem_look.BROKEN) + ' ' + said(f"not updated: {store['skipped']}")),
                rem_look.follow(style.command(spell(['sync'])))]
    rows = store.get('rows') or {}
    return [rem_look.section('Index', said(f"{rows.get('people', 0):,} people · {rows.get('messages', 0):,} messages"))]


def _pages_line(pages: list, left) -> str:
    counts = {}
    for row in pages:
        counts[row.get('outcome')] = counts.get(row.get('outcome'), 0) + 1
    words = [f"{counts.pop('accepted', 0)} updated"]
    words += [f"{number} {name.replace('_', ' ')}" for name, number in counts.items()]
    return " · ".join(words) + (f" · {left} left" if left is not None else "")


def sync_summary(value, spell=lambda arguments: 'co rem ' + ' '.join(arguments)):
    """What `co rem sync` ends on (#2044): a few lines, not the run record.

    It ended in a ~200-line dump: page paths as capitalised keys, the model's
    report cut mid-sentence, "Seconds: Unknown". Each page's outcome is said as
    it finishes; this is the total and where the full record is, in status's
    layout (1.9.0a9): a label in the margin, the value at one column, a refusal
    marked ✗ under the material it refused. `spell` writes a command as this
    user types it. Returns None for a result of another shape (a dry run, a
    slot not due), which `render` prints.
    """
    if not isinstance(value, dict) or not isinstance(value.get('maintenance', value), dict):
        return None
    if 'maintenance' not in value and 'items' not in value:
        return None
    from . import rem_look
    from .rem_look import highlight

    def said(text):
        return highlight(printable(text), counts=True)
    batch = value.get('maintenance') if 'maintenance' in value else value
    run = value.get('run') or {}
    changed = len(batch.get('changed') or [])
    material = f"{batch.get('items', 0)} items · {changed} page{'' if changed == 1 else 's'} changed"
    if batch.get('outcome') not in ('completed', None):
        material += f" · {str(batch.get('outcome')).replace('_', ' ')}"
    lines = [rem_look.section('New material', said(material))]
    lines += [rem_look.row('Refused', said(f"{row.get('record')}: {(row.get('errors') or ['rejected'])[0]}"[:160]),
                           style.warn(rem_look.BROKEN))
              for row in batch.get('refusals') or [] if isinstance(row, dict)]
    if 'maintenance' in value:
        investigation = value.get('investigation')
        if investigation:
            pages = _pages_line(investigation.get('pages') or [], investigation.get('left'))
        elif value.get('outcome') == 'budget_exhausted':
            pages = "none started; today's calls are spent"
        else:
            why = value.get('reason') or run.get('reason') or ''
            pages = f"none started; {NO_PAGE.get(why, why or 'see the log')}"
        lines.append(rem_look.section('Pages', said(pages)))
    archive = _archive_line(batch.get('mail_archive'))
    if archive:
        lines.append(rem_look.section('Mail archive', said(archive) + ' ' + style.muted(rem_look.RESUMES)))
    lines += _store_lines(batch.get('store'), said, spell)
    tokens = _tokens(batch.get('usage'), run.get('usage'))
    if tokens:
        lines.append(rem_look.section('Tokens', said(tokens)))
    record = run.get('id') or batch.get('id')
    if record:
        lines.append(rem_look.section('Full record', style.command(spell(['logs', record]))))
    outcome = str(value.get('outcome') or batch.get('outcome') or 'unknown').replace('_', ' ')
    title = style.heading('co rem sync') + (' — ' + style.error('needs attention')
                                            if value.get('outcome') in ('partial', 'failed') else
                                            ' · ' + highlight(outcome))
    return "\n".join([title, "", *lines, ""])


# What a check is called on doctor's page, where its JSON name is too long for the column.
DOCTOR_NAMES = {'spreadsheet support (co rem extra)': 'spreadsheet support'}


def doctor_board(checks: list) -> str:
    """`co rem doctor` as one check a line: ✓ or ✗, the check, what is true, and a fix under a failure.

    It printed `ok  co CLI: /Users/…` and `NO  schedule: not installed -> co rem
    start`: a fix at the end of a line that an 80-column terminal had already
    wrapped. Now the title counts what needs fixing and each fix is on the line
    under its check, where the eye already is (1.9.0a9).
    """
    from pathlib import Path

    from . import rem_look
    from .rem_look import highlight
    home = str(Path.home())
    names = [DOCTOR_NAMES.get(row['check'], row['check']) for row in checks]
    width = min(26, 4 + max((len(name) for name in names), default=0) + 2)
    failed = [row for row in checks if not row['ok']]
    verdict = (style.ok('every check passes') if not failed else
               style.warn(f"{len(failed)} of {len(checks)} checks need a fix"))
    lines = [style.heading('co rem doctor') + ' · ' + verdict, '']
    for name, row in zip(names, checks):
        mark = style.ok(rem_look.FINE) if row['ok'] else style.warn(rem_look.BROKEN)
        detail = printable(str(row['detail'])).replace(home, '~')
        lines.append(f"  {mark} {name}" + ' ' * max(1, width - 4 - len(name)) + highlight(detail))
        if not row['ok'] and row.get('fix'):
            lines.append(' ' * width + style.muted(rem_look.FIX) + ' ' + style.command(row['fix']))
    return '\n'.join([*lines, ''])
