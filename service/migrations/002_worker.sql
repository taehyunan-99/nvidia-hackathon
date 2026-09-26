ALTER TABLE runs ADD COLUMN IF NOT EXISTS lease_owner text;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS lease_until timestamptz;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS cleaned_at timestamptz;

INSERT INTO schema_migrations(version) VALUES (2) ON CONFLICT DO NOTHING;
