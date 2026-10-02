"""Local GitHub watch configuration; the provider owns all GitHub reads."""
import json

from ...inbox.github import configure, read_config
from ...inbox.store import default_home
from .command_tips import print_tip


def handle_watch(repo: str, **options) -> None:
    config = configure(repo, **options)
    print(json.dumps(config))
    print_tip('Next: co github watches' if options.get('remove') else 'Next: co github check')


def handle_watches() -> None:
    config = read_config()
    checkpoint = default_home('github') / 'checkpoint.json'
    config['checkpoints'] = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    print(json.dumps(config))
