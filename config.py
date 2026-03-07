import os
from dotenv import load_dotenv

load_dotenv()

def get_database_url():
    """Get database URL, handling Render's postgres:// prefix"""
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Render uses postgres:// but SQLAlchemy requires postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    # Default to SQLite for local development
    return 'sqlite:///bpbadi.db'

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    APP_PASSWORD = os.environ.get('APP_PASSWORD') or 'bpbadi2024'

    # Environment detection
    IS_PRODUCTION = os.environ.get('RENDER') == 'true'

    # Connection pool tuning — prevents stale connection errors after Render free tier sleep
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,   # test connection before use; reconnects transparently
        'pool_recycle': 300,     # recycle connections every 5 min (before Render closes them)
        'pool_size': 5,
        'max_overflow': 2,
    }
