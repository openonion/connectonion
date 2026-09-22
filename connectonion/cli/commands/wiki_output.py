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
    """Commands that require a page are discovered through an actual listing."""
    steps = [
        ('Build the map (no model)', ['init']),
        ('Choose a page to investigate (no model until you select one)', ['investigate']),
        ('Browse the map in your browser', ['open']),
        ('Preview pending updates (no model)', ['sync', '--dry-run']),
        ('Update from pending material', ['sync']),
        ('Inspect results and failures', ['logs']),
        ('Discover all commands and options', ['--help']),
    ]
    lines = ['Wiki — map first, investigate next', '']
    for description, arguments in steps:
        lines.extend([description + ':', '  ' + next_command(arguments)])
    lines.extend(['', 'init builds People, Organizations, Projects and Skills; it does not start investigation.',
                  'investigate with no argument lists your pages and prints a concrete next command.',
                  'investigate and sync may use the configured model. start explicitly enables background work.',
                  'Tip: put --root and --json before the subcommand; add --help after any command.', ''])
    return '\n'.join(lines)
