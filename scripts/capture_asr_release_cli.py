"""Capture real, account-free ASR help/configuration/recovery output."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from capture_186a2_release_cli import page
from capture_190a2_release_cli import shoot

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/releases/assets/v1.9.3rc23'


def main():
    with tempfile.TemporaryDirectory(prefix='co-asr-capture-') as temporary:
        env = {'PATH': os.defpath, 'HOME': temporary, 'TMPDIR': temporary,
               'PYTHONPATH': str(ROOT), 'NO_COLOR': '1', 'COLUMNS': '96'}
        blocks = []
        for arguments, expected in [(['asr', '--help'], 0),
                                    (['env', 'set', 'ASR_PROVIDER', 'connectonion'], 0),
                                    (['asr', 'missing.wav', '--json'], 1)]:
            result = subprocess.run([sys.executable, '-m', 'connectonion.cli.main', *arguments],
                                    cwd=temporary, env=env, text=True, capture_output=True,
                                    timeout=30)
            assert result.returncode == expected, (arguments, result.returncode)
            output = (result.stderr + result.stdout).replace(temporary, '~')
            blocks.append(('co ' + ' '.join(arguments), output))
        shoot(page('', blocks[:1]), OUT/'asr-help.png')
        shoot(page('', blocks[1:]), OUT/'asr-config-recovery.png')


if __name__ == '__main__':
    main()
