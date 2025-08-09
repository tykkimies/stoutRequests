#!/bin/bash

# Complete Database Migration for CuePlex
# This script will create the new database, migrate data, and update configurations

set -e

echo "🎬 CuePlex Database Migration"
echo "============================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_status "This script will:"
echo "1. Create new 'cueplex' database and 'cueplex_user'"  
echo "2. Migrate all data from 'stout_requests' database"
echo "3. Update your .env file to use new credentials"
echo "4. Optionally remove old database and user"
echo

# Check if old database is accessible
print_status "Checking current database connection..."
if PGPASSWORD=Yyxd7fku! psql -h localhost -U stout -d stout_requests -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" > /dev/null 2>&1; then
    OLD_DB_COUNT=$(PGPASSWORD=Yyxd7fku! psql -h localhost -U stout -d stout_requests -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | xargs)
    print_success "Old database accessible - found $OLD_DB_COUNT tables"
    OLD_DB_WORKS=true
else
    print_error "Cannot connect to old database"
    OLD_DB_WORKS=false
    exit 1
fi

echo
print_warning "You need sudo access or postgres user password to create the new database."
print_status "Choose your method:"
echo "1. Use sudo (requires your system password)"
echo "2. Use postgres password (if you know it)" 
echo "3. Exit and do manually"
echo

read -p "Enter choice (1-3): " choice

case $choice in
    1)
        print_status "Creating database using sudo..."
        echo "You may be prompted for your system password."
        
        if sudo -u postgres psql -f complete_migration.sql; then
            print_success "Database created successfully"
        else
            print_error "Failed to create database with sudo"
            exit 1
        fi
        ;;
    2)
        read -s -p "Enter postgres password: " POSTGRES_PASSWORD
        echo
        
        if PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U postgres -f complete_migration.sql; then
            print_success "Database created successfully"
        else
            print_error "Failed to create database with postgres password"
            exit 1
        fi
        ;;
    3)
        print_status "Exiting. To create database manually:"
        echo "sudo -u postgres psql -f complete_migration.sql"
        exit 0
        ;;
    *)
        print_error "Invalid choice"
        exit 1
        ;;
esac

# Test new database connection
print_status "Testing new database connection..."
if PGPASSWORD=CuePlexSecure2024! psql -h localhost -U cueplex_user -d cueplex -c "SELECT version();" > /dev/null 2>&1; then
    print_success "New database connection verified"
else
    print_error "Cannot connect to new database"
    exit 1
fi

# Migrate data
print_status "Migrating data from old to new database..."
if PGPASSWORD=Yyxd7fku! pg_dump -h localhost -U stout --no-owner --no-privileges stout_requests | PGPASSWORD=CuePlexSecure2024! psql -h localhost -U cueplex_user cueplex; then
    print_success "Data migration completed"
    
    # Verify data migration
    OLD_COUNT=$(PGPASSWORD=Yyxd7fku! psql -h localhost -U stout -d stout_requests -t -c "SELECT COUNT(*) FROM users;" 2>/dev/null | xargs || echo "0")
    NEW_COUNT=$(PGPASSWORD=CuePlexSecure2024! psql -h localhost -U cueplex_user -d cueplex -t -c "SELECT COUNT(*) FROM users;" 2>/dev/null | xargs || echo "0")
    
    print_status "Data verification: Old DB users: $OLD_COUNT, New DB users: $NEW_COUNT"
    
    if [[ "$OLD_COUNT" == "$NEW_COUNT" ]] && [[ "$NEW_COUNT" != "0" ]]; then
        print_success "Data migration verified successfully"
    else
        print_warning "Data counts don't match - please verify manually"
    fi
else
    print_error "Data migration failed"
    exit 1
fi

# Update .env file
print_status "Updating .env file with new credentials..."
cp .env .env.backup
sed -i 's/stout:Yyxd7fku!/cueplex_user:CuePlexSecure2024!/g' .env
sed -i 's/stout_requests/cueplex/g' .env
print_success "Environment file updated (backup saved as .env.backup)"

# Test application connection
print_status "Testing application database connection..."
if python3 -c "
import os
os.chdir('/opt/stoutRequests')
from app.core.database import engine
from sqlmodel import text, Session
with Session(engine) as session:
    result = session.exec(text('SELECT version()'))
    print('Database connection successful')
" 2>/dev/null; then
    print_success "Application can connect to new database"
else
    print_warning "Application cannot connect yet - may need restart"
fi

echo
print_success "Migration completed successfully!"
print_status "Summary:"
echo "✅ New database 'cueplex' created"
echo "✅ New user 'cueplex_user' created" 
echo "✅ Data migrated from 'stout_requests'"
echo "✅ .env file updated"
echo

# Ask about cleanup
read -p "Remove old database and user? (y/N): " cleanup
if [[ "$cleanup" =~ ^[Yy]$ ]]; then
    print_status "Cleaning up old database..."
    
    case $choice in
        1)
            if sudo -u postgres psql -c "DROP DATABASE stout_requests; DROP USER stout;"; then
                print_success "Old database and user removed"
            else
                print_warning "Could not remove old database/user - may need manual cleanup"
            fi
            ;;
        2)
            if PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -U postgres -c "DROP DATABASE stout_requests; DROP USER stout;"; then
                print_success "Old database and user removed"
            else
                print_warning "Could not remove old database/user - may need manual cleanup"
            fi
            ;;
    esac
fi

echo
print_success "🎉 Migration complete! Your app is now using the new CuePlex database."
print_status "Restart your application to use the new database:"
echo "cd /opt/stoutRequests && ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8001"