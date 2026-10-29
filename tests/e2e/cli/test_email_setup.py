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
    state = {'addresses': None}

    def get(url, params=None, **kwargs):
        if str(url).endswith('/email/check-name'):
            name = (params or {}).get('name', '')
            return response({'available': True, 'email': f'{name}@mail.openonion.ai', 'price': 9.9})
        if state['addresses'] is not None:
            return state['addresses']
        return response(SETTINGS)

    with patch.object(email_commands, 'load_api_key', return_value='test-token'), \
         patch.object(email_commands.requests, 'get', side_effect=get) as get_mock, \
         patch.object(email_commands.requests, 'post', return_value=response({
             'address': 'iron.share@steadmail.com', 'message': 'Claimed iron.share@steadmail.com',
         })) as post:
        get_mock.state = state
        yield get_mock, post


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


@pytest.mark.parametrize('command', [['domains'], ['setup', 'new.alias', '--buy']])
def test_signed_out_commands_do_not_contact_the_cloud(cloud, command):
    with patch.object(email_commands, 'load_api_key', return_value=None):
        result = CliRunner().invoke(app, ['email', *command])
    assert result.exit_code == 1
    cloud[0].assert_not_called()
    cloud[1].assert_not_called()


@pytest.mark.parametrize('command', [['domains'], ['setup', 'new.alias', '--buy']])
def test_settings_failure_stops_before_purchase(cloud, command):
    cloud[0].state['addresses'] = response({'detail': 'Account access denied'}, 403)
    result = CliRunner().invoke(app, ['email', *command])
    assert result.exit_code == 1
    assert 'Account access denied' in result.output
    cloud[1].assert_not_called()


def test_a_reserved_domain_is_not_sold_until_the_cloud_enables_it(cloud):
    cloud[0].state['addresses'] = response({**SETTINGS, 'domains': ['mail.openonion.ai']})
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '-d', 'steadmail.com', '--buy'])
    assert result.exit_code == 1
    assert 'co email domains' in result.output
    cloud[1].assert_not_called()


def test_an_owned_address_is_recognized_when_its_domain_closes_to_new_purchases(cloud):
    cloud[0].state['addresses'] = response({
        **SETTINGS,
        'domains': ['mail.openonion.ai'],
        'addresses': [*SETTINGS['addresses'], {'address': 'iron.share@steadmail.com'}],
    })
    result = CliRunner().invoke(app, ['email', 'setup', 'iron.share', '-d', 'steadmail.com', '--buy'])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == 'Already owned: iron.share@steadmail.com'
    cloud[1].assert_not_called()


def _names(cloud, answers):
    """Serve /email/addresses from the usual settings, and check-name from `answers`."""
    def get(url, params=None, **kwargs):
        if str(url).endswith('/email/check-name'):
            name = (params or {}).get('name', '')
            return response(answers(name))
        forced = getattr(get, 'addresses', None)
        return forced if forced is not None else response(SETTINGS)
    cloud[0].side_effect = get
    return get


@pytest.mark.parametrize('alias,reason', [
    ('Bad_Alias!', 'Name can only contain letters, numbers, and single dots between them'),
    ('admin', 'This name is reserved'),
    ('0xAbCdEf1234', 'This name is reserved'),
])
def test_preview_does_not_offer_buy_for_a_name_the_server_refuses(cloud, alias, reason):
    seen = []

    def answers(name):
        seen.append(name)
        return {'available': False, 'email': f'{name}@steadmail.com', 'reason': reason}

    _names(cloud, answers)
    result = CliRunner().invoke(app, ['email', 'setup', alias, '--domain', 'steadmail.com'])
    assert result.exit_code == 1, result.output
    assert reason in result.output
    assert '--buy' not in result.output
    assert '$9.90' not in result.output
    assert seen == [alias.lower()]
    cloud[1].assert_not_called()


def test_buy_does_not_post_a_name_the_server_refuses(cloud):
    _names(cloud, lambda name: {'available': False, 'reason': 'This name is reserved'})
    result = CliRunner().invoke(app, ['email', 'setup', 'admin', '--domain', 'steadmail.com', '--buy'])
    assert result.exit_code == 1, result.output
    assert 'This name is reserved' in result.output
    assert '--buy' not in result.output
    cloud[1].assert_not_called()


def test_a_name_that_is_only_taken_still_shows_the_price(cloud):
    _names(cloud, lambda name: {'available': False, 'reason': 'Already taken'})
    result = CliRunner().invoke(app, ['email', 'setup', 'ops', '--domain', 'steadmail.com'])
    assert result.exit_code == 0, result.output
    assert '$9.90' in result.output and '--buy' in result.output
    cloud[1].assert_not_called()


def test_a_sellable_alias_still_shows_the_price(cloud):
    _names(cloud, lambda name: {'available': True, 'email': f'{name}@steadmail.com', 'price': 5})
    result = CliRunner().invoke(app, ['email', 'setup', 'ops', '--domain', 'steadmail.com'])
    assert result.exit_code == 0, result.output
    assert 'ops@steadmail.com: $9.90' in result.output
    assert '--buy' in result.output
    cloud[1].assert_not_called()


def test_a_rejected_name_check_is_the_whole_answer(cloud):
    def get(url, params=None, **kwargs):
        if str(url).endswith('/email/check-name'):
            return response(
                {'detail': {'message': 'Name can only contain letters, numbers, and single dots between them'}},
                400,
            )
        return response(SETTINGS)
    cloud[0].side_effect = get
    result = CliRunner().invoke(app, ['email', 'setup', 'bad_alias!', '--buy'])
    assert result.exit_code == 1, result.output
    assert 'Name can only contain letters, numbers, and single dots between them' in result.output
    assert '--buy' not in result.output
    cloud[1].assert_not_called()
