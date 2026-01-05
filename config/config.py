import os
from datetime import timedelta

class Config:
    """Base configuration"""
    # Do not provide production secret defaults here. Production MUST set these env vars.
    SECRET_KEY = os.getenv('SECRET_KEY')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=3)
    BCRYPT_ROUNDS = int(os.getenv('BCRYPT_ROUNDS', '12'))
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')

    # MongoDB
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/Discussio')
    MONGODB_DATABASE = os.getenv('MONGODB_DATABASE', 'Discussio')
    
    # Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Flask-Limiter
    LIMITER_STORAGE_URI = os.getenv('LIMITER_STORAGE_URI', REDIS_URL)
    DEFAULT_RATE_LIMITS = ["200 per day", "50 per hour"]
    
    # MinIO
    MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
    MINIO_ROOT_USER = os.getenv('MINIO_ROOT_USER', 'minioadmin')
    MINIO_ROOT_PASSWORD = os.getenv('MINIO_ROOT_PASSWORD')
    MINIO_BUCKET = os.getenv('MINIO_BUCKET', 'Discussio')
    MINIO_USE_SSL = os.getenv('MINIO_USE_SSL', 'False') == 'True'

    # LiveKit
    LIVEKIT_URL = os.getenv('LIVEKIT_URL', 'http://localhost:7880')
    LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY')
    LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET')
    
    # Meilisearch
    MEILISEARCH_URL = os.getenv('MEILISEARCH_URL', 'http://localhost:7700')
    MEILISEARCH_API_KEY = os.getenv('MEILISEARCH_API_KEY')
    
    # App
    APP_URL = os.getenv('APP_URL', 'http://localhost:5000')
    MAX_CONTENT_LENGTH = 104857600  # 100MB
    UPLOAD_FOLDER = 'uploads'
    MAX_PARTICIPANTS_PER_ROOM = int(os.getenv('MAX_PARTICIPANTS_PER_ROOM', '10'))
    
    # CORS / SocketIO allowed origins (set via env in production)
    CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', 'localhost:3000')
    SOCKETIO_CORS_ALLOWED_ORIGINS = os.getenv('SOCKETIO_CORS_ALLOWED_ORIGINS', 'localhost:3000')


    # Group Streaks
    GROUP_STREAK_MIN_PERCENT = float(os.getenv('GROUP_STREAK_MIN_PERCENT', '0.2'))  # fraction of members
    GROUP_STREAK_MIN_ABSOLUTE = int(os.getenv('GROUP_STREAK_MIN_ABSOLUTE', '2'))
    GROUP_STREAK_CHECK_INTERVAL_SECONDS = int(os.getenv('GROUP_STREAK_CHECK_INTERVAL_SECONDS', '3600'))
    # Allow streaks to tolerate short inactivity windows (days). If there is no sufficient activity
    # for more than this number of days, the streak will be reset. Default: 7 days.
    GROUP_STREAK_MAX_GAP_DAYS = int(os.getenv('GROUP_STREAK_MAX_GAP_DAYS', '7'))

    # Seasons
    SEASON_LENGTH_DAYS = int(os.getenv('SEASON_LENGTH_DAYS', '7'))  # weeks are 7 days by default
    AUTO_CREATE_SEASONS = os.getenv('AUTO_CREATE_SEASONS', 'False') == 'True'  # manual by default


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    # Provide convenient defaults for development (NOT for production)
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key')
    MINIO_ROOT_PASSWORD = os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')
    MEILISEARCH_API_KEY = os.getenv('MEILISEARCH_API_KEY', 'masterKey')


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False

class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    MONGODB_DATABASE = 'Discussio_test'
    # Keep predictable test keys
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key')


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
