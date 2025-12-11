from flask import jsonify
from datetime import datetime

def success_response(data: any = None, message: str = 'Success', 
                    status_code: int = 200):
    """Return a success response"""
    response = {
        'status': 'success',
        'message': message,
        'data': data
    }
    return jsonify(response), status_code

def error_response(message: str = 'Error', status_code: int = 400, 
                  error_code: str = None):
    """Return an error response"""
    response = {
        'status': 'error',
        'message': message
    }
    if error_code:
        response['error_code'] = error_code
    return jsonify(response), status_code

def validate_email(email: str) -> bool:
    """Validate email format"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def serialize_document(doc):
    """Serialize MongoDB document for JSON response"""
    from bson import ObjectId
    
    if doc is None:
        return None
    
    if isinstance(doc, ObjectId):
        return str(doc)
    
    if isinstance(doc, datetime):
        return doc.isoformat()
    
    if isinstance(doc, list):
        return [serialize_document(item) for item in doc]
    
    if not isinstance(doc, dict):
        return doc
    
    serialized = {}
    for key, value in doc.items():
        serialized[key] = serialize_document(value)
    
    return serialized

def paginate(collection, page: int = 1, per_page: int = 10):
    """Paginate query results"""
    skip = (page - 1) * per_page
    return skip, per_page
