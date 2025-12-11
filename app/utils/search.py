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
        self._initialized = True
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Make a request to Meilisearch"""
        try:
            url = f"{self.base_url}{endpoint}"
            if method == 'GET':
                response = requests.get(url, headers=self.headers, params=data)
            elif method == 'POST':
                response = requests.post(url, headers=self.headers, json=data)
            elif method == 'DELETE':
                response = requests.delete(url, headers=self.headers)
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
