CREATE TABLE IF NOT EXISTS request_budget (
    bucket timestamptz PRIMARY KEY,
    used integer NOT NULL CHECK (used > 0)
);
INSERT INTO schema_migrations(version) VALUES (5) ON CONFLICT DO NOTHING;
