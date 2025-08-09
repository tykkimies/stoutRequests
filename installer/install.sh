#!/bin/bash

# CuePlex Auto-Installer
# Automatically deploys CuePlex stack with PostgreSQL

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${CYAN}"
    echo "🎬 CuePlex Auto-Installer"
    echo "========================="
    echo -e "${NC}"
}

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

# Configuration
CUEPLEX_IMAGE=${CUEPLEX_IMAGE:-"cueplex-test:latest"}
CUEPLEX_VERSION=${CUEPLEX_VERSION:-"latest"}
INSTALL_DIR=${DATA_PATH:-"/opt/cueplex"}
STACK_NAME="cueplex"
NETWORK_NAME=${CUEPLEX_NETWORK:-"cueplex"}

print_header

# Check if Docker is available
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running or accessible"
    print_status "Make sure Docker is installed and the daemon is running"
    exit 1
fi

print_success "Docker is available"

# Check if running with Docker socket mounted
if [[ ! -S /var/run/docker.sock ]]; then
    print_error "Docker socket not mounted"
    print_status "Run with: docker run -v /var/run/docker.sock:/var/run/docker.sock ..."
    exit 1
fi

print_success "Docker socket is mounted"

# Create installation directory
print_status "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Generate secure credentials
print_status "Generating secure credentials..."
DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
SECRET_KEY=$(openssl rand -hex 32)

print_success "Credentials generated"

# Create environment file
print_status "Creating environment configuration..."
cat > .env << EOF
# CuePlex Configuration - Generated $(date)
DB_PASSWORD=$DB_PASSWORD
SECRET_KEY=$SECRET_KEY

# Network Configuration
CUEPLEX_PORT=${CUEPLEX_PORT:-8001}
CUEPLEX_NETWORK=$NETWORK_NAME

# Optional: Configure these after installation
# PLEX_URL=http://your-plex-server:32400
# RADARR_URL=http://radarr:7878
# SONARR_URL=http://sonarr:8989
EOF

print_success "Environment file created"

# Create docker-compose.yml with direct substitution
print_status "Creating Docker Compose configuration..."
cat > docker-compose.yml << EOF
# Docker Compose file for CuePlex - Generated $(date)

services:
  cueplex:
    image: $CUEPLEX_IMAGE
    container_name: cueplex-app
    restart: unless-stopped
    ports:
      - "${CUEPLEX_PORT:-8001}:8001"
    environment:
      - DATABASE_URL=postgresql://cueplex_user:$DB_PASSWORD@postgres:5432/cueplex
      - SECRET_KEY=$SECRET_KEY
      - ENVIRONMENT=production
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - cueplex_data:/app/data
      - cueplex_logs:/app/logs
    networks:
      - plexapps

  postgres:
    image: postgres:15
    container_name: cueplex-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=cueplex
      - POSTGRES_USER=cueplex_user
      - POSTGRES_PASSWORD=$DB_PASSWORD
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init-db.sql:ro
    networks:
      - plexapps
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cueplex_user -d cueplex"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

volumes:
  postgres_data:
    driver: local
  cueplex_data:
    driver: local
  cueplex_logs:
    driver: local

networks:
  plexapps:
    external: true
EOF

# Copy init script
cp /installer/templates/init-db.sql ./

print_success "Configuration files created"

# Network setup - ensure plexapps network exists
print_status "Checking for plexapps network..."
if ! docker network inspect plexapps >/dev/null 2>&1; then
    print_error "plexapps network not found!"
    print_status "Creating plexapps network..."
    docker network create plexapps
    print_success "plexapps network created"
else
    print_success "plexapps network exists - will join containers to it"
fi

# Check if local image exists, otherwise pull
print_status "Checking for CuePlex image..."
if docker image inspect "$CUEPLEX_IMAGE" >/dev/null 2>&1; then
    print_success "Using local image: $CUEPLEX_IMAGE"
else
    print_status "Pulling Docker images..."
    if ! docker compose pull; then
        print_error "Failed to pull images"
        print_status "Make sure the image exists or build it locally:"
        print_status "docker build -t $CUEPLEX_IMAGE ."
        exit 1
    fi
fi

# Start the stack
print_status "Starting CuePlex stack..."
docker compose up -d

# Wait for services to be ready
print_status "Waiting for services to start..."
sleep 15

# Check if CuePlex is running
if docker compose ps | grep -q "cueplex.*running"; then
    print_success "CuePlex stack is running!"
    echo
    echo "🎉 Installation Complete!"
    echo "========================"
    echo -e "• Web Interface: ${GREEN}http://localhost:${CUEPLEX_PORT:-8001}${NC}"
    echo -e "• Installation Directory: ${CYAN}$INSTALL_DIR${NC}"
    echo -e "• Database: ${YELLOW}PostgreSQL (auto-configured)${NC}"
    echo
    echo "Management Commands:"
    echo "  cd $INSTALL_DIR"
    echo "  docker compose logs -f    # View logs"
    echo "  docker compose stop       # Stop services"
    echo "  docker compose start      # Start services"
    echo "  docker compose down       # Remove containers"
    echo
    echo "Next Steps:"
    echo "1. Open the web interface and complete setup"
    echo "2. Configure Plex server connection"
    echo "3. Add Radarr/Sonarr integration (optional)"
    echo
else
    print_error "Installation failed"
    print_status "Check logs with: cd $INSTALL_DIR && docker compose logs"
    exit 1
fi