"""Two module headers name an API path the code has not called for versions.

    useful_tools/send_email.py
      header:  POST /api/email
      code:    POST /api/v1/email/send

    useful_tools/get_emails.py
      header:  /api/email, /api/email/{id}/read
      code:    /api/v1/email/received, /api/v1/email/s/mark-read,
               /api/v1/email/s/mark-unread

This is not hypothetical harm. Auditing the email path, I read the header, probed
`POST /api/email` against production, got `404 {"detail":"Not Found"}` on every
call, and briefly concluded `co email send` might be dead. It is not — the code
posts to `/api/v1/email/send`, which answers. The header cost a wrong conclusion
about a shipping feature.

test_every_header_names_something_real.py checks that the *symbols* a header names
exist. A URL is the other half of what these headers promise, and nothing looked
at it.

The rule has to tolerate two things, or it flags four correct headers — which is
how a guard becomes noise:

  * placeholder names differ. connect.py says `/api/agents/{addr}` where the code
    writes `{agent_address}`; deploy_commands.py says `{id}` for
    `{deployment_id}`. Same endpoint, and the header is the more readable name.
  * a header may name a prefix. sub_commands.py says `/api/agents/` and
    email_commands.py says `/api/v1/email/`, standing for the family below them.

So: normalise every `{...}` to `{}`, and accept a header path that any code path
starts with. What is left is a header naming an endpoint the module does not call.
"""

import pathlib
import re

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2] / "connectonion"
API_PATH = re.compile(r"/api/[A-Za-z0-9_/{}.-]+")
PLACEHOLDER = re.compile(r"\{[^}]*\}")


def _normalise(path: str) -> str:
    return PLACEHOLDER.sub("{}", path.rstrip(".,)"))


def _header_and_body(text: str):
    """A module's leading docstring and everything after it."""
    if not text.startswith('"""'):
        return "", text
    end = text.find('"""', 3)
    return text[:end], text[end:]


def _modules_naming_an_api_path():
    for path in sorted(ROOT.rglob("*.py")):
        header, body = _header_and_body(path.read_text(encoding="utf-8", errors="replace"))
        named = {_normalise(p) for p in API_PATH.findall(header)}
        if named:
            yield path, named, {_normalise(p) for p in API_PATH.findall(body)}


MODULES = list(_modules_naming_an_api_path())


class TestEveryNamedEndpointIsOneTheModuleCalls:

    def test_some_modules_name_an_endpoint(self):
        """A rename would otherwise empty the parametrize and pass silently."""
        assert len(MODULES) >= 6

    @pytest.mark.parametrize("path,named,in_code",
                             MODULES, ids=[p.name for p, _, _ in MODULES])
    def test_the_header_matches_the_code(self, path, named, in_code):
        unmatched = sorted(
            candidate for candidate in named
            if not any(actual.startswith(candidate) for actual in in_code)
        )

        assert not unmatched, (
            f"{path.relative_to(ROOT.parent)}'s header names "
            f"{unmatched}, which this module does not call. It calls "
            f"{sorted(in_code)}."
        )


class TestThePrefixAndPlaceholderCasesStayAccepted:
    """The four correct headers this rule must not flag."""

    @pytest.mark.parametrize("named,in_code", [
        ("/api/agents/{}", "/api/agents/{}"),          # {addr} vs {agent_address}
        ("/api/agents/", "/api/agents/{}/profile"),    # a family prefix
        ("/api/v1/email/", "/api/v1/email/check-name"),
        ("/api/v1/deploy/{}/status", "/api/v1/deploy/{}/status"),
    ])
    def test_they_match(self, named, in_code):
        assert in_code.startswith(named)

    def test_a_genuinely_different_path_does_not_match(self):
        """The two this file was written for."""
        assert not "/api/v1/email/send".startswith("/api/email")
        assert not "/api/v1/email/received".startswith("/api/email")
