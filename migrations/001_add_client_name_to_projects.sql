-- Migration: Add client_name column to projects table
-- Date: 2026-01-16
-- Description: Adds an optional client_name field to store the client/publisher name

-- Add the client_name column to the projects table
ALTER TABLE projects ADD COLUMN client_name VARCHAR;

-- Optional: Add a comment to the column
COMMENT ON COLUMN projects.client_name IS 'Client or publisher organization name';
