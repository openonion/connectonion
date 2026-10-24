import base64,json
from unittest.mock import patch, MagicMock
import requests
import typer
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
@pytest.fixture
def login_service():
    response=MagicMock()
    response.json.side_effect=[{'code':'a'*43,'public_key':'0x'+'b'*64,'expires_in':599},{'code':'c'*43,'public_key':'0x'+'b'*64,'expires_in':599}]
    with patch('connectonion.cli.commands.project_cmd_lib.load_api_key',return_value='private-cli-token') as auth, \
         patch('requests.post',return_value=response) as post:
        yield response,post,auth

def test_no_browser_prints_only_a_one_time_link(capsys,login_service):
    with patch('webbrowser.open') as opened: handle_email_open(no_browser=True)
    opened.assert_not_called()
    output=capsys.readouterr()
    assert output.out.strip() == 'https://mail.openonion.ai/connect#code='+'a'*43+'&account=0x'+'b'*64
    assert 'private-cli-token' not in output.out+output.err
    assert '9m 59s' in output.err and 'Next: co email inbox' in output.err
    _,post,auth=login_service
    auth.assert_called_once()
    assert post.call_args.args[0].endswith('/api/v1/auth/mail-link')
    assert post.call_args.kwargs['headers']['Authorization']=='Bearer private-cli-token'

def test_open_launches_exact_link_in_browser(capsys,login_service):
    with patch('webbrowser.open',return_value=True) as opened: handle_email_open()
    output=capsys.readouterr()
    assert opened.call_args.args[0]=='https://mail.openonion.ai/connect#code='+'a'*43+'&account=0x'+'b'*64
    assert output.out.strip()=='https://mail.openonion.ai/connect#code='+'c'*43+'&account=0x'+'b'*64
    assert opened.call_args.args[0]!=output.out.strip()
    assert login_service[1].call_count==2

def test_browser_unavailable_keeps_copyable_link(capsys,login_service):
    with patch('webbrowser.open',return_value=False): handle_email_open()
    output=capsys.readouterr()
    assert output.out.startswith('https://mail.openonion.ai/connect#code=')
    assert 'Open the link above' in output.err

@pytest.mark.parametrize('body',[[], {'code':'x'}, {'code':'a'*43,'public_key':'bad'}, {'code':'https://attacker.example','public_key':'0x'+'b'*64}])
def test_bad_service_response_never_launches_a_browser(body,login_service):
    login_service[0].json.side_effect=None
    login_service[0].json.return_value=body
    with patch('webbrowser.open') as opened,pytest.raises(typer.Exit): handle_email_open()
    opened.assert_not_called()

def test_missing_login_has_recovery_and_does_not_call_service(capsys):
    with patch('connectonion.cli.commands.project_cmd_lib.load_api_key',return_value=None),patch('requests.post') as post,pytest.raises(typer.Exit):
        handle_email_open(no_browser=True)
    post.assert_not_called()
    assert 'Next: co auth login' in capsys.readouterr().err

@pytest.mark.parametrize('status',[401,500])
def test_http_failure_is_actionable_and_does_not_expose_server_details(status,capsys,login_service):
    response=MagicMock(status_code=status)
    login_service[0].raise_for_status.side_effect=requests.HTTPError('private upstream data',response=response)
    with pytest.raises(typer.Exit):handle_email_open(no_browser=True)
    output=capsys.readouterr()
    assert not output.out and 'private upstream data' not in output.err
    assert ('co auth login' if status==401 else 'co email open --no-browser') in output.err


def test_no_browser_only_creates_one_unused_ticket(capsys,login_service):
    with patch('webbrowser.open') as opened:handle_email_open(no_browser=True)
    assert login_service[1].call_count==1
    opened.assert_not_called()
    assert '#code='+'a'*43 in capsys.readouterr().out


def test_qr_is_phone_only_and_encodes_the_printed_link(capsys,login_service):
    with patch('webbrowser.open') as opened,patch('connectonion.cli.commands.email_web._phone_qr',return_value='SCANNABLE\n') as render:
        handle_email_open(qr=True)
    captured=capsys.readouterr()
    opened.assert_not_called()
    assert login_service[1].call_count==1
    render.assert_called_once_with(captured.out.strip())
    assert 'SCANNABLE' in captured.err and 'private-cli-token' not in captured.err


def test_duplicate_desktop_phone_ticket_is_rejected_before_opening(capsys,login_service):
    response=login_service[0];response.json.side_effect=None
    response.json.return_value={'code':'a'*43,'public_key':'0x'+'b'*64,'expires_in':599}
    with patch('webbrowser.open') as opened,pytest.raises(typer.Exit):handle_email_open()
    opened.assert_not_called()
    assert not capsys.readouterr().out
