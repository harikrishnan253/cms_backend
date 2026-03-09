import sqlite3
import uuid
from pathlib import Path

from flask import Flask
from sqlalchemy import inspect

from app.models.database import db, init_db


def test_init_db_adds_missing_llm_columns_and_table():
    test_dir = Path("backend/tests/.tmp_schema_compat").resolve()
    test_dir.mkdir(parents=True, exist_ok=True)
    db_path = test_dir / f"legacy_{uuid.uuid4().hex}.sqlite"

    # Simulate a pre-existing DB schema without newer LLM/token columns.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id VARCHAR(36) UNIQUE NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id VARCHAR(36) UNIQUE NOT NULL,
            batch_id INTEGER NOT NULL,
            original_filename VARCHAR(255) NOT NULL,
            input_path VARCHAR(500) NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path.as_posix()}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    init_db(app)

    with app.app_context():
        inspector = inspect(db.engine)
        job_columns = {c["name"] for c in inspector.get_columns("jobs")}
        assert "input_tokens" in job_columns
        assert "output_tokens" in job_columns
        assert "total_tokens" in job_columns
        assert "llm_latency_ms" in job_columns
        assert "llm_used" in job_columns
        assert "llm_provider" in job_columns
        assert "llm_model" in job_columns
        assert "llm_calls" in inspector.get_table_names()
