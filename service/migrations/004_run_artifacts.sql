DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = 4) THEN
        ALTER TABLE artifact_files DROP CONSTRAINT artifact_files_pkey;
        ALTER TABLE artifact_files ADD PRIMARY KEY (run_id, artifact_id);
    END IF;
END $$;

INSERT INTO schema_migrations(version) VALUES (4) ON CONFLICT DO NOTHING;
