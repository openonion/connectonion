"""An account can discover domains and add another alias without replacing mail."""
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import email_commands

SETTINGS = {
    'addresses': [{'address': 'iron.share@mail.openonion.ai', 'is_default': True}],
    'domains': ['mail.openonion.ai', 'steadmail.com'],
    'prices': {'add': 9.9},
}


def response(data, status=200):
    return Mock(ok=status == 200, status_code=status, json=lambda: data,
                headers={'content-type': 'application/json'})


@pytest.fixture
def cloud():
    with patch.object(email_commands, 'load_api_key', return_value='test-token'), \
         patch.object(email_commands.requests, 'get', return_value=response(SETTINGS)) as get, \
         patch.object(email_commands.requests, 'post', return_value=response({
             'address': 'iron.share@steadmail.com', 'message': 'Claimed iron.share@steadmail.com',
         })) as post:
        yield get, post


def test_domains_come_from_the_cloud(cloud):
    result = CliRunner().invoke(app, ['email', 'domains'])
    assert result.exit_code == 0, result.output
    assert 'steadmail.com' in result.output.splitlines()
    assert '$9.90' in result.output
    cloud[1].assert_not_called()


def test_setup_shows_price_without_charging(cloud):
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '--domain', 'steadmail.com'])
    assert result.exit_code == 0, result.output
    assert '$9.90' in result.output and '--buy' in result.output
    cloud[1].assert_not_called()


def test_buy_adds_a_second_address_and_names_the_next_steps(cloud):
    result = CliRunner().invoke(app, ['email', 'setup', 'Iron.Share', '-d', 'Steadmail.com', '--buy'])
    assert result.exit_code == 0, result.output
    call = cloud[1].call_args
    assert call.args[0].endswith('/email/addresses')
    assert call.kwargs['json'] == {'local_part': 'iron.share', 'domain': 'steadmail.com'}
    assert 'Choose default: co email default iron.share@steadmail.com' in result.output
    assert '--from iron.share@steadmail.com' in result.output


def test_an_owned_address_is_not_purchased_again(cloud):
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '--buy'])
    assert result.exit_code == 0 and 'Already owned' in result.output
    cloud[1].assert_not_called()


def test_unknown_domains_cannot_be_purchased(cloud):
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '-d', 'mail.com', '--buy'])
    assert result.exit_code == 1
    assert 'co email domains' in result.output
    cloud[1].assert_not_called()


def test_taken_address_explains_other_domains_and_exits_nonzero(cloud):
    cloud[1].return_value = response({'detail': {'message': 'Taken; available on oakinbox.com'}}, 409)
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '-d', 'steadmail.com', '--buy'])
    assert result.exit_code == 1
    assert result.output.strip() == '✗ Taken; available on oakinbox.com'
