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
    assert result.output.splitlines()[:2] == SETTINGS['domains']
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
    assert call.kwargs['json'] == {'local_part': 'iron.share', 'domain': 'steadmail.com',
                                   'make_default': False}
    assert '--from iron.share@steadmail.com' in result.output


def test_buy_says_the_default_sender_did_not_move(cloud):
    """openonion/oo-api#288: a purchase used to take over the default silently."""
    cloud[1].return_value = response({
        'address': 'iron.share@steadmail.com', 'message': 'Claimed iron.share@steadmail.com',
        'default_address': '0x1234567890@mail.openonion.ai', 'default_changed': False,
    })
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '-d', 'steadmail.com', '--buy'])
    assert result.exit_code == 0, result.output
    assert 'Default sender is still 0x1234567890@mail.openonion.ai' in result.output
    assert 'Make the new one default: co email default iron.share@steadmail.com' in result.output


def test_buy_with_default_asks_for_it_and_says_it_moved(cloud):
    cloud[1].return_value = response({
        'address': 'iron.share@steadmail.com', 'message': 'Claimed iron.share@steadmail.com',
        'default_address': 'iron.share@steadmail.com', 'default_changed': True,
    })
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '-d', 'steadmail.com', '--buy', '--default'])
    assert result.exit_code == 0, result.output
    assert cloud[1].call_args.kwargs['json']['make_default'] is True
    assert 'Default sender is now iron.share@steadmail.com' in result.output
    assert 'still' not in result.output


def test_buy_against_an_older_backend_points_at_the_listing(cloud):
    """Before #288 the server did not report the default and may have moved it."""
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '-d', 'steadmail.com', '--buy'])
    assert result.exit_code == 0, result.output
    assert 'Check the default sender: co email addresses' in result.output


def test_preview_says_buying_keeps_the_default(cloud):
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '-d', 'steadmail.com', '--default'])
    assert result.exit_code == 0, result.output
    assert 'co email setup iron.share --domain steadmail.com --buy --default' in result.output
    assert 'keeps your current default sender' in result.output
    cloud[1].assert_not_called()


def test_the_derived_address_can_be_chosen_as_default_again(cloud):
    cloud[1].return_value = response({'address': '0x1234567890@mail.openonion.ai', 'is_default': True})
    result = CliRunner().invoke(app, ['email', 'default', '0x1234567890@mail.openonion.ai'])
    assert result.exit_code == 0, result.output
    assert cloud[1].call_args.args[0].endswith('/email/addresses/default')
    assert cloud[1].call_args.kwargs['json'] == {'address': '0x1234567890@mail.openonion.ai'}
    assert '0x1234567890@mail.openonion.ai is now the default sender' in result.output


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


@pytest.mark.parametrize('command', [['domains'], ['setup', 'new.alias', '--buy']])
def test_signed_out_commands_do_not_contact_the_cloud(cloud, command):
    with patch.object(email_commands, 'load_api_key', return_value=None):
        result = CliRunner().invoke(app, ['email', *command])
    assert result.exit_code == 1
    cloud[0].assert_not_called()
    cloud[1].assert_not_called()


@pytest.mark.parametrize('command', [['domains'], ['setup', 'new.alias', '--buy']])
def test_settings_failure_stops_before_purchase(cloud, command):
    cloud[0].return_value = response({'detail': 'Account access denied'}, 403)
    result = CliRunner().invoke(app, ['email', *command])
    assert result.exit_code == 1
    assert 'Account access denied' in result.output
    cloud[1].assert_not_called()


def test_a_reserved_domain_is_not_sold_until_the_cloud_enables_it(cloud):
    cloud[0].return_value = response({**SETTINGS, 'domains': ['mail.openonion.ai']})
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '-d', 'steadmail.com', '--buy'])
    assert result.exit_code == 1
    assert 'co email domains' in result.output
    cloud[1].assert_not_called()


def test_an_owned_address_is_recognized_when_its_domain_closes_to_new_purchases(cloud):
    cloud[0].return_value = response({
        **SETTINGS,
        'domains': ['mail.openonion.ai'],
        'addresses': [*SETTINGS['addresses'], {'address': 'iron.share@steadmail.com'}],
    })
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '-d', 'steadmail.com', '--buy'])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == 'Already owned: iron.share@steadmail.com'
    cloud[1].assert_not_called()
