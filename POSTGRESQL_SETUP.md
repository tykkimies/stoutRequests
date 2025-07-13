# PostgreSQL Database Setup for Stout Requests

This guide will help you set up PostgreSQL for Stout Requests on various platforms.

## Quick Setup Commands

### Ubuntu/Debian
```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql
```

### CentOS/RHEL/Fedora
```bash
# Install PostgreSQL
sudo dnf install postgresql postgresql-server postgresql-contrib
# or for older versions: sudo yum install postgresql postgresql-server postgresql-contrib

# Initialize database
sudo postgresql-setup initdb

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql
```

### macOS (using Homebrew)
```bash
# Install PostgreSQL
brew install postgresql

# Start PostgreSQL service
brew services start postgresql

# Create database and user
psql postgres
```

### Windows
1. Download PostgreSQL installer from https://www.postgresql.org/download/windows/
2. Run the installer and follow the setup wizard
3. Remember the password you set for the `postgres` user
4. Open pgAdmin or use Command Prompt with `psql`

## Database Configuration

Once PostgreSQL is installed and running, create the database and user:

### Method 1: Using psql command line

```sql
-- Connect to PostgreSQL as postgres user
-- Ubuntu/Debian/CentOS: sudo -u postgres psql
-- macOS/Windows: psql postgres

-- Create database
CREATE DATABASE stout_requests;

-- Create user with password
CREATE USER stout WITH PASSWORD 'Yyxd7fku!';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE stout_requests TO stout;

-- Connect to the new database
\c stout_requests

-- Grant schema permissions (PostgreSQL 15+)
GRANT ALL ON SCHEMA public TO stout;
GRANT ALL ON ALL TABLES IN SCHEMA public TO stout;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO stout;

-- Exit psql
\q
```

### Method 2: Using pgAdmin (GUI)

1. Open pgAdmin in your web browser
2. Connect to your PostgreSQL server
3. Right-click on "Databases" → Create → Database
4. Name: `stout_requests`
5. Right-click on "Login/Group Roles" → Create → Login/Group Role
6. Name: `stout`, Password: `your_secure_password_here`
7. Go to Privileges tab, check "Can login?"
8. Go to the `stout_requests` database → Right-click → Properties → Security
9. Add `stout` user with all privileges

## Environment Configuration

Update your `.env` file with the database connection details:

```env
# Database Configuration
DATABASE_URL=postgresql://stout:your_secure_password_here@localhost:5432/stout_requests

# For local development, you can also use:
# DATABASE_URL=postgresql://stout:your_secure_password_here@localhost/stout_requests
```

### Connection String Format
```
postgresql://[username]:[password]@[host]:[port]/[database_name]
```

**Components:**
- `username`: Database user (e.g., `stout`)
- `password`: User password
- `host`: Database server (usually `localhost` for local setup)
- `port`: PostgreSQL port (default is `5432`)
- `database_name`: Database name (e.g., `stout_requests`)

## Testing the Connection

Use the provided test script to verify your database setup:

```bash
# Make sure you're in the project directory
cd /path/to/stout-requests

# Activate virtual environment
source venv/bin/activate

# Test database connection
python test_db.py
```

## Troubleshooting

### Connection Issues

**Error: `psql: FATAL: role "postgres" does not exist`**
```bash
# Create postgres superuser
sudo -u postgres createuser --superuser $USER
```

**Error: `psql: FATAL: database "postgres" does not exist`**
```bash
# Create postgres database
sudo -u postgres createdb postgres
```

**Error: `FATAL: Peer authentication failed for user "stout"`**

Edit PostgreSQL configuration:
```bash
# Find pg_hba.conf location
sudo -u postgres psql -c "SHOW hba_file;"

# Edit the file (example path)
sudo nano /etc/postgresql/14/main/pg_hba.conf

# Change this line:
local   all             all                                     peer
# To this:
local   all             all                                     md5

# Restart PostgreSQL
sudo systemctl restart postgresql
```

**Error: `FATAL: password authentication failed for user "stout"`**
- Double-check the password in your `.env` file
- Ensure the user was created with the correct password
- Try resetting the password: `ALTER USER stout PASSWORD 'new_password';`

### Permission Issues

**Error: `permission denied for schema public`**
```sql
-- Connect as postgres user and run:
GRANT ALL ON SCHEMA public TO stout;
GRANT ALL ON ALL TABLES IN SCHEMA public TO stout;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO stout;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO stout;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO stout;
```

### Service Issues

**PostgreSQL not starting:**
```bash
# Check status
sudo systemctl status postgresql

# Check logs
sudo journalctl -u postgresql

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*.log
```

## Production Considerations

### Security
- Use a strong, unique password for the database user
- Consider using connection pooling for high-traffic deployments
- Restrict database access to localhost if possible
- Regular database backups

### Performance
- Configure `shared_buffers` and `work_mem` for your server specs
- Enable query logging for optimization
- Set up connection pooling with pgbouncer for high-traffic sites

### Backup
```bash
# Create backup
pg_dump -U stout -h localhost stout_requests > backup.sql

# Restore backup
psql -U stout -h localhost stout_requests < backup.sql
```

## Docker Alternative (Optional)

If you prefer Docker for local development:

```bash
# Run PostgreSQL in Docker
docker run --name stout-postgres \
  -e POSTGRES_USER=stout \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=stout_requests \
  -p 5432:5432 \
  -d postgres:15

# Connection string for Docker:
# DATABASE_URL=postgresql://stout:your_password@localhost:5432/stout_requests
```

## Next Steps

After setting up PostgreSQL:

1. ✅ Database is running and accessible
2. ✅ User and database created with proper permissions
3. ✅ `.env` file updated with correct DATABASE_URL
4. ✅ Test connection with `python test_db.py`
5. 🚀 **Run the application**: `python run.py`
6. 🌐 **Visit**: `http://localhost:8000` (will redirect to setup wizard)

The first time you visit the application, you'll be guided through the setup wizard to configure your Plex server and API keys securely through the web interface.