CREATE TABLE IF NOT EXISTS artifact_files (
    artifact_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES runs(id),
    relative_path text NOT NULL,
    UNIQUE (run_id, relative_path)
);

INSERT INTO schema_migrations(version) VALUES (3) ON CONFLICT DO NOTHING;
