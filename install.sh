#!/bin/bash

# CuePlex Installation Script
# This script automatically sets up CuePlex with PostgreSQL

set -e

echo "🎬 Installing CuePlex Media Request System..."
echo "============================================"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root for security reasons"
   print_status "Please run as a regular user with sudo privileges"
   exit 1
fi

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v apt &> /dev/null; then
        OS="debian"
        INSTALL_CMD="sudo apt install -y"
        UPDATE_CMD="sudo apt update"
    elif command -v dnf &> /dev/null; then
        OS="fedora"
        INSTALL_CMD="sudo dnf install -y"
        UPDATE_CMD="sudo dnf update -y"
    elif command -v yum &> /dev/null; then
        OS="centos"
        INSTALL_CMD="sudo yum install -y"
        UPDATE_CMD="sudo yum update -y"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    if ! command -v brew &> /dev/null; then
        print_error "Homebrew is required for macOS installation"
        print_status "Install Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi
    INSTALL_CMD="brew install"
    UPDATE_CMD="brew update"
fi

print_status "Detected OS: $OS"

# Function to install Docker and Docker Compose
install_docker() {
    print_status "Installing Docker and Docker Compose..."
    
    if [[ "$OS" == "debian" ]]; then
        # Ubuntu/Debian Docker installation
        sudo apt remove -y docker docker-engine docker.io containerd runc || true
        $UPDATE_CMD
        $INSTALL_CMD ca-certificates curl gnupg lsb-release
        
        # Add Docker's official GPG key
        sudo mkdir -p /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        
        # Add Docker repository
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        
        $UPDATE_CMD
        $INSTALL_CMD docker-ce docker-ce-cli containerd.io docker-compose-plugin
        
    elif [[ "$OS" == "fedora" || "$OS" == "centos" ]]; then
        $INSTALL_CMD dnf-plugins-core
        sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
        $INSTALL_CMD docker-ce docker-ce-cli containerd.io docker-compose-plugin
        
    elif [[ "$OS" == "macos" ]]; then
        $INSTALL_CMD --cask docker
        print_status "Please start Docker Desktop application"
        read -p "Press Enter after Docker Desktop is running..."
    fi
    
    # Add user to docker group (Linux only)
    if [[ "$OS" != "macos" ]]; then
        sudo systemctl start docker
        sudo systemctl enable docker
        sudo usermod -aG docker $USER
        print_warning "You need to log out and log back in for docker group changes to take effect"
        print_status "Or run: newgrp docker"
    fi
    
    print_success "Docker installed successfully"
}

# Function to install using Docker (Recommended)
install_with_docker() {
    print_status "Installing CuePlex using Docker..."
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        print_status "Docker not found. Installing Docker..."
        install_docker
    fi
    
    # Create project directory
    INSTALL_DIR="$HOME/cueplex"
    print_status "Creating installation directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    # Download or copy necessary files
    if [[ -f "docker-compose.yml" ]]; then
        print_status "Using existing docker-compose.yml"
    else
        print_status "Downloading CuePlex Docker configuration..."
        # Copy the docker-compose.yml content here or download from repository
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
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
      - ./.env:/app/.env
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
      - ./init-db.sql:/docker-entrypoint-initdb.d/init-db.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cueplex_user -d cueplex"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: cueplex-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
EOF
    fi
    
    # Create init-db.sql
    cat > init-db.sql << 'EOF'
-- Initialize CuePlex database
GRANT ALL ON SCHEMA public TO cueplex_user;
GRANT ALL ON ALL TABLES IN SCHEMA public TO cueplex_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO cueplex_user;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO cueplex_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cueplex_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cueplex_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO cueplex_user;
EOF
    
    # Create .env file from template
    if [[ ! -f ".env" ]]; then
        if [[ -f "env-template" ]]; then
            cp env-template .env
            print_status "Created .env from template"
        else
            # Download env-template if not available
            curl -fsSL https://raw.githubusercontent.com/your-repo/cueplex/main/env-template -o .env
            print_status "Downloaded .env configuration"
        fi
        
        # Generate random SECRET_KEY
        SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | base64 | tr -d "=+/" | cut -c1-32)
        sed -i "s/CHANGE_THIS_TO_A_RANDOM_STRING_32_CHARS_MIN/$SECRET_KEY/g" .env
        print_status "Generated secure random SECRET_KEY"
    fi
    
    # Create directories
    mkdir -p logs data
    
    # Start services
    print_status "Starting CuePlex services..."
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d
    else
        docker compose up -d
    fi
    
    print_success "CuePlex is starting up!"
    print_status "Waiting for services to be ready..."
    sleep 15
    
    # Check if services are running
    if docker ps | grep -q cueplex-app; then
        print_success "CuePlex is now running!"
        echo
        echo "🎉 Installation Complete!"
        echo "========================"
        echo "• Web Interface: http://localhost:8001"
        echo "• Log files: $INSTALL_DIR/logs"
        echo "• Configuration: $INSTALL_DIR/.env"
        echo
        echo "Next Steps:"
        echo "1. Open http://localhost:8001 in your browser"
        echo "2. Follow the setup wizard to configure Plex"
        echo "3. Configure media servers (Radarr/Sonarr) if desired"
        echo
        echo "Management Commands:"
        echo "• Stop: cd $INSTALL_DIR && docker compose down"
        echo "• Restart: cd $INSTALL_DIR && docker compose restart"
        echo "• Update: cd $INSTALL_DIR && docker compose pull && docker compose up -d"
        echo "• Logs: cd $INSTALL_DIR && docker compose logs -f"
    else
        print_error "Installation failed. Check logs with: docker compose logs"
        exit 1
    fi
}

# Function to install natively (advanced users)
install_native() {
    print_status "Installing CuePlex natively..."
    print_warning "This method requires manual PostgreSQL setup"
    
    # Install system dependencies
    print_status "Installing system dependencies..."
    
    if [[ "$OS" == "debian" ]]; then
        $UPDATE_CMD
        $INSTALL_CMD python3 python3-pip python3-venv postgresql postgresql-contrib redis-server git
        sudo systemctl start postgresql redis-server
        sudo systemctl enable postgresql redis-server
        
    elif [[ "$OS" == "fedora" || "$OS" == "centos" ]]; then
        $UPDATE_CMD
        $INSTALL_CMD python3 python3-pip postgresql-server postgresql-contrib redis git
        sudo postgresql-setup initdb
        sudo systemctl start postgresql redis
        sudo systemctl enable postgresql redis
        
    elif [[ "$OS" == "macos" ]]; then
        $UPDATE_CMD
        $INSTALL_CMD python3 postgresql redis git
        brew services start postgresql redis
    fi
    
    # Database setup
    print_status "Setting up PostgreSQL database..."
    
    # Create database and user
    sudo -u postgres psql << 'EOF'
CREATE DATABASE cueplex;
CREATE USER cueplex_user WITH PASSWORD 'CuePlexSecure2024!';
GRANT ALL PRIVILEGES ON DATABASE cueplex TO cueplex_user;
\c cueplex
GRANT ALL ON SCHEMA public TO cueplex_user;
\q
EOF
    
    # Clone or setup application
    INSTALL_DIR="$HOME/cueplex"
    if [[ ! -d "$INSTALL_DIR" ]]; then
        print_status "Creating application directory..."
        mkdir -p "$INSTALL_DIR"
        # Here you would copy your application files or clone from git
    fi
    
    cd "$INSTALL_DIR"
    
    # Setup Python virtual environment
    print_status "Setting up Python environment..."
    python3 -m venv venv
    source venv/bin/activate
    
    # Install Python dependencies
    pip install --upgrade pip
    pip install -r requirements.txt
    
    # Create .env file from template
    if [[ ! -f ".env" ]]; then
        if [[ -f "env-template" ]]; then
            cp env-template .env
            print_status "Created .env from template"
        else
            # Download env-template if not available
            curl -fsSL https://raw.githubusercontent.com/your-repo/cueplex/main/env-template -o .env
            print_status "Downloaded .env configuration"
        fi
        
        # Generate random SECRET_KEY
        SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | base64 | tr -d "=+/" | cut -c1-32)
        sed -i "s/CHANGE_THIS_TO_A_RANDOM_STRING_32_CHARS_MIN/$SECRET_KEY/g" .env
        print_status "Generated secure random SECRET_KEY"
    fi
    
    # Create systemd service
    print_status "Creating systemd service..."
    sudo tee /etc/systemd/system/cueplex.service > /dev/null << EOF
[Unit]
Description=CuePlex Media Request System
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin
ExecStart=$INSTALL_DIR/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable cueplex
    sudo systemctl start cueplex
    
    print_success "CuePlex installed and started!"
    print_status "Service status: $(sudo systemctl is-active cueplex)"
}

# Main installation menu
echo "Choose installation method:"
echo "1) Docker (Recommended - Easy, isolated, includes PostgreSQL)"
echo "2) Native (Advanced - Direct installation, requires manual database setup)"
echo "3) Exit"

read -p "Enter your choice (1-3): " choice

case $choice in
    1)
        install_with_docker
        ;;
    2)
        install_native
        ;;
    3)
        echo "Installation cancelled"
        exit 0
        ;;
    *)
        print_error "Invalid choice"
        exit 1
        ;;
esac