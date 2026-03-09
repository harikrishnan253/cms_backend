-- FILES
CREATE TABLE files (
    id SERIAL PRIMARY KEY,
    project_id INT REFERENCES projects(id),
    path TEXT NOT NULL,
    file_type TEXT,
    version INT DEFAULT 1,
    locked BOOLEAN DEFAULT FALSE,
    uploaded_by INT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AUDIT LOGS
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    action TEXT,
    entity TEXT,
    entity_id INT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);