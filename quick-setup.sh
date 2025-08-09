#!/bin/bash

# Quick CuePlex Setup Script
# Downloads and starts CuePlex with Docker in one command

set -e

echo "🎬 Quick CuePlex Setup"
echo "====================="

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed."
    echo "Please install Docker first, or use the full installer: curl -fsSL https://get.cueplex.com | bash"
    exit 1
fi

# Create project directory
SETUP_DIR="$HOME/cueplex-quick"
echo "📁 Setting up in: $SETUP_DIR"
mkdir -p "$SETUP_DIR"
cd "$SETUP_DIR"

# Download docker-compose.yml
echo "📥 Downloading configuration..."
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  cueplex:
    image: cueplex/cueplex:latest
    container_name: cueplex-app
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://cueplex_user:CuePlexSecure2024!@postgres:5432/cueplex
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./logs:/app/logs
      - cueplex_data:/app/data
    restart: unless-stopped

  postgres:
    image: postgres:15
    container_name: cueplex-postgres
    environment:
      - POSTGRES_DB=cueplex
      - POSTGRES_USER=cueplex_user  
      - POSTGRES_PASSWORD=CuePlexSecure2024!
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cueplex_user -d cueplex"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  postgres_data:
  cueplex_data:
EOF

# Create .env file from template
if [[ ! -f ".env" ]]; then
    echo "📝 Creating environment configuration..."
    curl -fsSL https://raw.githubusercontent.com/your-repo/cueplex/main/env-template -o .env
    
    # Generate random SECRET_KEY
    SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | base64 | tr -d "=+/" | cut -c1-32)
    sed -i "s/CHANGE_THIS_TO_A_RANDOM_STRING_32_CHARS_MIN/$SECRET_KEY/g" .env
    echo "✅ Environment configured with secure random key"
fi

# Start services
echo "🚀 Starting CuePlex..."
if command -v docker-compose &> /dev/null; then
    docker-compose up -d
else
    docker compose up -d
fi

echo "⏳ Waiting for services to start..."
sleep 10

# Check if running
if docker ps | grep -q cueplex-app; then
    echo
    echo "✅ CuePlex is now running!"
    echo
    echo "🌐 Open: http://localhost:8001"
    echo "📁 Setup directory: $SETUP_DIR"
    echo
    echo "Management commands:"
    echo "  Stop:    cd $SETUP_DIR && docker compose down"
    echo "  Restart: cd $SETUP_DIR && docker compose restart"
    echo "  Logs:    cd $SETUP_DIR && docker compose logs -f"
    echo
else
    echo "❌ Something went wrong. Check logs: docker compose logs"
    exit 1
fi