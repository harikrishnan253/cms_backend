# CMS Backend — Linux Deployment Guide

> **Production requirement**: Nginx must be installed and configured as a reverse proxy. It handles routing browser traffic to the FastAPI backend (port 8000) and exposes a clean public URL. Without it, your server port `8000` is exposed directly, which is insecure and fragile.

Complete guide to deploying the full CMS backend stack on a Linux server using Docker Compose.

---

## Architecture Overview

```
Browser
  │
  ├── :80/:443 ──► Nginx (reverse proxy, optional)
  │                     │
  │                     ▼
  │              :8000 ── FastAPI Backend (Gunicorn + Uvicorn)
  │                     │          │
  │                     │     PostgreSQL :5432
  │                     │          │
  │                     │       Redis :6379
  │                     │          │
  │                     │   Celery Worker (background jobs)
  │
  └── :9980 ──► Collabora (LibreOffice Online, WOPI doc editing)
```

### Processing Pipelines Included
| Engine | What it does | Dependencies |
|---|---|---|
| **PPDEngine** | Manuscript analysis dashboard (citations, formatting, multilingual) | `python-docx`, `lxml`, `chardet` |
| **BiasEngine** | Scans for bias terms, highlights DOCX, generates Excel + ZIP | `python-docx`, `openpyxl`, `pdfplumber`, LibreOffice (`soffice`) |
| **ReferencesEngine** | APA/AMA reference structuring + validation via CrossRef, PubMed, Google Books | `requests`, `python-docx`, `lxml` |
| **PermissionsEngine** | Extracts figure credit lines (regex-based) | `python-docx`, `openpyxl` |
| **AIExtractorEngine** | AI-based credit line extraction via Gemini | `google-genai` |
| **XMLEngine** | Converts DOCX → BITS XML via Perl + Saxon XSLT | **Perl**, **Java** (`saxon.jar`), CPAN modules |
| **StructuringEngine** | Applies book-styling rules to DOCX paragraphs | `python-docx`, `lxml`, `PyYAML` |
| **WOPI / Collabora** | In-browser DOCX editing | **Collabora CODE** container |

---

## Step 1: Prepare the Server

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker + Nginx
sudo apt-get install -y docker.io docker-compose nginx
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# → Log out and back in for group changes to take effect

# Verify
docker --version
docker-compose --version
```

---

## Step 2: Clone / Deploy the Code

```bash
# Create app directory
sudo mkdir -p /var/www/cms_backend
sudo chown $USER:$USER /var/www/cms_backend

cd /var/www/cms_backend
git clone <your-repo-url> .
# OR: copy files via rsync / scp
```

---

## Step 3: Configure Environment Variables

Create a `.env` file in the project root. **Never commit this file to Git.**

```bash
cp .env .env.bak   # backup default
nano .env
```

Populate it with the following (replace all `<...>` placeholders):

```env
# ── Database ─────────────────────────────────────────────────────────────────
POSTGRES_USER=cms_user
POSTGRES_PASSWORD=<strong_password_here>
POSTGRES_DB=cms_db
DATABASE_URL=postgresql://cms_user:<strong_password_here>@db:5432/cms_db

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ── App Security ──────────────────────────────────────────────────────────────
SECRET_KEY=<generate_with: python3 -c "import secrets; print(secrets.token_hex(32))">
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# ── Project ───────────────────────────────────────────────────────────────────
PROJECT_NAME=Publishing CMS
API_V1_STR=/api/v1

# ── LibreOffice / Collabora WOPI Integration ──────────────────────────────────
# COLLABORA_URL: URL the END USER's BROWSER uses to connect to Collabora.
#   ► In production: use your public IP or domain (ensure port 9980 is open)
#   ► Example: http://203.0.113.10:9980
COLLABORA_URL=http://<your-server-ip-or-domain>:9980

# WOPI_BASE_URL: URL Collabora uses INTERNALLY to call back to the FastAPI backend.
#   ► Use the internal Docker Compose service name "backend"
WOPI_BASE_URL=http://backend:8000

# ── AI Extractor (Gemini) ─────────────────────────────────────────────────────
# Required by AIExtractorEngine (permissions/AI extraction feature)
GEMINI_API_KEY=<your_google_gemini_api_key>
GOOGLE_API_KEY=<your_google_api_key_if_different>
```

> ⚠️ **Important**: `COLLABORA_URL` must be reachable by the user's browser. In production, this should be your server's public IP or domain on port `9980`. `WOPI_BASE_URL` is used by Collabora internally, so `http://backend:8000` (Docker service name) is correct.

---

## Step 4: Build and Launch All Services

```bash
cd /var/www/cms_backend

# Build images and start all services
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Check all services are running
docker-compose ps
```

Expected services running:
- `cms_db` — PostgreSQL
- `cms_redis` — Redis
- `cms_backend` — FastAPI (Gunicorn)
- `cms_celery_worker` — Celery worker
- `cms_collabora` — LibreOffice Online

---

## Step 5: Initialize the Database (First-time only)

Run Alembic migrations to create all tables:

```bash
docker-compose exec backend alembic upgrade head
```

Seed roles and initial data:

```bash
docker-compose exec backend python seed_db.py
```

Reset admin user if needed:

```bash
docker-compose exec backend python reset_admin.py
```

---

## Step 6: Verify the Deployment

```bash
# Check backend logs
docker-compose logs -f backend

# Check celery worker logs
docker-compose logs -f celery_worker

# Check collabora logs
docker-compose logs -f collabora

# Test the API
curl http://localhost:8000/
# Expected: {"message": "Welcome to the Publishing CMS API"}
```

---

## Step 7: Configure Nginx Reverse Proxy *(Required for Production)*

Nginx is included as a Docker Compose service (`cms_nginx`) — no separate installation needed. It automatically starts with the stack and routes port `80` → FastAPI backend.

The config file is at `nginx/nginx.conf` (already created in the project). It handles:
- Large file uploads (up to 200MB)
- Long request timeouts (300s) for processing jobs
- WebSocket upgrade headers for Collabora DOCX editing

### Add SSL with Let's Encrypt (run on the host, not in Docker)

```bash
# Install certbot on the host once
sudo apt-get install -y certbot

# Stop nginx temporarily to issue the cert
docker-compose stop nginx

# Get the certificate (replace with your actual domain)
sudo certbot certonly --standalone -d your-domain.com

# Certs are saved to /etc/letsencrypt/live/your-domain.com/
# docker-compose.yml mounts /etc/letsencrypt into the nginx container automatically

# Restart nginx
docker-compose start nginx
```

### Update nginx.conf for HTTPS

Once certificates are in place, update `nginx/nginx.conf` to add the HTTPS server block:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Redirect all HTTP → HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # FastAPI backend
    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
        client_max_body_size 100M;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## Maintenance Commands

```bash
# View running containers
docker-compose ps

# Restart a specific service
docker-compose restart backend

# Pull latest code and redeploy
git pull origin main
docker-compose build backend celery_worker
docker-compose up -d

# Run a Django-style management command
docker-compose exec backend python reset_admin.py

# Tail all logs
docker-compose logs -f

# Stop everything
docker-compose down

# Stop and remove volumes (DESTRUCTIVE - deletes DB data)
docker-compose down -v
```

---

## Fallback: Native Systemd Deployment (Without Docker)

If you prefer to run without Docker using the existing `deploy/` service files:

```bash
# 1. Install system dependencies
sudo apt-get install -y \
    python3-venv gcc libpq-dev libxml2-dev libxslt-dev \
    postgresql postgresql-contrib redis-server \
    libreoffice-writer default-jre \
    perl cpanminus make

# 2. Install Perl CPAN modules
cpanm Archive::Zip File::Copy::Recursive File::HomeDir \
      HTTP::Tiny List::MoreUtils String::Substitution \
      Try::Tiny XML::LibXML

# 3. Set up Python virtualenv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Set up PostgreSQL
sudo -u postgres psql -c "CREATE USER cms_user WITH PASSWORD 'cms_pass';"
sudo -u postgres psql -c "CREATE DATABASE cms_db OWNER cms_user;"

# 5. Run migrations
alembic upgrade head

# 6. Install systemd services
sudo cp deploy/cms-backend.service /etc/systemd/system/
sudo cp deploy/cms-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cms-backend cms-worker

# 7. Check status
sudo systemctl status cms-backend
sudo systemctl status cms-worker
```
