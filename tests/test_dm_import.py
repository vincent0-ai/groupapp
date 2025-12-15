import importlib.util
import sys
import types
from pathlib import Path


def _make_dummy_flask():
    flask_mod = types.ModuleType('flask')

    class DummyBlueprint:
        def __init__(self, *args, **kwargs):
            pass

    def _jsonify(x):
        return x

    # minimal objects used by dm.py
    flask_mod.Blueprint = DummyBlueprint
    flask_mod.jsonify = _jsonify
    flask_mod.request = types.SimpleNamespace()
    flask_mod.g = types.SimpleNamespace()

    sys.modules['flask'] = flask_mod


def test_dm_imports():
    _make_dummy_flask()
    file_path = Path('app/routes/dm.py')
    spec = importlib.util.spec_from_file_location('dm_test', file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, 'dm_bp')
