-- Read-only role for db-service.
-- Run it as the owner of the database.
-- For local PostgreSQL, run: make db-load. For Supabase, run the same statements in the SQL editor
-- and change the password.
-- The file is safe to run more than once.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nl2sql_reader') THEN
        CREATE ROLE nl2sql_reader WITH LOGIN PASSWORD 'reader_pw';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE nl2sql TO nl2sql_reader;
GRANT USAGE ON SCHEMA public TO nl2sql_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO nl2sql_reader;

-- Tables created later in this schema by the same user also get SELECT.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO nl2sql_reader;

-- Every session of this role starts read-only. This is a second safety layer.
ALTER ROLE nl2sql_reader SET default_transaction_read_only = on;
