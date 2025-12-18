from datetime import datetime, timezone
from app.utils.helpers import serialize_document


def test_serialize_naive_datetime_is_utc_z():
    dt = datetime(2025, 1, 1, 12, 0, 0)
    s = serialize_document(dt)
    assert isinstance(s, str)
    assert s.endswith('Z')
    assert 'T' in s


def test_serialize_aware_datetime_preserves_utc_z():
    dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    s = serialize_document(dt)
    assert s.endswith('Z')
    assert 'T' in s
