#!/bin/bash

# Database Migration Script
# Migrates from stout/stout_requests to cueplex_user/cueplex

echo "🔄 CuePlex Database Migration"
echo "============================="

# Check if old database is accessible
echo "📋 Checking current database..."
if PGPASSWORD=Yyxd7fku! psql -h localhost -U stout -d stout_requests -c "SELECT count(*) FROM users;" > /dev/null 2>&1; then
    echo "✅ Old database (stout_requests) is accessible"
    OLD_DB_WORKS=true
else
    echo "❌ Old database is not accessible"
    OLD_DB_WORKS=false
fi

# Ask for postgres password
echo ""
echo "To create the new database, we need the postgres superuser password."
echo "If you don't know it, you can:"
echo "1. Reset it: sudo -u postgres psql -c \"ALTER USER postgres PASSWORD 'newpassword';\""
echo "2. Or temporarily revert to old database credentials"
echo ""

read -s -p "Enter postgres password (or press Enter to skip): " POSTGRES_PASSWORD
echo ""

if [[ -z "$POSTGRES_PASSWORD" ]]; then
    echo "⚠️  Skipping database migration"
    echo "   Option 1: Revert .env to old credentials temporarily"
    echo "   Option 2: Create database manually later"
    
    echo ""
    echo "Reverting .env to old credentials..."
    sed -i 's/cueplex_user:CuePlexSecure2024!/stout:Yyxd7fku!/g' /opt/stoutRequests/.env
    sed -i 's/cueplex/stout_requests/g' /opt/stoutRequests/.env
    echo "✅ .env reverted to old database credentials"
    echo "   Your app should now start successfully"
    
    exit 0
fi

# Create new database with postgres superuser
echo "🏗️  Creating new database and user..."

PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U postgres << EOF
-- Create database and user
CREATE DATABASE cueplex;
CREATE USER cueplex_user WITH PASSWORD 'CuePlexSecure2024!';
GRANT ALL PRIVILEGES ON DATABASE cueplex TO cueplex_user;

-- Connect to new database and set permissions
\c cueplex

GRANT ALL ON SCHEMA public TO cueplex_user;
GRANT ALL ON ALL TABLES IN SCHEMA public TO cueplex_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO cueplex_user;

-- Set default privileges
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cueplex_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cueplex_user;
EOF

if [[ $? -eq 0 ]]; then
    echo "✅ New database created successfully"
    
    # Test connection
    if PGPASSWORD=CuePlexSecure2024! psql -h localhost -U cueplex_user -d cueplex -c "SELECT version();" > /dev/null 2>&1; then
        echo "✅ New database connection verified"
        
        # Optionally migrate data
        if [[ "$OLD_DB_WORKS" == "true" ]]; then
            echo ""
            read -p "Migrate data from old database? (y/N): " MIGRATE_DATA
            if [[ "$MIGRATE_DATA" =~ ^[Yy]$ ]]; then
                echo "📦 Migrating data..."
                PGPASSWORD=Yyxd7fku! pg_dump -h localhost -U stout stout_requests | PGPASSWORD=CuePlexSecure2024! psql -h localhost -U cueplex_user cueplex
                
                if [[ $? -eq 0 ]]; then
                    echo "✅ Data migration completed"
                else
                    echo "⚠️  Data migration had issues - check manually"
                fi
            fi
        fi
        
        echo ""
        echo "🎉 Database migration completed!"
        echo "   New database: cueplex"
        echo "   New user: cueplex_user"
        echo "   Your .env file is already configured correctly"
        
    else
        echo "❌ Could not connect to new database"
        echo "   Reverting .env to old credentials..."
        sed -i 's/cueplex_user:CuePlexSecure2024!/stout:Yyxd7fku!/g' /opt/stoutRequests/.env
        sed -i 's/cueplex/stout_requests/g' /opt/stoutRequests/.env
        exit 1
    fi
else
    echo "❌ Database creation failed"
    echo "   Reverting .env to old credentials..."
    sed -i 's/cueplex_user:CuePlexSecure2024!/stout:Yyxd7fku!/g' /opt/stoutRequests/.env
    sed -i 's/cueplex/stout_requests/g' /opt/stoutRequests/.env
    exit 1
fi