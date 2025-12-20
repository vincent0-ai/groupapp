from datetime import datetime, timedelta
from app.models import Season


def test_create_season_doc_fields():
    start = datetime.utcnow()
    end = start + timedelta(days=7)
    doc = Season.create_season_doc('Week 1', start, end, '507f1f77bcf86cd799439011')
    assert doc['title'] == 'Week 1'
    assert doc['start_time'] == start
    assert doc['end_time'] == end
    assert 'is_active' in doc and doc['is_active'] is True
    assert isinstance(doc['group_scores'], dict)
    assert isinstance(doc['winners'], list)
    assert 'created_at' in doc and 'updated_at' in doc
