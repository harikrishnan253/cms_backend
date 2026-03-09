import os
from pathlib import Path

# Runtime root can be overridden via env. Default is /opt/cms_runtime
RUNTIME_ROOT = Path(os.getenv("CMS_RUNTIME_ROOT", "/opt/cms_runtime")).resolve()

DB_DIR = RUNTIME_ROOT / "db"
DATA_DIR = RUNTIME_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
REF_CACHE_PATH = RUNTIME_ROOT / "ref_cache.json"

def ensure_runtime_dirs() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
