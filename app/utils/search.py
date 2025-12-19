import requests
from flask import current_app
from typing import List, Dict, Any, Optional

class MeilisearchClient:
    """Meilisearch client for fast search functionality"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MeilisearchClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.base_url = current_app.config['MEILISEARCH_URL']
        self.api_key = current_app.config['MEILISEARCH_API_KEY']
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        # Basic validation to avoid accidental SSRF: base_url must be a non-empty http(s) URL
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.base_url)
            if parsed.scheme not in ('http', 'https') or not parsed.netloc:
                raise ValueError('MEILISEARCH_URL must be a valid http(s) URL')
        except Exception as e:
            print(f'Invalid Meilisearch base URL: {e}')
            # Prevent initialization from silently proceeding with an invalid URL
            raise
        self._initialized = True
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Make a request to Meilisearch"""
        try:
            url = f"{self.base_url}{endpoint}"
            # Use a short timeout and do not follow user-supplied redirects
            timeout = float(current_app.config.get('SEARCH_REQUEST_TIMEOUT', 5))
            if method == 'GET':
                response = requests.get(url, headers=self.headers, params=data, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, headers=self.headers, json=data, timeout=timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=self.headers, timeout=timeout)
            else:
                return None
            
            if response.status_code in [200, 201, 202]:
                return response.json() if response.text else {}
            else:
                print(f"Meilisearch error: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Error making Meilisearch request: {e}")
            return None
    
    def add_documents(self, index_name: str, documents: List[Dict]) -> bool:
        """Add documents to an index"""
        result = self._make_request('POST', f'/indexes/{index_name}/documents', {
            'documents': documents
        })
        return result is not None
    
    def search(self, index_name: str, query: str, limit: int = 10, 
               offset: int = 0, attributes_to_search: List[str] = None) -> Optional[Dict]:
        """Search in an index"""
        data = {
            'q': query,
            'limit': limit,
            'offset': offset
        }
        if attributes_to_search:
            data['attributesToSearchIn'] = attributes_to_search
        
        result = self._make_request('POST', f'/indexes/{index_name}/search', data)
        return result
    
    def update_document(self, index_name: str, document_id: str, 
                       document: Dict) -> bool:
        """Update a document"""
        result = self._make_request('POST', f'/indexes/{index_name}/documents', {
            'documents': [{**document, 'id': document_id}]
        })
        return result is not None
    
    def delete_document(self, index_name: str, document_id: str) -> bool:
        """Delete a document"""
        result = self._make_request('DELETE', 
                                   f'/indexes/{index_name}/documents/{document_id}')
        return result is not None
    
    def create_index(self, index_name: str, primary_key: str = 'id') -> bool:
        """Create an index"""
        result = self._make_request('POST', '/indexes', {
            'uid': index_name,
            'primaryKey': primary_key
        })
        return result is not None
    
    def index_exists(self, index_name: str) -> bool:
        """Check if an index exists"""
        result = self._make_request('GET', f'/indexes/{index_name}')
        return result is not None
