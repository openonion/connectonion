"""Who decides how open a host is.

One place: `.co/host.yaml`, a file the operator owns and can read back.

The docs used to promise a second channel — `CONNECTONION_ENV=development`
would set trust to "open" — and shipped two functions implementing it that
nothing ever called. Trust stayed "careful" whatever the variable said.

Wiring it up as documented was the obvious fix and is the wrong one. It makes
an environment variable able to *widen* a host to everyone, and
`CONNECTONION_ENV=development` is exactly the kind of thing that sits in a
shell profile for months. The person running `co host` on their laptop would
not be reading the docs at that moment.

So the promise is gone and these tests pin its absence. They are green today —
what they defend against is someone implementing the removed promise later
because the docs used to describe it.
"""

import pytest

from connectonion.network.host.config import load_host_config


ENVS = ['development', 'production', 'staging', 'test', 'nonsense', '']


@pytest.mark.parametrize("env", ENVS)
def test_the_environment_does_not_decide_trust(env, tmp_path, monkeypatch):
    monkeypatch.setenv('CONNECTONION_ENV', env)
    co_dir = tmp_path / '.co'
    co_dir.mkdir()
    (co_dir / 'host.yaml').write_text("name: a\nentrypoint: agent.py\ntrust: careful\n")

    config = load_host_config(co_dir)

    assert config.get('trust') == 'careful', (
        f"CONNECTONION_ENV={env!r} changed trust; host.yaml is the only place "
        "that may decide how open a host is"
    )


def test_host_yaml_is_read_back_as_written(tmp_path, monkeypatch):
    """The operator's file, not a default that happens to agree with it."""
    monkeypatch.setenv('CONNECTONION_ENV', 'development')
    co_dir = tmp_path / '.co'
    co_dir.mkdir()
    (co_dir / 'host.yaml').write_text("name: a\nentrypoint: agent.py\ntrust: strict\n")

    assert load_host_config(co_dir).get('trust') == 'strict'


def test_the_removed_helpers_are_still_removed():
    """A function whose only purpose is a mechanism we decided against is how
    that mechanism comes back."""
    import importlib
    trust_pkg = importlib.import_module('connectonion.network.trust')
    server = importlib.import_module('connectonion.network.host.server')

    assert not hasattr(trust_pkg, 'get_default_trust_level')
    assert not hasattr(server, 'get_default_trust')
