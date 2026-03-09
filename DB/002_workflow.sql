-- PROJECTS
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    team_id INT REFERENCES teams(id),
    code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    xml_standard TEXT CHECK (xml_standard IN ('JATS', 'BITS')),
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- WORKFLOW STATES
CREATE TABLE workflow_states (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    sequence INT NOT NULL
);

-- WORKFLOW TRANSITIONS
CREATE TABLE workflow_transitions (
    from_state INT REFERENCES workflow_states(id),
    to_state INT REFERENCES workflow_states(id),
    allowed_role INT REFERENCES roles(id)
);
