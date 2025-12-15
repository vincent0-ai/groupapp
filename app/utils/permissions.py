def compute_permissions(wb, user_id):
    """Return permission booleans for a user in a whiteboard document."""
    is_creator = str(wb.get('created_by')) == str(user_id)
    can_draw = is_creator or str(user_id) in [str(x) for x in wb.get('can_draw', [])]
    can_speak = is_creator or str(user_id) in [str(x) for x in wb.get('can_speak', [])]
    can_share = is_creator or str(user_id) in [str(x) for x in wb.get('can_share_screen', [])]
    return {
        'can_draw': can_draw,
        'can_speak': can_speak,
        'can_share': can_share,
        'can_publish': bool(can_speak or can_share)
    }
