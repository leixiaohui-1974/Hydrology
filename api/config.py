"""Configuration settings for the Hydrology Framework REST API.

This module contains configuration classes for different environments
and API-specific settings.
"""

import os
from datetime import timedelta


class BaseConfig:
    """Base configuration class."""
    
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hydrology-framework-secret-key-change-in-production'
    
    # API settings
    API_TITLE = 'Hydrology Framework API'
    API_VERSION = '1.0.0'
    API_DESCRIPTION = 'RESTful API for hydrology modeling and simulation'
    
    # CORS settings
    CORS_ORIGINS = ['http://localhost:3000', 'http://localhost:8080']
    CORS_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    CORS_HEADERS = ['Content-Type', 'Authorization']
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = 'memory://'
    RATELIMIT_DEFAULT = '100 per hour'
    RATELIMIT_HEADERS_ENABLED = True
    
    # JWT settings
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_ALGORITHM = 'HS256'
    
    # Pagination
    DEFAULT_PAGE_SIZE = 10
    MAX_PAGE_SIZE = 100
    
    # File upload
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '..', 'uploads')
    ALLOWED_EXTENSIONS = {'csv', 'txt', 'json', 'xlsx'}
    
    # Simulation settings
    MAX_SIMULATION_TIME = 300  # 5 minutes
    SIMULATION_CLEANUP_INTERVAL = 3600  # 1 hour
    MAX_CONCURRENT_SIMULATIONS = 10
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Database (if using one)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///hydrology.db'
    
    # Redis (for caching and session storage)
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # Security
    BCRYPT_LOG_ROUNDS = 12
    WTF_CSRF_ENABLED = False  # Disabled for API
    
    # Performance
    JSONIFY_PRETTYPRINT_REGULAR = False
    
    @staticmethod
    def init_app(app):
        """Initialize application with this config."""
        pass


class DevelopmentConfig(BaseConfig):
    """Development configuration."""
    
    DEBUG = True
    TESTING = False
    
    # More permissive CORS for development
    CORS_ORIGINS = ['*']
    
    # Relaxed rate limiting
    RATELIMIT_DEFAULT = '1000 per hour'
    
    # Longer token expiry for development
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    
    # Enable pretty printing for development
    JSONIFY_PRETTYPRINT_REGULAR = True
    
    # Lower bcrypt rounds for faster development
    BCRYPT_LOG_ROUNDS = 4
    
    LOG_LEVEL = 'DEBUG'


class TestingConfig(BaseConfig):
    """Testing configuration."""
    
    DEBUG = True
    TESTING = True
    
    # Use in-memory database for testing
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    
    # Disable rate limiting for tests
    RATELIMIT_ENABLED = False
    
    # Short token expiry for testing
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)
    
    # Fast bcrypt for tests
    BCRYPT_LOG_ROUNDS = 4
    
    # Disable CSRF for API testing
    WTF_CSRF_ENABLED = False
    
    LOG_LEVEL = 'WARNING'


class ProductionConfig(BaseConfig):
    """Production configuration."""
    
    DEBUG = False
    TESTING = False
    
    # Strict CORS for production
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '').split(',')
    
    # Stricter rate limiting
    RATELIMIT_DEFAULT = '60 per hour'
    
    # Secure JWT settings
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    
    # Production database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://user:password@localhost/hydrology_prod'
    
    # Production Redis
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # Higher security
    BCRYPT_LOG_ROUNDS = 15
    
    # Production logging
    LOG_LEVEL = 'WARNING'
    
    @staticmethod
    def init_app(app):
        """Initialize production app."""
        BaseConfig.init_app(app)
        
        # Log to syslog in production
        import logging
        from logging.handlers import SysLogHandler
        
        syslog_handler = SysLogHandler()
        syslog_handler.setLevel(logging.WARNING)
        app.logger.addHandler(syslog_handler)


class DockerConfig(ProductionConfig):
    """Docker container configuration."""
    
    # Use environment variables for Docker
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://postgres:password@db:5432/hydrology'
    
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://redis:6379/0'
    
    # Docker-specific settings
    HOST = '0.0.0.0'
    PORT = int(os.environ.get('PORT', 5000))


# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'docker': DockerConfig,
    'default': DevelopmentConfig
}


def get_config(config_name=None):
    """Get configuration class by name."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    return config.get(config_name, config['default'])


# API-specific configuration
class APIConfig:
    """API-specific configuration settings."""
    
    # API versioning
    API_VERSION_HEADER = 'X-API-Version'
    DEFAULT_API_VERSION = '1.0'
    SUPPORTED_VERSIONS = ['1.0']
    
    # Response format
    DEFAULT_RESPONSE_FORMAT = 'json'
    SUPPORTED_FORMATS = ['json', 'xml']
    
    # Error handling
    INCLUDE_ERROR_DETAILS = True  # Set to False in production
    ERROR_INCLUDE_MESSAGE = True
    ERROR_INCLUDE_TRACEBACK = False  # Set to True only in development
    
    # Caching
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes
    
    # Monitoring
    ENABLE_METRICS = True
    METRICS_ENDPOINT = '/metrics'
    
    # Documentation
    ENABLE_SWAGGER = True
    SWAGGER_URL = '/docs'
    SWAGGER_CONFIG = {
        'title': 'Hydrology Framework API',
        'version': '1.0.0',
        'description': 'RESTful API for hydrology modeling and simulation',
        'termsOfService': '',
        'contact': {
            'name': 'API Support',
            'email': 'support@hydrology-framework.com'
        },
        'license': {
            'name': 'MIT',
            'url': 'https://opensource.org/licenses/MIT'
        }
    }
    
    # Health check
    HEALTH_CHECK_ENDPOINT = '/health'
    HEALTH_CHECK_DETAILED = True
    
    # Request/Response middleware
    ENABLE_REQUEST_LOGGING = True
    ENABLE_RESPONSE_COMPRESSION = True
    
    # Validation
    STRICT_VALIDATION = True
    VALIDATE_RESPONSES = False  # Set to True in development