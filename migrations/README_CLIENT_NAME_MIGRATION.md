# Database Migration: Add Client Name to Projects

## Overview
This migration adds a `client_name` column to the `projects` table to store the client/publisher organization name.

## Changes Made

### 1. **Database Schema** (`app/models.py`)
- Added `client_name` column to the `Project` model
- Type: `String` (VARCHAR)
- Nullable: `True` (optional field)

### 2. **Frontend** (`app/templates/dashboard.html`)
- Added "Client Name" input field to the New Project modal
- Added "Client" column to the projects table
- Displays client name with a building icon badge

### 3. **Backend** (`app/routers/web.py`)
- Updated `create_project_with_files` route to accept `client_name` parameter
- Saves client name to database when creating new projects

## How to Apply the Migration

### Option 1: Using SQL (Recommended)
Run this SQL command in your PostgreSQL database:

```sql
ALTER TABLE projects ADD COLUMN IF NOT EXISTS client_name VARCHAR;
```

### Option 2: Using psql command line
```bash
psql -U your_username -d cms_db -c "ALTER TABLE projects ADD COLUMN client_name VARCHAR;"
```

### Option 3: Using pgAdmin or any PostgreSQL GUI
1. Connect to your database
2. Navigate to the `projects` table
3. Add a new column:
   - Name: `client_name`
   - Type: `VARCHAR` or `TEXT`
   - Nullable: `Yes`

### Option 4: Drop and Recreate (Development Only - WILL LOSE DATA!)
If you're in development and don't mind losing data:

```python
# In Python console or script
from app.database import engine, Base
from app import models

# WARNING: This will drop all tables and recreate them
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
```

## Verification

After running the migration, verify it worked:

```sql
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'projects' AND column_name = 'client_name';
```

Expected output:
```
 column_name | data_type | is_nullable
-------------+-----------+-------------
 client_name | varchar   | YES
```

## Usage

Once the migration is complete:

1. **Creating Projects**: Users can now enter a client name when creating new projects
2. **Viewing Projects**: The dashboard will display the client name in the projects table
3. **Optional Field**: Client name is optional - existing projects will have NULL values

## Rollback (if needed)

To remove the column:

```sql
ALTER TABLE projects DROP COLUMN IF EXISTS client_name;
```

## Notes

- The column is nullable, so existing projects will continue to work without any issues
- The frontend gracefully handles NULL values by displaying a "-" placeholder
- No data migration is needed for existing records
