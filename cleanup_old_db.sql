-- Cleanup script to remove old database and user
-- Run as: sudo -u postgres psql -f cleanup_old_db.sql

-- First disconnect all connections to the old database
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'stout_requests';

-- Drop the old database
DROP DATABASE IF EXISTS stout_requests;

-- Drop the old user
DROP USER IF EXISTS stout;

-- Show confirmation
SELECT 'Old database and user removed successfully' as status;