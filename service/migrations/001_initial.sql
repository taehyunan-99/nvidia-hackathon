CREATE TABLE IF NOT EXISTS schema_migrations (
    version integer PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS sessions (
    id text PRIMARY KEY,
    token_hash text NOT NULL UNIQUE,
    status text NOT NULL CHECK (status IN ('active', 'expired', 'deleting', 'deleted')),
    expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id text PRIMARY KEY,
    session_id text NOT NULL REFERENCES sessions(id),
    input_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS uploads (
    id text PRIMARY KEY,
    review_id text NOT NULL REFERENCES reviews(id),
    upload_key text NOT NULL,
    relative_path text NOT NULL,
    sha256 text NOT NULL,
    size_bytes bigint NOT NULL,
    UNIQUE (review_id, upload_key)
);

CREATE TABLE IF NOT EXISTS runs (
    id text PRIMARY KEY,
    review_id text NOT NULL REFERENCES reviews(id),
    session_id text NOT NULL REFERENCES sessions(id),
    request_key text NOT NULL,
    state_json jsonb NOT NULL,
    result_json jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, review_id, request_key)
);

INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT DO NOTHING;
