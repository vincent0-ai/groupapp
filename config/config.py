import os
from datetime import timedelta

class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key')
    JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=3)
    
    # MongoDB
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/Discussio')
    MONGODB_DATABASE = os.getenv('MONGODB_DATABASE', 'Discussio')
    
    # Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # MinIO
    MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
    MINIO_ROOT_USER = os.getenv('MINIO_ROOT_USER', 'minioadmin')
    MINIO_ROOT_PASSWORD = os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')
    MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'Discussio')
    MINIO_USE_SSL = os.getenv('MINIO_USE_SSL', 'False') == 'True'
    
    # Meilisearch
    MEILISEARCH_URL = os.getenv('MEILISEARCH_URL', 'http://localhost:7700')
    MEILISEARCH_API_KEY = os.getenv('MEILISEARCH_API_KEY', 'masterKey')
    
    # App
    APP_URL = os.getenv('APP_URL', 'http://localhost:5000')
    MAX_CONTENT_LENGTH = 104857600  # 100MB
    UPLOAD_FOLDER = 'uploads'
    
    # Flask-SocketIO
    SOCKETIO_CORS_ALLOWED_ORIGINS = '*'

    # Gamification Points
    POINTS_CONFIG = {
        'CREATE_GROUP': 5,
        'SEND_MESSAGE': 1,
        'UPLOAD_FILE': 2,
        'JOIN_COMPETITION': 3
    }

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False

class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    MONGODB_DATABASE = 'Discussio_test'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
