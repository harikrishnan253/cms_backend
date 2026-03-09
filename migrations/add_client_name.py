"""
Migration script to add client_name column to projects table
Run this script to update the database schema
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from app.database import engine

def run_migration():
    """Add client_name column to projects table"""
    
    try:
        # Check if column already exists
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('projects')]
        
        if 'client_name' in columns:
            print("ℹ️  Column 'client_name' already exists in 'projects' table")
            print("   No migration needed!")
            return
        
        # SQLite-compatible migration
        migration_sql = "ALTER TABLE projects ADD COLUMN client_name VARCHAR;"
        
        with engine.connect() as connection:
            connection.execute(text(migration_sql))
            connection.commit()
            print("✅ Migration completed successfully!")
            print("   Added 'client_name' column to 'projects' table")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    print("Running migration: Add client_name to projects table...")
    print(f"Database: {engine.url}")
    run_migration()
