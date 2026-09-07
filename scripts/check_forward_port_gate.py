"""Block newer releases while a stable patch is missing from active lines."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any


STABLE_PATCH = re.compile(r"^\d+\.\d+\.[1-9]\d*$")


def release_needs_clear_forward_ports(version: str) -> bool:
    """Patch publication may proceed; every newer channel requires a clear ledger."""

    return STABLE_PATCH.fullmatch(version) is None


def open_forward_port_issues(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("GitHub issue payload must be a list")
    return [issue for issue in payload if isinstance(issue, dict)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--issues-json", required=True)
    args = parser.parse_args()

    if not release_needs_clear_forward_ports(args.version):
        print(f"{args.version} is a stable patch; forward integration follows publication.")
        return 0

    issues = open_forward_port_issues(json.loads(args.issues_json))
    if not issues:
        print(f"{args.version} has no open stable-patch forward-port blockers.")
        return 0

    lines = [
        f"#{issue.get('number')}: {issue.get('title')} ({issue.get('url')})"
        for issue in issues
    ]
    raise SystemExit(
        "Refusing to publish a newer release while stable patch fixes are missing:\n"
        + "\n".join(lines)
    )


if __name__ == "__main__":
    raise SystemExit(main())
