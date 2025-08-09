-- Initialize CuePlex database
-- This script runs automatically when the PostgreSQL container starts

-- Ensure the database and user exist (Docker already creates them)
-- but set up any additional permissions or initial data

-- Grant all privileges on schema
GRANT ALL ON SCHEMA public TO cueplex_user;
GRANT ALL ON ALL TABLES IN SCHEMA public TO cueplex_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO cueplex_user;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO cueplex_user;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cueplex_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cueplex_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO cueplex_user;