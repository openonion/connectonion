"""A synthetic OS credential store for platform-independent profile tests."""
import os
from types import SimpleNamespace
import pytest
from connectonion.useful_tools.synology_profiles import ProfileStore

STORAGE='keyring' if os.name=='nt' else 'file'


@pytest.fixture(autouse=True)
def isolated_keyring(monkeypatch):
    values={}
    class Missing(Exception):
        pass
    def delete(service,key):
        if (service,key) not in values:
            raise Missing()
        del values[service,key]
    fake=SimpleNamespace(set_password=lambda service,key,value:values.__setitem__((service,key),value),
                         get_password=lambda service,key:values.get((service,key)),delete_password=delete,
                         errors=SimpleNamespace(PasswordDeleteError=Missing))
    monkeypatch.setattr(ProfileStore,'_keyring',staticmethod(lambda:fake))
