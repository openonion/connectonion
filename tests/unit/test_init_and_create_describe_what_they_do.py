"""`co init` and `co create` say they generate a keypair. Neither does.

Both module headers claim it:

    create.py:7   … uses address.generate() for Ed25519 keypair
    init.py:7     … uses address.generate() and address.save() for Ed25519 keypair

Neither file calls either function. Confirmed by running it — `co create
demo-agent --yes` leaves a `.co/` holding `host.yaml`, `docs`, `admins.txt` and
`logs`, and no `keys/`. The project reports the machine's address.

The generation those lines describe happens inside `ensure_global_config()`,
for `~/.co` — the *machine's* identity, not the project's. So the sentence
describes something real, in the wrong place.

It cost something. #642 states as fact that `co create` writes a project-local
keypair and scoped its problem to legacy `co init` projects on that basis. It is
not a legacy problem; every project shares the machine identity, and I read that
issue's premise as given for several rounds before measuring it.

These headers are read as a map of the file. One naming a function the file does
not call is worse than no header, so this test compares them against the code
rather than trusting either.
"""

import ast
import pathlib

import pytest


COMMANDS = pathlib.Path(__file__).resolve().parents[2] / "connectonion" / "cli" / "commands"


def _called_names(path: pathlib.Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            names.add(getattr(fn, "attr", None) or getattr(fn, "id", None))
    return names


def _header(path: pathlib.Path) -> str:
    return ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""


@pytest.mark.parametrize("filename", ["create.py", "init.py"])
class TestTheHeaderMatchesTheCode:

    def test_it_does_not_claim_to_generate_a_keypair(self, filename):
        path = COMMANDS / filename
        header = _header(path)

        for claim in ("address.generate()", "address.save()"):
            if claim in header:
                assert claim.split(".")[1].rstrip("()") in _called_names(path), (
                    f"{filename}'s header says it {claim} and the file never calls it"
                )

    def test_it_still_says_where_the_identity_does_come_from(self, filename):
        """Removing the claim must not remove the answer — the reader still
        needs to know a keypair is involved somewhere."""
        header = _header(COMMANDS / filename)

        assert "ensure_global_config()" in header


class TestWhatTheCommandsActuallyProduce:
    """The fact the headers got wrong, pinned so it is checkable."""

    def test_neither_writes_a_project_key(self):
        for filename in ("create.py", "init.py"):
            called = _called_names(COMMANDS / filename)
            assert "save" not in called or "generate" not in called, (
                f"{filename} now writes a project key — the header should say so"
            )
