import base64,json
from unittest.mock import patch
import pytest
from connectonion.cli.commands.email_web import connection_code,handle_email_open
from connectonion import address
NOW=1792822000
CHALLENGE='ConnectOnion-Auth-OO-Mail-'+'a'*48+'-'+str(NOW)
@pytest.mark.parametrize('challenge',['x','ConnectOnion-Auth-other','ConnectOnion-Auth-OO-Mail-'+'a'*48+'-1'])
def test_only_mail_protocol_is_signed(challenge):
    with patch('connectonion.project.project_identity') as identity:
        with pytest.raises(ValueError,match='Invalid challenge'):connection_code(challenge,now=NOW)
        identity.assert_not_called()
@pytest.mark.parametrize('now',[NOW+121,NOW-6])
def test_expired_or_future_challenge_is_refused(now):
    with pytest.raises(ValueError,match='expired'):connection_code(CHALLENGE,now=now)
def test_connection_code_uses_selected_identity_and_verifies():
    identity=address.generate()
    with patch('connectonion.project.project_identity',return_value=identity),patch('connectonion.environment.load_environment'):
        code=connection_code(CHALLENGE,now=NOW)
    proof=json.loads(base64.urlsafe_b64decode(code+'='*(-len(code)%4)))
    assert proof['public_key']==identity['address'] and proof['message']==CHALLENGE
    assert address.verify(proof['public_key'],CHALLENGE.encode(),bytes.fromhex(proof['signature']))
    assert 'private' not in str(proof).lower()
def test_missing_identity_is_actionable():
    with patch('connectonion.project.project_identity',return_value=None),patch('connectonion.environment.load_environment'):
        with pytest.raises(ValueError,match='co init'):connection_code(CHALLENGE,now=NOW)
def test_no_browser_prints_url_without_side_effect(capsys):
    with patch('webbrowser.open') as opened:handle_email_open(no_browser=True)
    opened.assert_not_called()
    assert capsys.readouterr().out.strip() == 'https://mail.openonion.ai'
