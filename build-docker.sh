#!/bin/bash

# CuePlex Docker Build Script
# Builds and optionally tests the Docker image

set -e

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

# Configuration
IMAGE_NAME="cueplex/cueplex"
VERSION=${1:-"latest"}
DOCKERFILE=${2:-"Dockerfile"}
PLATFORM=${3:-"linux/amd64"}

echo "🐳 CuePlex Docker Build"
echo "======================="
echo "Image: $IMAGE_NAME:$VERSION"
echo "Dockerfile: $DOCKERFILE"
echo "Platform: $PLATFORM"
echo

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running or accessible"
    exit 1
fi

print_success "Docker is running"

# Build the image
print_status "Building Docker image..."
if docker build \
    --platform "$PLATFORM" \
    -f "$DOCKERFILE" \
    -t "$IMAGE_NAME:$VERSION" \
    -t "$IMAGE_NAME:latest" \
    .; then
    print_success "Docker image built successfully"
else
    print_error "Docker build failed"
    exit 1
fi

# Show image info
print_status "Image information:"
docker images "$IMAGE_NAME:$VERSION" --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedAt}}\t{{.Size}}"

# Test the image
echo
read -p "Test the image? (y/N): " test_image
if [[ "$test_image" =~ ^[Yy]$ ]]; then
    print_status "Testing Docker image..."
    
    # Create a test docker-compose file
    cat > docker-compose.test.yml << EOF
version: '3.8'
services:
  cueplex-test:
    image: $IMAGE_NAME:$VERSION
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://cueplex_user:CuePlexSecure2024!@postgres:5432/cueplex
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./test-logs:/app/logs
      - test-data:/app/data

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=cueplex
      - POSTGRES_USER=cueplex_user
      - POSTGRES_PASSWORD=CuePlexSecure2024!
    volumes:
      - test-postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cueplex_user -d cueplex"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  test-postgres:
  test-data:
EOF

    print_status "Starting test environment..."
    docker-compose -f docker-compose.test.yml up -d
    
    print_status "Waiting for services to start..."
    sleep 15
    
    # Test health endpoint
    if curl -f http://localhost:8001/health > /dev/null 2>&1; then
        print_success "Health check passed"
        
        # Show logs
        print_status "Recent logs:"
        docker-compose -f docker-compose.test.yml logs --tail=10 cueplex-test
        
        echo
        print_success "🎉 Test successful! CuePlex is running at http://localhost:8001"
        echo
        read -p "Stop test environment? (Y/n): " stop_test
        if [[ ! "$stop_test" =~ ^[Nn]$ ]]; then
            docker-compose -f docker-compose.test.yml down
            print_status "Test environment stopped"
            rm docker-compose.test.yml
        else
            print_warning "Test environment left running"
            print_status "To stop: docker-compose -f docker-compose.test.yml down"
        fi
    else
        print_error "Health check failed"
        print_status "Logs:"
        docker-compose -f docker-compose.test.yml logs cueplex-test
        docker-compose -f docker-compose.test.yml down
        rm docker-compose.test.yml
        exit 1
    fi
fi

echo
print_success "🎉 Build complete!"
print_status "Image: $IMAGE_NAME:$VERSION"
print_status "Size: $(docker images $IMAGE_NAME:$VERSION --format '{{.Size}}')"
echo
print_status "Next steps:"
echo "• Test locally: docker run -p 8001:8001 $IMAGE_NAME:$VERSION"
echo "• Push to registry: docker push $IMAGE_NAME:$VERSION"
echo "• Multi-arch build: ./build-multi-arch.sh"