from app.models import Argument
import pytest


def test_create_argument_doc_valid():
    doc = Argument.create_argument_doc('claim', 'This is a claim', '605c72a7a0f1b2b4c3d4e5f6', '605c72a7a0f1b2b4c3d4e5f7')
    assert doc['node_type'] == 'claim'
    assert 'content' in doc and doc['content'] == 'This is a claim'
    assert 'author_id' in doc
    assert 'group_id' in doc
    assert doc['parent_id'] is None


def test_create_argument_invalid_type():
    with pytest.raises(ValueError):
        Argument.create_argument_doc('invalid_type', 'x', '605c72a7a0f1b2b4c3d4e5f6', '605c72a7a0f1b2b4c3d4e5f7')
