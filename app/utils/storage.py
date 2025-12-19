from minio import Minio
from minio.error import S3Error
import os
from flask import current_app
from datetime import timedelta
from urllib.parse import urlparse

class MinioClient:
    """MinIO client for S3-compatible file storage"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MinioClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Parse endpoint - MinIO client only accepts host:port, not full URLs
        endpoint = current_app.config['MINIO_ENDPOINT']
        use_ssl = current_app.config['MINIO_USE_SSL']
        
        # If endpoint looks like a URL, parse it
        if endpoint.startswith('http://') or endpoint.startswith('https://'):
            parsed = urlparse(endpoint)
            endpoint = parsed.netloc  # Extract just host:port
            # If URL uses https, enable SSL
            if parsed.scheme == 'https':
                use_ssl = True
        
        self.client = Minio(
            endpoint,
            access_key=current_app.config['MINIO_ROOT_USER'],
            secret_key=current_app.config['MINIO_ROOT_PASSWORD'],
            secure=use_ssl
        )
        self.bucket = current_app.config['MINIO_BUCKET']
        self._ensure_bucket_exists()
        self._initialized = True
    
    def _ensure_bucket_exists(self):
        """Ensure the bucket exists, create if not"""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error as e:
            print(f"Error creating bucket: {e}")
    
    def _validate_object_name(self, object_name: str) -> bool:
        """Basic validation to avoid accidental path traversal or absolute paths."""
        if not object_name or '..' in object_name or object_name.startswith('/') or '\\' in object_name:
            return False
        return True

    def upload_file(self, file_path: str, object_name: str, 
                   content_type: str = 'application/octet-stream') -> bool:
        """Upload a file to MinIO"""
        if not self._validate_object_name(object_name):
            print(f"Rejected upload due to invalid object_name: {object_name}")
            return False
        try:
            file_size = os.path.getsize(file_path)
            with open(file_path, 'rb') as file_data:
                self.client.put_object(
                    self.bucket,
                    object_name,
                    file_data,
                    file_size,
                    content_type=content_type
                )
            return True
        except S3Error as e:
            print(f"Error uploading file: {e}")
            return False
    
    def download_file(self, object_name: str, file_path: str) -> bool:
        """Download a file from MinIO"""
        try:
            response = self.client.get_object(self.bucket, object_name)
            with open(file_path, 'wb') as file_data:
                for d in response.stream(32*1024):
                    file_data.write(d)
            response.close()
            response.release_conn()
            return True
        except S3Error as e:
            print(f"Error downloading file: {e}")
            return False
    
    def delete_file(self, object_name: str) -> bool:
        """Delete a file from MinIO"""
        if not self._validate_object_name(object_name):
            print(f"Rejected delete due to invalid object_name: {object_name}")
            return False
        try:
            self.client.remove_object(self.bucket, object_name)
            return True
        except S3Error as e:
            print(f"Error deleting file: {e}")
            return False
    
    def get_presigned_url(self, object_name: str, 
                         expires: int = 3600) -> str:
        """Get a presigned URL for a file"""
        if not self._validate_object_name(object_name):
            print(f"Rejected presigned URL due to invalid object_name: {object_name}")
            return None
        try:
            url = self.client.presigned_get_object(
                self.bucket,
                object_name,
                expires=timedelta(seconds=expires)
            )
            return url
        except S3Error as e:
            print(f"Error generating presigned URL: {e}")
            return None
    
    def list_objects(self, prefix: str = '', recursive: bool = True):
        """List objects in the bucket"""
        try:
            objects = self.client.list_objects(
                self.bucket,
                prefix=prefix,
                recursive=recursive
            )
            return [obj for obj in objects]
        except S3Error as e:
            print(f"Error listing objects: {e}")
            return []
