"""The optional adapters use bounded read-only transports and explicit grants."""
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from connectonion.useful_tools import synology_inspections as inspect
from connectonion.useful_tools.synology_transport import SynologyError


def snmp_module(monkeypatch, walk):
    engine=Mock()
    target=Mock()
    async def create(*args,**kwargs):
        target(*args,**kwargs)
        return 'target'
    fake=SimpleNamespace(USM_AUTH_HMAC96_SHA='sha',USM_AUTH_HMAC192_SHA256='sha256',
                         USM_PRIV_CFB128_AES='aes',SnmpEngine=Mock(return_value=engine),
                         UdpTransportTarget=SimpleNamespace(create=create),UsmUserData=Mock(),
                         ContextData=Mock(),ObjectType=lambda x:x,ObjectIdentity=lambda x:x,walk_cmd=walk)
    monkeypatch.setitem(sys.modules,'pysnmp',SimpleNamespace())
    monkeypatch.setitem(sys.modules,'pysnmp.hlapi',SimpleNamespace())
    monkeypatch.setitem(sys.modules,'pysnmp.hlapi.v3arch',SimpleNamespace(asyncio=fake))
    return fake,engine,target


def test_snmp_uses_authpriv_and_closes_dispatcher(monkeypatch):
    calls=[]
    Integer32=type('Integer32',(),{'__int__':lambda s:7,'prettyPrint':lambda s:'7'})
    async def walk(*args,**kwargs):
        calls.append((args,kwargs))
        yield None,0,0,[('1.3.6.1.4.1.6574.1.2.0',Integer32())]
    fake,engine,target=snmp_module(monkeypatch,walk)
    values=inspect.snmp_values({'host':'nas.test','username':'reader'},
                               {'snmp_auth':'auth-secret','snmp_priv':'privacy-secret'},[inspect.SYSTEM],1)
    assert values[inspect.SYSTEM+'.2.0']==7
    assert fake.UsmUserData.call_args.kwargs=={'authProtocol':'sha256','privProtocol':'aes'}
    assert calls[0][1]=={'lookupMib':False,'lexicographicMode':False}
    assert target.call_args.kwargs['retries']==0
    engine.close_dispatcher.assert_called_once()


def test_snmp_timeout_is_bounded_and_sanitized(monkeypatch):
    async def walk(*args,**kwargs):
        await asyncio.sleep(1)
        yield None,0,0,[]
    _,engine,_=snmp_module(monkeypatch,walk)
    with pytest.raises(SynologyError) as error:
        inspect.snmp_values({'host':'nas.test','username':'reader'},
                            {'snmp_auth':'secret','snmp_priv':'secret'},[inspect.SYSTEM],.01)
    assert error.value.code=='timeout' and 'secret' not in str(error.value)
    engine.close_dispatcher.assert_called_once()


def test_ssh_rejects_unknown_hosts_and_disables_credential_fallback(monkeypatch):
    client=Mock(); client.connect.side_effect=RuntimeError('secret internal detail')
    reject=object()
    monkeypatch.setitem(sys.modules,'paramiko',SimpleNamespace(SSHClient=lambda:client,RejectPolicy=lambda:reject))
    with pytest.raises(SynologyError) as error:
        inspect.ssh_services({'host':'nas.test','username':'reader','key_file':'/synthetic/key',
                              'known_hosts':'/synthetic/known_hosts'},1)
    client.set_missing_host_key_policy.assert_called_once_with(reject)
    kwargs=client.connect.call_args.kwargs
    assert kwargs['look_for_keys'] is False and kwargs['allow_agent'] is False
    assert 'password' not in kwargs and 'secret' not in str(error.value)
    client.close.assert_called_once()
