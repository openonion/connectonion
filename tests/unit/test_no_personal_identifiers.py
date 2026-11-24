"""Keep personal identifiers out of fixtures and packaged examples (#2801)."""

from pathlib import Path


def test_no_personal_identifiers():
    root = Path(__file__).resolve().parents[2]
    forbidden = (b"aaronplus1996", b"xietianle", b"aaron xie", b"ody zhou")
    violations = []
    for area in ("tests", "docs", "connectonion"):
        for path in sorted((root / area).rglob("*")):
            if not path.is_file() or path == Path(__file__).resolve() or "__pycache__" in path.parts:
                continue
            content = path.read_bytes()
            if b"\0" in content:  # Binary assets are not text fixtures.
                continue
            for number, line in enumerate(content.lower().splitlines(), 1):
                for identifier in forbidden:
                    if identifier in line:
                        violations.append(f"{path.relative_to(root)}:{number}: {identifier.decode()}")
    assert not violations, "Personal identifiers found:\n" + "\n".join(violations)
