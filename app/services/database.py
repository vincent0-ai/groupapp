from pymongo import MongoClient, ASCENDING, DESCENDING
from flask import current_app
from typing import List, Dict, Optional
from bson import ObjectId

class Database:
    """MongoDB database service"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.client = MongoClient(current_app.config['MONGODB_URI'])
        self.db = self.client[current_app.config['MONGODB_DATABASE']]
        self._create_indexes()
        self._initialized = True
    
    def _create_indexes(self):
        """Create indexes for collections"""
        # Users indexes
        self.db.users.create_index('email', unique=True)
        self.db.users.create_index('username', unique=True)
        
        # Groups indexes
        self.db.groups.create_index('owner_id')
        self.db.groups.create_index('name')
        
        # Messages indexes
        self.db.messages.create_index('channel_id')
        self.db.messages.create_index('user_id')
        self.db.messages.create_index('group_id')
        self.db.messages.create_index([('created_at', DESCENDING)])
        
        # Competitions indexes
        self.db.competitions.create_index('group_id')
        self.db.competitions.create_index('created_by')
        self.db.competitions.create_index('start_time')
        
        # Files indexes
        self.db.files.create_index('uploaded_by')
        self.db.files.create_index('group_id')
        self.db.files.create_index([('created_at', DESCENDING)])
    
    def insert_one(self, collection_name: str, document: Dict) -> Optional[str]:
        """Insert a single document"""
        try:
            result = self.db[collection_name].insert_one(document)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error inserting document: {e}")
            return None
    
    def find_one(self, collection_name: str, query: Dict) -> Optional[Dict]:
        """Find a single document"""
        try:
            return self.db[collection_name].find_one(query)
        except Exception as e:
            print(f"Error finding document: {e}")
            return None
    
    def find(self, collection_name: str, query: Dict, skip: int = 0, 
            limit: int = 0, sort: tuple = None) -> List[Dict]:
        """Find multiple documents"""
        try:
            cursor = self.db[collection_name].find(query).skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            if sort:
                cursor = cursor.sort(sort[0], sort[1])
            return list(cursor)
        except Exception as e:
            print(f"Error finding documents: {e}")
            return []
    
    def update_one(self, collection_name: str, query: Dict, 
                  update: Dict) -> bool:
        """Update a single document"""
        try:
            result = self.db[collection_name].update_one(query, {'$set': update})
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating document: {e}")
            return False
    
    def update_many(self, collection_name: str, query: Dict, 
                   update: Dict) -> int:
        """Update multiple documents"""
        try:
            result = self.db[collection_name].update_many(query, {'$set': update})
            return result.modified_count
        except Exception as e:
            print(f"Error updating documents: {e}")
            return 0
    
    def delete_one(self, collection_name: str, query: Dict) -> bool:
        """Delete a single document"""
        try:
            result = self.db[collection_name].delete_one(query)
            return result.deleted_count > 0
        except Exception as e:
            print(f"Error deleting document: {e}")
            return False
    
    def delete_many(self, collection_name: str, query: Dict) -> int:
        """Delete multiple documents"""
        try:
            result = self.db[collection_name].delete_many(query)
            return result.deleted_count
        except Exception as e:
            print(f"Error deleting documents: {e}")
            return 0
    
    def count(self, collection_name: str, query: Dict = None) -> int:
        """Count documents"""
        try:
            query = query or {}
            return self.db[collection_name].count_documents(query)
        except Exception as e:
            print(f"Error counting documents: {e}")
            return 0
    
    def push_to_array(self, collection_name: str, query: Dict, 
                     field: str, value) -> bool:
        """Push a value to an array field"""
        try:
            result = self.db[collection_name].update_one(query, 
                                                         {'$push': {field: value}})
            return result.modified_count > 0
        except Exception as e:
            print(f"Error pushing to array: {e}")
            return False
    
    def pull_from_array(self, collection_name: str, query: Dict, 
                       field: str, value) -> bool:
        """Remove a value from an array field"""
        try:
            result = self.db[collection_name].update_one(query, 
                                                         {'$pull': {field: value}})
            return result.modified_count > 0
        except Exception as e:
            print(f"Error pulling from array: {e}")
            return False
    
    def increment(self, collection_name: str, query: Dict, 
                 field: str, amount: int = 1) -> bool:
        """Increment a numeric field"""
        try:
            result = self.db[collection_name].update_one(query, 
                                                         {'$inc': {field: amount}})
            return result.modified_count > 0
        except Exception as e:
            print(f"Error incrementing field: {e}")
            return False
    
    def close(self):
        """Close database connection"""
        self.client.close()
