# 📦 CuePlex Installation Guide

This guide covers different ways to install CuePlex, from beginner-friendly one-click setups to advanced manual installations.

## 🚀 Quick Install Options

### Option 1: One-Click Docker Setup (Recommended)

**For most users - includes everything automatically:**

```bash
curl -fsSL https://raw.githubusercontent.com/your-repo/cueplex/main/quick-setup.sh | bash
```

This automatically:
- Downloads and starts CuePlex with Docker
- Sets up PostgreSQL database
- Configures all dependencies
- Starts the service on `http://localhost:8001`

### Option 2: Full Installation Script

**With OS detection and dependency installation:**

```bash
curl -fsSL https://raw.githubusercontent.com/your-repo/cueplex/main/install.sh | bash
```

This provides:
- OS-specific dependency installation
- Choice between Docker and native installation
- Automatic PostgreSQL setup
- System service configuration

## 🐳 Docker Installation (Detailed)

### Prerequisites
- Docker and Docker Compose installed
- 2GB+ available disk space
- Ports 8001, 5432 available

### Step 1: Download Configuration

```bash
# Create project directory
mkdir ~/cueplex && cd ~/cueplex

# Download docker-compose.yml
wget https://raw.githubusercontent.com/your-repo/cueplex/main/docker-compose.yml
```

### Step 2: Start Services

```bash
# Start all services in background
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f cueplex
```

### Step 3: Access CuePlex

Open `http://localhost:8001` in your browser and follow the setup wizard.

### Docker Management Commands

```bash
# Stop services
docker compose down

# Update to latest version
docker compose pull && docker compose up -d

# View logs
docker compose logs -f

# Restart services
docker compose restart

# Complete reset (removes data!)
docker compose down -v
```

## 🔧 Manual Installation

**For advanced users or custom deployments:**

### Prerequisites

- **Python 3.9+** 
- **PostgreSQL 13+**
- **Redis** (optional, for caching)
- **Git**

### Step 1: Install System Dependencies

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv postgresql postgresql-contrib redis-server git
```

#### CentOS/RHEL/Fedora
```bash
sudo dnf install python3 python3-pip postgresql-server postgresql-contrib redis git
sudo postgresql-setup initdb  # CentOS/RHEL only
```

#### macOS
```bash
brew install python3 postgresql redis git
```

### Step 2: Setup Database

```bash
# Start PostgreSQL
sudo systemctl start postgresql  # Linux
brew services start postgresql   # macOS

# Create database and user
sudo -u postgres psql
```

```sql
CREATE DATABASE cueplex;
CREATE USER cueplex_user WITH PASSWORD 'CuePlexSecure2024!';
GRANT ALL PRIVILEGES ON DATABASE cueplex TO cueplex_user;
\c cueplex
GRANT ALL ON SCHEMA public TO cueplex_user;
\q
```

### Step 3: Install CuePlex

```bash
# Clone repository
git clone https://github.com/your-repo/cueplex.git
cd cueplex

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your database settings
```

### Step 4: Initialize Database

```bash
# Run database migrations
python -c "from app.core.database import create_db_and_tables; create_db_and_tables()"
```

### Step 5: Start Application

```bash
# Development
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Production with Gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8001
```

### Step 6: Setup System Service (Optional)

```bash
# Create systemd service file
sudo nano /etc/systemd/system/cueplex.service
```

```ini
[Unit]
Description=CuePlex Media Request System
After=network.target postgresql.service

[Service]
Type=simple
User=cueplex
WorkingDirectory=/home/cueplex/cueplex
Environment=PATH=/home/cueplex/cueplex/venv/bin
ExecStart=/home/cueplex/cueplex/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable cueplex
sudo systemctl start cueplex
```

## 🌐 Reverse Proxy Setup

### Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Apache

```apache
<VirtualHost *:80>
    ServerName your-domain.com
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8001/
    ProxyPassReverse / http://127.0.0.1:8001/
</VirtualHost>
```

### Traefik

```yaml
version: '3.8'
services:
  cueplex:
    image: cueplex/cueplex:latest
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.cueplex.rule=Host(`cueplex.example.com`)"
      - "traefik.http.services.cueplex.loadbalancer.server.port=8001"
```

## 🔒 Security Considerations

### Change Default Passwords

1. Update database password in `.env` or docker-compose.yml
2. Set strong `SECRET_KEY` and `JWT_SECRET_KEY` in environment

### Firewall Setup

```bash
# Only allow necessary ports
sudo ufw allow 8001/tcp  # CuePlex web interface
sudo ufw deny 5432/tcp   # PostgreSQL (internal only)
```

### SSL/TLS

Use a reverse proxy (Nginx, Traefik) with SSL certificates from Let's Encrypt:

```bash
# Certbot with Nginx
sudo certbot --nginx -d your-domain.com
```

## 🐛 Troubleshooting

### Common Issues

**Port 8001 already in use:**
```bash
# Check what's using the port
sudo lsof -i :8001
# Kill the process or change CuePlex port
```

**Database connection failed:**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql
# Test connection manually
psql -h localhost -U cueplex_user -d cueplex
```

**Permission denied errors:**
```bash
# Fix file permissions
chmod +x install.sh
# Fix directory permissions
sudo chown -R $USER:$USER ~/cueplex
```

### Getting Help

- **Logs**: Check application logs for detailed error messages
- **Health Check**: Visit `/health` endpoint to check service status
- **Documentation**: See [SETUP.md](SETUP.md) for configuration details
- **Issues**: Report bugs on GitHub issues page

## 📈 Post-Installation

1. **Access**: Open `http://localhost:8001` or your domain
2. **Setup Wizard**: Follow the initial configuration prompts
3. **Plex Integration**: Connect your Plex server
4. **Media Services**: Configure Radarr/Sonarr (optional)
5. **Users**: Invite users or enable registration

## 🔄 Updates

### Docker Updates
```bash
cd ~/cueplex
docker compose pull
docker compose up -d
```

### Manual Updates
```bash
cd ~/cueplex
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart cueplex
```

---

**Need help?** Check the [troubleshooting section](#-troubleshooting) or open an issue on GitHub.