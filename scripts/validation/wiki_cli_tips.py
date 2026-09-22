"""Check Wiki discovery using synthetic pages and text-only model replies.

Run from the checkout with PYTHONPATH=. No suggested command is executed.
"""
import argparse
import json
import shlex
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from typer.testing import CliRunner

from connectonion import llm_do
from connectonion.cli.main import app
from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='co/gemini-3.7-flash')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = []
    with tempfile.TemporaryDirectory(prefix='wiki-cli-tips-') as folder:
        root = Path(folder) / 'wiki with spaces'
        runner = CliRunner()
        def capture(command, goal):
            result = runner.invoke(app, ['wiki', '--root', str(root), *command])
            assert 'Next: ' in result.output, result.output
            cases.append({'command': shlex.join(['co', 'wiki', *command]), 'exit': result.exit_code,
                          'output': result.output, 'goal': goal,
                          'next': result.output.rsplit('Next: ', 1)[1].strip()})
        capture([], 'Build the initial map.')
        capture(['investigate'], 'Build a map because no pages exist yet.')
        prepare(root)
        Notebook(root).stub_person('people/ody-123.md', 'Ody', ['ody@example.org'], email='ody@example.org')
        for command, goal in [
            (['investigate'], 'Investigate the available person page.'),
            (['unfinished'], 'Investigate the unfinished page.'),
            (['list', 'people'], 'Read the listed person page.'),
            (['search', 'Ody'], 'Read the matching page.'),
            (['show', 'people/ody-123.md'], 'Return to the list of people.'),
            (['show', 'people/missing.md'], 'Find the actual person page path.'),
            (['investigate', 'Nobody'], 'Discover available pages without running a model.'),
            (['people'], 'List person page paths.'),
            (['status'], 'Inspect previous run results.'),
            (['logs'], 'Inspect the notebook status.'),
            (['config'], 'Inspect the notebook status.'),
            (['subscriptions'], 'Inspect the notebook status.'),
            (['usage'], 'Inspect the run logs.'),
            (['reflections'], 'Browse existing pages.'),
        ]:
            capture(command, goal)
    def judge(case):
        reply = llm_do(
            f'You just ran a shell command. Its full output was:\n\n{case["output"]}\n\n'
            f'Your goal: {case["goal"]} Reply with ONE shell command and nothing else.',
            model=args.model, max_tokens=2000,
        ).strip()
        case['reply'] = reply
        try:
            case['pass'] = shlex.split(reply) == shlex.split(case['next'])
        except ValueError:
            case['pass'] = False
        return case
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(judge, cases))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'model': args.model, 'cases': results}, indent=2) + '\n')
    print(f'{sum(row["pass"] for row in results)}/{len(results)} tip checks passed; {args.output}')
    return 0 if all(row['pass'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
