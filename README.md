# CMS Backend Project Documentation

## 1. Overview
This project is a Content Management System (CMS) designed for the publishing industry. It facilitates the workflow of receiving manuscripts, processing them (structuring, styling, XML tagging), and managing the publication lifecycle through various stages (Art, InDesign, Proof, XML).

### Key Features
- **Project Structure:** Hierarchical organization of Projects > Chapters > Files.
- **Role-Based Access Control (RBAC):** Granular permissions for Project Managers, Editors, Typesetters, etc.
- **Workflow Automation:** Automated status transitions and task tracking.
- **Structuring Engine:** Automated analysis and styling of DOCX manuscripts using Python logic.
- **In-Browser Editing:** Integration with LibreOffice Online (Collabora) for editing Word documents directly within the browser without downloading.
- **Versioning:** checkout/check-in mechanism to prevent conflicts.

---

## 2. Architecture

### Backend
- **Framework:** FastAPI (Python 3.10+)
- **Database:** SQLAlchemy ORM with SQLite (development) or PostgreSQL (production).
- **Asynchronous:** Fully async route handlers for high performance.
- **Authentication:** Cookie-based session authentication with hashed passwords.

### Frontend
- **Templating:** Jinja2 (server-side rendering).
- **Styling:** Tailwind CSS (via CDN or build process).
- **Interactivity:** Vanilla JavaScript for dynamic behaviors (modals, dropdowns, AJAX).

### Integrations
- **Collabora Online:** Docker container running LibreOffice Online for WOPI-based document editing.
- **Gemini API:** (Optional) Integration for AI-assisted tasks like alt-text generation.

---

## 3. Key Modules

### 3.1 User & Team Management
- **Users:** Managed via `app/routers/users.py`.
- **Teams:** Organize users into functional groups.
- **Roles:** Defined in `app/models.py` (e.g., `Admin`, `ProjectManager`, `Editor`).

### 3.2 File Management (`app/routers/files.py`)
- **Upload:** Supports multi-file upload with category assignment (Manuscript, Art, etc.).
- **Checkout/Checkin:** Locks files to prevents concurrent edits.
- **Versioning:** Keeps history of file changes.

### 3.3 Structuring Engine (`app/processing/structuring_lib`)
- **Purpose:** Analyze raw manuscripts and apply strict styling rules.
- **Core Logic:**
    - `doc_utils.py`: Low-level DOCX manipulation.
    - `styler.py`: Applies styles based on regex rules.
    - `rules_loader.py`: Loads styling rules from `rules.yaml`.
- **Review Interface:** `structuring_review.html` allows users to review and modify styles before finalizing.

### 3.4 Collabora Integration (WOPI)
- **Protocol:** Uses the Web Application Open Platform Interface (WOPI) protocol.
- **Endpoints:** `app/routers/wopi.py` implements:
    - `CheckFileInfo`: Returns metadata and permissions.
    - `GetFile`: Serves the file content.
    - `PutFile`: Receives updated content from Collabora.
- **UI:** Embedded via `<iframe>` in `editor.html` and `structuring_review.html`.

---

## 4. Setup Instructions

### 4.1 Prerequisites
- Python 3.10+
- Docker (for Collabora)
- Git

### 4.2 Backend Setup
1. **Clone Repository:**
   ```bash
   git clone <repo_url>
   cd cms_backend
   ```
2. **Virtual Environment:**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate  # Windows
   source .venv/bin/activate # Linux/Mac
   ```
3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Run Server:**
   ```bash
   python -m uvicorn app.main:app --reload --port 8000
   ```
   Access at `http://127.0.0.1:8000`.

### 4.3 Collabora (LibreOffice Online) Setup
Collabora is required for in-browser editing.

**Run in Docker:**
```bash
docker run -t -d -p 9980:9980 \
  -e "aliasgroup1=http://host.docker.internal:8000,http://127.0.0.1:8000,http://localhost:8000" \
  -e "extra_params=--o:ssl.enable=false --o:net.post_allow.host[0]=.*" \
  --name collabora \
  collabora/code
```

**Note on SSL:** The command above disables SSL for easier local development. For production, configuring SSL/HTTPS is recommended.

**Environment Variables (Optional overrides):**
- `COLLABORA_URL`: URL of the Collabora container (default: `http://127.0.0.1:9980`)
- `WOPI_BASE_URL`: URL backend uses to reach itself (default: `http://host.docker.internal:8000`)

---

## 5. Development Workflow

### Adding a New Route
1. Create route handler in `app/routers/`.
2. Register router in `app/main.py`.

### Database Migrations
Currently using `Base.metadata.create_all(bind=engine)` in `main.py` for auto-schema creation. For production, consider using Alembic.

### Customizing Styles
Edit `app/processing/structuring_lib/rules.yaml` to define new regex patterns and their corresponding Word styles.

---

## 6. Troubleshooting

**Collabora "Refused to connect":**
- Ensure Docker container is running (`docker ps`).
- Check if `COLLABORA_URL` matches the container's port.
- If using `http`, ensure `ssl.enable=false` is set in the docker command.

**File Upload Errors:**
- Check permissions on the `uploads/` directory.
- Ensure allowed file extensions are configured.

**Database Locked (SQLite):**
- Occurs with high concurrency. Switch to PostgreSQL for production environments.
