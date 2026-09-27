"""Capture 1.8.9b17's zero-balance tip from `co status` itself.

    python scripts/capture_189b17_release_cli.py

`co status` runs against a stand-in account answer with a zero balance: no
real account, key or network is used. Everything else on screen is the
command's own output from this checkout.
"""

import io
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from rich.console import Console

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from capture_186a2_release_cli import page, shoot

OUT = ROOT / "docs/releases/assets/v1.8.9b17"


def zero_balance_status() -> str:
    from connectonion.cli.commands import status_commands
    user = {"balance_usd": 0.0, "total_cost_usd": 5.0, "credits_usd": 5.0,
            "email": {"address": "demo@mail.openonion.ai"}}
    output = io.StringIO()
    with tempfile.TemporaryDirectory(prefix="co-189b17-capture-") as temporary:
        home = Path(temporary)
        (home / ".co" / "keys").mkdir(parents=True)
        (home / ".co" / "keys" / "agent.key").write_text("demo")
        cwd = os.getcwd()
        os.chdir(home)
        try:
            with patch.dict(os.environ, {"OPENONION_API_KEY": "demo", "HOME": str(home)}), \
                    patch("connectonion.address.load", return_value={"address": "0x0000demo"}), \
                    patch("connectonion.address.sign", return_value=b"\0" * 64), \
                    patch.object(status_commands.requests, "post",
                                 return_value=Mock(status_code=200, json=lambda: {"user": user})), \
                    patch.object(status_commands.requests, "get",
                                 return_value=Mock(status_code=200, json=lambda: {"deployments": []})), \
                    patch.object(Path, "home", return_value=home), \
                    patch.object(status_commands, "console",
                                 Console(file=output, force_terminal=False, color_system=None, width=100)):
                status_commands.handle_status()
        finally:
            os.chdir(cwd)
    text = output.getvalue()
    # The account panel and the tip; the credential table above them is not what changed.
    return text[text.index("No credits left") - 4:].split("\n\n")[0].rstrip()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    shoot(page("", [("co status   # at a zero balance", zero_balance_status())]), OUT / "status-zero-balance.png")
    print(f"wrote 1 capture into {OUT}")
