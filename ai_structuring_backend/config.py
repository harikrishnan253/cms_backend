"""
Configuration for the Pre-Editor backend.
"""

import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent.absolute()

# Folders
UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', str(BASE_DIR / 'uploads'))
OUTPUT_FOLDER = os.getenv('OUTPUT_FOLDER', str(BASE_DIR / 'outputs'))

# =====================================================
# Database configuration
# =====================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Production (PostgreSQL, etc.)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
else:
    # Development fallback (SQLite)
    DATABASE_PATH = os.getenv(
        "DATABASE_PATH",
        str(BASE_DIR / "dev.db")
    )
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"

SQLALCHEMY_TRACK_MODIFICATIONS = False

# API Keys
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')

# Flask
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max upload

# Processing
MAX_PARAGRAPHS_PER_CHUNK = 100
CONFIDENCE_THRESHOLD = 85
