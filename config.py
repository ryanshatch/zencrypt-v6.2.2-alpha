"""Configuration settings for Zencrypt"""

import os
import multiprocessing

# Base directory of the application
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Flask configuration
class Config:
    # Basic Flask config
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'sqlite:///{os.path.join(BASE_DIR, "zencrypt.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File handling
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    
    # Parallel processing settings
    CHUNK_SIZE = 2 * 1024 * 1024  # 2MB chunks
    MAX_WORKERS = min(32, multiprocessing.cpu_count() * 2)  # 2 workers per CPU core, max 32
    USE_PROCESSES = True  # Use multiprocessing instead of threading for CPU-bound tasks
    
    # Cryptographic settings
    ECC_CURVE = 'secp384r1'  # Default ECC curve
    ARGON2_TIME_COST = 3     # Number of iterations
    ARGON2_MEMORY_COST = 65536  # Memory usage in KiB
    ARGON2_PARALLELISM = 4   # Number of parallel threads
    
    # Security settings
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or SECRET_KEY
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1 hour
    
    @staticmethod
    def init_app(app):
        # Create upload folder if it doesn't exist
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

class DevelopmentConfig(Config):
    DEBUG = True
    
class ProductionConfig(Config):
    DEBUG = False
    # Increase security in production
    MAX_WORKERS = min(16, multiprocessing.cpu_count())  # Limit workers in prod
    ARGON2_TIME_COST = 4  # Increase iterations
    ARGON2_MEMORY_COST = 131072  # Double memory usage
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        # Production-specific initialization
        if not os.environ.get('SECRET_KEY'):
            raise RuntimeError('SECRET_KEY must be set in production')

# Dictionary to map config names to classes
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
