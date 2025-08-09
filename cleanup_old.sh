#!/bin/bash

# Simple cleanup script for old database

echo "🧹 Cleaning up old CuePlex database and user"
echo "============================================="

# Check if new database is working
if PGPASSWORD=CuePlexSecure2024! psql -h localhost -U cueplex_user -d cueplex -c "SELECT COUNT(*) FROM \"user\";" > /dev/null 2>&1; then
    echo "✅ New database is working"
else
    echo "❌ New database not working - STOPPING cleanup for safety"
    exit 1
fi

echo "⚠️  This will permanently remove:"
echo "   - Database: stout_requests"
echo "   - User: stout"
echo ""
read -p "Are you sure? (yes/NO): " confirm

if [[ "$confirm" != "yes" ]]; then
    echo "Cleanup cancelled"
    exit 0
fi

echo "🗑️  Removing old database and user..."

# Method 1: Try with sudo
if sudo -u postgres psql -f cleanup_old_db.sql; then
    echo "✅ Cleanup completed successfully"
elif read -s -p "Sudo failed. Enter postgres password: " POSTGRES_PASSWORD && echo; then
    # Method 2: Use postgres password
    if PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U postgres -f cleanup_old_db.sql; then
        echo "✅ Cleanup completed successfully"
    else
        echo "❌ Cleanup failed"
        echo ""
        echo "Manual cleanup commands:"
        echo "sudo -u postgres psql -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'stout_requests';\""
        echo "sudo -u postgres psql -c \"DROP DATABASE stout_requests;\""
        echo "sudo -u postgres psql -c \"DROP USER stout;\""
    fi
else
    echo "❌ Cleanup cancelled"
fi