# 🐳 Docker Deployment Guide

This guide covers deploying CuePlex using Docker in production.

## 🚀 Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Download the production compose file
wget https://raw.githubusercontent.com/your-repo/cueplex/main/docker-compose.prod.yml

# Create environment file
cat > .env << EOF
DB_PASSWORD=your_secure_database_password_here
SECRET_KEY=$(openssl rand -hex 32)
EOF

# Start services
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps
```

### Option 2: Docker Run

```bash
# Create network
docker network create cueplex

# Run PostgreSQL
docker run -d \
  --name cueplex-postgres \
  --network cueplex \
  -e POSTGRES_DB=cueplex \
  -e POSTGRES_USER=cueplex_user \
  -e POSTGRES_PASSWORD=CuePlexSecure2024! \
  -v postgres_data:/var/lib/postgresql/data \
  postgres:15

# Run CuePlex
docker run -d \
  --name cueplex-app \
  --network plexapps \
  -p 8001:8001 \
  -e DATABASE_URL=postgresql://cueplex_user:CuePlexSecure2024!@cueplex-postgres:5432/cueplex \
  -v cueplex_logs:/app/logs \
  -v cueplex_data:/app/data \
  cueplex/cueplex:latest
```

## 🏗️ Building Your Own Image

### Local Build

```bash
# Single architecture
./build-docker.sh v1.0.0

# Multi-architecture (requires buildx)
./build-multi-arch.sh v1.0.0
```

### Custom Build

```bash
# Clone repository
git clone https://github.com/your-repo/cueplex.git
cd cueplex

# Build image
docker build -t your-registry/cueplex:custom .

# Push to your registry
docker push your-registry/cueplex:custom
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `SECRET_KEY` | JWT signing key | Random (generated) |
| `ENVIRONMENT` | App environment | `production` |

### Docker Compose Environment

Create `.env` file:

```env
# Database
DB_PASSWORD=your_secure_password_here

# Application
SECRET_KEY=your_32_character_secret_key_here

# Optional: Reverse proxy
# BASE_URL=/cueplex
```

## 🔧 Production Configuration

### Reverse Proxy Setup

#### Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Traefik

```yaml
version: '3.8'
services:
  cueplex:
    image: cueplex/cueplex:latest
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.cueplex.rule=Host(`cueplex.example.com`)"
      - "traefik.http.routers.cueplex.tls=true"
      - "traefik.http.routers.cueplex.tls.certresolver=letsencrypt"
      - "traefik.http.services.cueplex.loadbalancer.server.port=8001"
```

### SSL/HTTPS

Use a reverse proxy with SSL termination:

```bash
# Certbot with Nginx
sudo certbot --nginx -d your-domain.com

# Or use Traefik with Let's Encrypt
```

### Resource Limits

```yaml
services:
  cueplex:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M
```

## 📊 Monitoring

### Health Checks

CuePlex includes built-in health checks:

```bash
# Check application health
curl http://localhost:8001/health

# Docker health status
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### Logs

```bash
# Application logs
docker-compose logs -f cueplex

# Database logs
docker-compose logs postgres

# All services
docker-compose logs -f
```

### Metrics

The application exposes metrics for monitoring:

- Health endpoint: `/health`
- Application logs in JSON format
- Database connection status

## 🔄 Updates

### Docker Compose

```bash
# Pull latest images
docker-compose pull

# Recreate containers
docker-compose up -d

# Remove old images
docker image prune
```

### Manual Update

```bash
# Stop application
docker stop cueplex-app

# Remove old container
docker rm cueplex-app

# Pull latest image
docker pull cueplex/cueplex:latest

# Start new container
docker run -d \
  --name cueplex-app \
  --network cueplex \
  -p 8001:8001 \
  -e DATABASE_URL=your_database_url \
  -v cueplex_logs:/app/logs \
  -v cueplex_data:/app/data \
  cueplex/cueplex:latest
```

## 💾 Backup

### Database Backup

```bash
# Create backup
docker exec cueplex-postgres pg_dump -U cueplex_user -d cueplex > cueplex-backup.sql

# Restore backup
docker exec -i cueplex-postgres psql -U cueplex_user -d cueplex < cueplex-backup.sql
```

### Volume Backup

```bash
# Backup application data
docker run --rm -v cueplex_data:/data -v $(pwd):/backup alpine tar czf /backup/cueplex-data-backup.tar.gz -C /data .

# Restore application data
docker run --rm -v cueplex_data:/data -v $(pwd):/backup alpine tar xzf /backup/cueplex-data-backup.tar.gz -C /data
```

## 🐛 Troubleshooting

### Common Issues

**Container won't start:**
```bash
# Check logs
docker logs cueplex-app

# Check database connection
docker exec cueplex-app curl -f http://localhost:8001/health
```

**Database connection failed:**
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Test database connection
docker exec cueplex-postgres psql -U cueplex_user -d cueplex -c "SELECT version();"
```

**Permission errors:**
```bash
# Fix volume permissions
docker exec -u root cueplex-app chown -R cueplex:cueplex /app/logs /app/data
```

### Performance Tuning

**Increase workers:**
```yaml
services:
  cueplex:
    command: ["gunicorn", "app.main:app", "-w", "8", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8001"]
```

**Database tuning:**
```yaml
services:
  postgres:
    command: postgres -c shared_buffers=256MB -c max_connections=200
```

## 🔐 Security

### Best Practices

1. **Change default passwords**
2. **Use strong SECRET_KEY**
3. **Run behind reverse proxy with SSL**
4. **Keep images updated**
5. **Limit exposed ports**
6. **Use Docker secrets for sensitive data**

### Docker Secrets

```yaml
services:
  cueplex:
    secrets:
      - db_password
    environment:
      - DATABASE_URL=postgresql://cueplex_user@postgres:5432/cueplex
    
secrets:
  db_password:
    file: ./db_password.txt
```

---

## 📞 Support

- **Documentation**: [Installation Guide](INSTALLATION.md)
- **Health Check**: http://your-domain:8001/health  
- **Logs**: `docker-compose logs cueplex`
- **Issues**: GitHub Issues