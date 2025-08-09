# 🚀 CuePlex Auto-Installer

One-command deployment of the complete CuePlex stack!

## ✨ What It Does

The CuePlex Auto-Installer:
- ✅ **Deploys complete stack** (CuePlex + PostgreSQL + networking)
- ✅ **Generates secure credentials** automatically
- ✅ **Configures everything** for immediate use
- ✅ **No manual setup** required
- ✅ **Production-ready** configuration

## 🎯 Quick Start

### Option 1: One-Command Install

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  cueplex/installer:latest
```

That's it! CuePlex will be running at `http://localhost:8001`

### Option 2: Custom Configuration

```bash
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e CUEPLEX_PORT=8080 \
  -e DATA_PATH=/opt/cueplex \
  -e CUEPLEX_NETWORK=media \
  cueplex/installer:latest
```

## ⚙️ Configuration Options

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `CUEPLEX_PORT` | `8001` | Port to expose CuePlex on |
| `DATA_PATH` | `/opt/cueplex` | Installation directory |
| `CUEPLEX_NETWORK` | `cueplex` | Docker network name |
| `CUEPLEX_VERSION` | `latest` | CuePlex version to install |

## 🔧 Post-Installation

After installation, manage your CuePlex instance:

```bash
# Navigate to installation directory
cd /opt/cueplex

# View status
docker compose ps

# View logs
docker compose logs -f

# Stop services
docker compose stop

# Start services
docker compose start

# Update to latest version
docker compose pull && docker compose up -d
```

## 🌐 Integration with Existing Services

### Connect to Existing Radarr/Sonarr

1. **Find your media network:**
   ```bash
   docker network ls
   ```

2. **Join CuePlex to that network:**
   ```bash
   cd /opt/cueplex
   # Edit docker-compose.yml and add your network
   docker compose up -d
   ```

3. **Use container names in CuePlex setup:**
   - Radarr: `http://radarr:7878`
   - Sonarr: `http://sonarr:8989`

### Reverse Proxy Setup

For Nginx/Apache/Traefik integration:

```bash
# CuePlex runs on localhost:8001
# Proxy /cueplex -> http://localhost:8001
```

## 📁 File Structure

After installation:

```
/opt/cueplex/
├── docker-compose.yml  # Stack configuration
├── .env               # Environment variables
├── init-db.sql        # Database initialization
└── management scripts
```

## 🔄 Management Commands

### Using Docker Compose

```bash
cd /opt/cueplex

# Basic operations
docker compose ps          # Status
docker compose logs -f     # Logs
docker compose stop        # Stop
docker compose start       # Start
docker compose restart     # Restart

# Maintenance
docker compose pull        # Update images
docker compose down        # Remove containers
docker compose down -v     # Remove everything
```

### Backup Data

```bash
# Backup application data
docker run --rm \
  -v cueplex_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/cueplex-backup.tar.gz -C /data .

# Backup database
docker exec cueplex-postgres pg_dump \
  -U cueplex_user cueplex > cueplex-db-backup.sql
```

## 🐛 Troubleshooting

### Installation Fails

```bash
# Check Docker is running
docker info

# Check permissions
docker run hello-world

# View installer logs
docker logs <installer-container-id>
```

### Services Won't Start

```bash
cd /opt/cueplex

# Check service status
docker compose ps

# View logs
docker compose logs

# Check network
docker network ls
```

### Can't Access Web Interface

1. **Check port binding:**
   ```bash
   docker compose ps
   # Should show: 0.0.0.0:8001->8001/tcp
   ```

2. **Check firewall:**
   ```bash
   # Test locally
   curl http://localhost:8001/health
   ```

3. **Check container logs:**
   ```bash
   docker compose logs cueplex
   ```

## 🔐 Security Notes

- **Generated passwords** are stored in `.env` file
- **Database** is isolated in Docker network
- **No default accounts** - secure by default
- **Regular updates** recommended

## 🏗️ Building the Installer

To build your own installer image:

```bash
# Clone repository
git clone https://github.com/your-repo/cueplex.git
cd cueplex

# Build installer
./build-installer.sh

# Test locally
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  cueplex/installer:latest
```

## 💡 Advanced Usage

### Custom Docker Compose

1. **Run installer to generate base files**
2. **Modify `/opt/cueplex/docker-compose.yml`** as needed
3. **Redeploy:** `docker compose up -d`

### Integration Examples

```yaml
# Add to existing docker-compose.yml
version: '3.8'
services:
  cueplex:
    image: cueplex/cueplex:latest
    # ... configuration from installer
    networks:
      - default
      - servarr  # Your existing network

networks:
  servarr:
    external: true
```

---

## 📞 Support

- **Quick Setup**: Use the auto-installer
- **Documentation**: [Installation Guide](INSTALLATION.md)
- **Issues**: GitHub Issues
- **Health Check**: `http://localhost:8001/health`