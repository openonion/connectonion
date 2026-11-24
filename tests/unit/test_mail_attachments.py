"""Local files, mailbox metadata and CLI attachment contracts."""
import base64
import hashlib
from importlib import import_module
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner
from connectonion.cli.main import app
from connectonion.useful_tools import email_attachments as files


def fake_response(data=b'abc', body=None):
    response=Mock();response.content=data;response.json.return_value=body
    return response


def test_encode_files_preserves_bytes_and_mime_type(tmp_path):
    source=tmp_path/'采购单.pdf';source.write_bytes(b'\x00\xffPDF')
    attachment=files.encode_attachments([str(source)])[0]
    assert attachment['filename']=='采购单.pdf' and attachment['content_type']=='application/pdf'
    assert base64.b64decode(attachment['content'])==source.read_bytes()


def test_send_uses_explicit_attachment_endpoint_and_retains_budget(monkeypatch,tmp_path):
    mod=import_module('connectonion.useful_tools.send_email')
    monkeypatch.setattr(mod,'require_ambient_api_key',lambda:'test-only')
    monkeypatch.setenv('AGENT_EMAIL','orders@example.com')
    post=Mock(return_value=Mock(status_code=200,json=lambda:{'message_id':'sent'}))
    monkeypatch.setattr(mod.requests,'post',post)
    source=tmp_path/'po.pdf';source.write_bytes(b'PDF')
    result=mod.send_email('buyer@example.com','PO','Attached',attachments=[str(source)],max_cost_usd='.003')
    assert result['success']
    assert post.call_args.args[0].endswith('/send-with-attachments')
    assert post.call_args.kwargs['json']['attachments'][0]['content']=='UERG'
    assert post.call_args.kwargs['json']['max_cost_usd']=='0.00300000'


def test_download_checks_hash_and_never_overwrites_even_symlinks(monkeypatch,tmp_path):
    data=b'PDF'
    metadata={'id':9,'filename':'../../po.pdf','size':len(data),'content_type':'application/pdf','sha256':hashlib.sha256(data).hexdigest()}
    monkeypatch.setattr(files,'get_email_attachments',lambda *args:[metadata])
    monkeypatch.setattr(files,'_get',lambda path:fake_response(data))
    saved=files.download_email_attachment('1',9,str(tmp_path))
    assert (tmp_path/'po.pdf').read_bytes()==data
    assert saved['sha256']==metadata['sha256']
    with pytest.raises(FileExistsError): files.download_email_attachment('1',9,str(tmp_path))
    (tmp_path/'po.pdf').unlink()
    (tmp_path/'po.pdf').symlink_to(tmp_path/'must-not-create')
    with pytest.raises(FileExistsError): files.download_email_attachment('1',9,str(tmp_path))
    assert not (tmp_path/'must-not-create').exists()


def test_integrity_failure_does_not_leave_a_download(monkeypatch,tmp_path):
    monkeypatch.setattr(files,'get_email_attachments',lambda *args:[{'id':9,'filename':'po.pdf','size':3,'sha256':'wrong'}])
    monkeypatch.setattr(files,'_get',lambda path:fake_response())
    with pytest.raises(ValueError,match='verification failed'): files.download_email_attachment('1',9,str(tmp_path))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('email_id',['../1','0',True,'-2'])
def test_invalid_email_id_cannot_escape_url(email_id):
    with pytest.raises(ValueError): files._mail_path(email_id)


def test_get_email_retains_attachment_metadata(monkeypatch):
    mod=import_module('connectonion.useful_tools.get_emails')
    monkeypatch.setattr(mod,'_read_message',lambda *args:{'id':1,'attachments':[{'id':9}]})
    assert mod.get_email(1)['attachments']==[{'id':9}]


def test_cli_repeat_attach_and_sent_download(monkeypatch):
    commands=import_module('connectonion.cli.commands.email_commands')
    send=Mock();download=Mock()
    monkeypatch.setattr(commands,'handle_email_send',send)
    monkeypatch.setattr(commands,'handle_email_download',download)
    runner=CliRunner()
    response=runner.invoke(app,['email','send','buyer@example.com','PO','Attached','--attach','a.pdf','--attach','b.csv'])
    assert response.exit_code==0, response.output
    assert send.call_args.kwargs['attachments']==['a.pdf','b.csv']
    response=runner.invoke(app,['email','download','1','9','--to','./files','--sent'])
    assert response.exit_code==0,response.output
    download.assert_called_once_with('1','9','./files',True)


def test_pdf_reader_retains_original_and_reports_scans(monkeypatch,tmp_path):
    from connectonion.rem import attachments as text_reader
    target=tmp_path/'po.pdf';target.write_bytes(b'PDF')
    monkeypatch.setattr(files,'download_email_attachment',lambda *args:{'path':str(target),'filename':'po.pdf'})
    monkeypatch.setattr(text_reader,'extract_text',lambda *args,**kwargs:'PO 144748 Wine 6 cases')
    result=files.read_email_attachment('1',9,str(tmp_path))
    assert result['readable'] and '6 cases' in result['text'] and target.exists()
    monkeypatch.setattr(text_reader,'extract_text',lambda *args,**kwargs:'')
    result=files.read_email_attachment('1',9,str(tmp_path))
    assert not result['readable'] and 'OCR' in result['error']


def test_forward_includes_original_files_and_reply_can_attach_local_files(monkeypatch,tmp_path):
    from connectonion.cli.commands import email_workflows as flow
    original={'from':'a@example.com','subject':'PO','message':'Attached','attachments':[{'id':9}]}
    monkeypatch.setattr(flow,'_read',lambda *args:original)
    def download(email_id,attachment_id,output):
        path=__import__('pathlib').Path(output)/'po.pdf';path.parent.mkdir(parents=True)
        path.write_bytes(b'PDF')
        return {'path':str(path)}
    monkeypatch.setattr(files,'download_email_attachment',download)
    send=Mock();monkeypatch.setattr(flow,'handle_email_send',send)
    flow.handle_email_reply('1','Note',to='b@example.com')
    paths=send.call_args.kwargs['attachments']
    assert len(paths)==1 and paths[0].endswith('po.pdf')
    # Successful forwards clean up their temporary originals.
    assert not __import__('pathlib').Path(paths[0]).exists()
    flow.handle_email_reply('1','Reply',from_address='orders@example.com',attachments=['local.pdf'])
    assert send.call_args.kwargs['attachments']==['local.pdf']
