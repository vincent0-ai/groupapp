from app.utils.permissions import compute_permissions


def test_compute_permissions_creator():
    wb = {'created_by': 'u1', 'can_draw': [], 'can_speak': [], 'can_share_screen': []}
    perms = compute_permissions(wb, 'u1')
    assert perms['can_draw']
    assert perms['can_speak']
    assert perms['can_share']
    assert perms['can_publish']


def test_compute_permissions_noncreator():
    wb = {
        'created_by': 'u1',
        'can_draw': ['u2'],
        'can_speak': [],
        'can_share_screen': []
    }
    perms = compute_permissions(wb, 'u2')
    assert perms['can_draw']
    assert not perms['can_speak']
    assert not perms['can_share']
    assert not perms['can_publish']
