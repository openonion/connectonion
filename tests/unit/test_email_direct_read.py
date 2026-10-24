from unittest.mock import Mock,patch
import pytest
import connectonion.useful_tools.get_emails as _unused
from importlib import import_module
mail=import_module('connectonion.useful_tools.get_emails')
@pytest.mark.parametrize('name,path,record,key',[
 ('get_email','received',{'id':4000,'from':'a@example.com','text':'Old body','is_read':False},'message'),
 ('get_sent_email','sent',{'id':5000,'to':'b@example.com','body':'Old sent body'},'body')])
def test_direct_read_is_not_limited_to_recent_pages(name,path,record,key):
    response=Mock();response.json.return_value=record
    with patch.object(mail,'require_ambient_api_key',return_value='test-token'),patch.object(mail.requests,'get',return_value=response) as request:
        result=getattr(mail,name)(record['id'])
    assert request.call_args.args[0].endswith(f'/email/{path}/{record["id"]}')
    assert result[key]==record.get('text',record.get('body'))
    response.raise_for_status.assert_called_once()
@pytest.mark.parametrize('bad',[0,-1,True,'1/../../auth','x'])
def test_invalid_ids_are_rejected_without_auth_or_requests(bad):
    with patch.object(mail,'require_ambient_api_key') as auth:
        with pytest.raises(ValueError):mail.get_email(bad)
    auth.assert_not_called()
