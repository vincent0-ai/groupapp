import importlib.util
import sys
import types
from pathlib import Path


def _make_dummy_livekit():
    api = types.SimpleNamespace()

    class DummyAccessToken:
        def __init__(self, key, secret):
            self.key = key
            self.secret = secret

        def with_identity(self, identity):
            return self

        def with_name(self, name):
            return self

        def with_grants(self, grants):
            return self

        def to_jwt(self):
            return "dummy.jwt"

    api.AccessToken = DummyAccessToken
    # Intentionally do NOT add VideoGrant to simulate older SDK
    rtc = types.SimpleNamespace(RpcError=Exception)
    sys.modules['livekit'] = types.ModuleType('livekit')
    sys.modules['livekit.api'] = api
    sys.modules['livekit.rtc'] = rtc


def test_create_token_with_compat_grant():
    _make_dummy_livekit()
    # Prevent importing the package-level app/__init__.py; load module directly
    file_path = Path('app/services/livekit_service.py')
    spec = importlib.util.spec_from_file_location('livekit_service_test', file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    vg = mod.VideoGrants(room_join=True, room='r', can_publish=True)
    svc = mod.LiveKitService(api_key='k', api_secret='s', url='u')
    token = svc.create_access_token('u1', 'name', 'r', vg)
    assert token == 'dummy.jwt'
