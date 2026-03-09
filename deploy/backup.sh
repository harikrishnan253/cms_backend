#!/bin/bash

# Backup Script for CMS
# Add to crontab: 0 3 * * * /path/to/backup.sh

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/var/backups/cms"
DB_NAME="cms_db"
DB_USER="cms_user"
UPLOAD_DIR="/var/www/cms_backend/data/uploads"

mkdir -p $BACKUP_DIR

# 1. Backup PostgreSQL
echo "Backing up Database..."
pg_dump -U $DB_USER $DB_NAME > "$BACKUP_DIR/db_$TIMESTAMP.sql"

# 2. Backup Uploads
echo "Backing up Files..."
tar -czf "$BACKUP_DIR/files_$TIMESTAMP.tar.gz" $UPLOAD_DIR

# 3. Retention Policy (keep last 7 days)
find $BACKUP_DIR -type f -mtime +7 -name "*.sql" -delete
find $BACKUP_DIR -type f -mtime +7 -name "*.tar.gz" -delete

echo "Backup completed: $TIMESTAMP"
