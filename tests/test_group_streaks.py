from app.models import GroupStreak


def test_create_group_streak_doc_defaults():
    gdoc = GroupStreak.create_group_streak_doc('605c72a7a0f1b2b4c3d4e5f7')
    assert gdoc['streak_count'] == 0
    assert 'group_id' in gdoc
    assert 'created_at' in gdoc


def test_create_group_streak_doc_with_values():
    gdoc = GroupStreak.create_group_streak_doc('605c72a7a0f1b2b4c3d4e5f7', streak_count=5, last_active_day='2025-12-18', threshold=3)
    assert gdoc['streak_count'] == 5
    assert gdoc['last_active_day'] == '2025-12-18'
    assert gdoc['threshold'] == 3
