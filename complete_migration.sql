-- Complete Database Migration Script
-- Run this as postgres superuser: sudo -u postgres psql -f complete_migration.sql

-- Create new database
CREATE DATABASE cueplex;

-- Create new user with password
CREATE USER cueplex_user WITH PASSWORD 'CuePlexSecure2024!';

-- Grant privileges on the new database
GRANT ALL PRIVILEGES ON DATABASE cueplex TO cueplex_user;

-- Connect to the new database
\c cueplex

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO cueplex_user;
GRANT ALL ON ALL TABLES IN SCHEMA public TO cueplex_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO cueplex_user;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO cueplex_user;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cueplex_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cueplex_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO cueplex_user;

-- Show confirmation
SELECT 'New database and user created successfully' as status;