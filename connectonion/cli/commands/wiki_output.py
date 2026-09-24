"""Plain, pipe-friendly Wiki output. JSON serialization stays in the command layer."""

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
    else:
        title = 'Wiki ' + ('status' if command == 'wiki' else command.replace('-', ' '))
        if command in ('status', 'wiki') and isinstance(value, dict):
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
            text += '\n\nMap initialized. Investigation has not started. Choose a page with unfinished.'
    return ''.join(char for char in text if char in '\n\t' or (ord(char) >= 32 and not 127 <= ord(char) <= 159))


def guide(next_command) -> str:
    """One workflow shared by the overview and --help, with root-aware commands."""
    paragraphs = [
        "Wiki — map first, investigate next",
        "First run: Build the map with " + next_command(["init"]) +
        ". This creates People, Organizations, Projects and Skills from templates and source metadata. "
        "It does not investigate or start background work.",
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
