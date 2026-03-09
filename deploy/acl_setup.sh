#!/bin/bash

# ACL Setup for CMS Directories
# Run as root

# 1. Create Groups if not exist
groupadd cms_admins
groupadd cms_editors
groupadd cms_viewers

# 2. Main Directories
DATA_DIR="/var/www/cms_backend/data"
UPLOADS_DIR="$DATA_DIR/uploads"

mkdir -p $UPLOADS_DIR

# 3. Set Base Permissions (Owner: cms_user, Group: www-data)
chown -R cms_user:www-data $DATA_DIR
chmod -R 770 $DATA_DIR

# 4. Set ACLs
# Admins: Read/Write/Execute
setfacl -R -m g:cms_admins:rwx $DATA_DIR
setfacl -R -d -m g:cms_admins:rwx $DATA_DIR

# Editors: Read/Write (Uploads)
setfacl -R -m g:cms_editors:rwX $UPLOADS_DIR
setfacl -R -d -m g:cms_editors:rwX $UPLOADS_DIR

# Viewers: Read Only
setfacl -R -m g:cms_viewers:r-X $UPLOADS_DIR
setfacl -R -d -m g:cms_viewers:r-X $UPLOADS_DIR

echo "ACLs applied successfully."
