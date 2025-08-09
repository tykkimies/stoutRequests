#!/bin/bash

# CuePlex Multi-Architecture Docker Build Script
# Builds for multiple platforms (x86_64, ARM64) and pushes to registry

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
PLATFORMS="linux/amd64,linux/arm64"
REGISTRY=${3:-""}

echo "🌍 CuePlex Multi-Architecture Build"
echo "==================================="
echo "Image: $IMAGE_NAME:$VERSION"
echo "Dockerfile: $DOCKERFILE"
echo "Platforms: $PLATFORMS"
if [[ -n "$REGISTRY" ]]; then
    echo "Registry: $REGISTRY"
fi
echo

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running or accessible"
    exit 1
fi

# Check if buildx is available
if ! docker buildx version > /dev/null 2>&1; then
    print_error "Docker buildx is not available"
    print_status "Install buildx or use Docker Desktop"
    exit 1
fi

print_success "Docker and buildx are ready"

# Create or use buildx builder
BUILDER_NAME="cueplex-builder"
if ! docker buildx inspect "$BUILDER_NAME" > /dev/null 2>&1; then
    print_status "Creating multi-platform builder..."
    docker buildx create --name "$BUILDER_NAME" --driver docker-container --bootstrap
else
    print_status "Using existing builder: $BUILDER_NAME"
fi

# Use the builder
docker buildx use "$BUILDER_NAME"

# Show builder info
print_status "Builder platforms:"
docker buildx inspect --bootstrap

# Determine if we should push
PUSH_FLAG=""
if [[ -n "$REGISTRY" ]] || [[ "$VERSION" != "latest" ]]; then
    echo
    read -p "Push to registry after build? (y/N): " should_push
    if [[ "$should_push" =~ ^[Yy]$ ]]; then
        PUSH_FLAG="--push"
        print_warning "Images will be pushed to registry"
    else
        print_status "Images will be built locally only"
    fi
fi

# Build multi-architecture image
print_status "Building multi-architecture image..."
echo "This may take several minutes..."

BUILD_ARGS=""
if [[ -n "$REGISTRY" ]]; then
    BUILD_ARGS="--tag $REGISTRY/$IMAGE_NAME:$VERSION --tag $REGISTRY/$IMAGE_NAME:latest"
else
    BUILD_ARGS="--tag $IMAGE_NAME:$VERSION --tag $IMAGE_NAME:latest"
fi

if docker buildx build \
    --platform "$PLATFORMS" \
    -f "$DOCKERFILE" \
    $BUILD_ARGS \
    $PUSH_FLAG \
    .; then
    print_success "Multi-architecture build completed"
else
    print_error "Multi-architecture build failed"
    exit 1
fi

if [[ -n "$PUSH_FLAG" ]]; then
    print_success "🎉 Images pushed to registry!"
    if [[ -n "$REGISTRY" ]]; then
        echo "• $REGISTRY/$IMAGE_NAME:$VERSION"
        echo "• $REGISTRY/$IMAGE_NAME:latest"
    else
        echo "• $IMAGE_NAME:$VERSION" 
        echo "• $IMAGE_NAME:latest"
    fi
else
    print_success "🎉 Multi-architecture build complete!"
    print_warning "Images built but not pushed to registry"
fi

echo
print_status "Supported architectures:"
if [[ -n "$REGISTRY" ]]; then
    docker buildx imagetools inspect "$REGISTRY/$IMAGE_NAME:$VERSION" 2>/dev/null || docker buildx imagetools inspect "$IMAGE_NAME:$VERSION"
else
    docker buildx imagetools inspect "$IMAGE_NAME:$VERSION" 2>/dev/null || print_warning "Cannot inspect - images may be local only"
fi

echo
print_status "Usage examples:"
echo "• Docker Compose: image: $IMAGE_NAME:$VERSION"
echo "• Docker run: docker run -p 8001:8001 $IMAGE_NAME:$VERSION"
if [[ -n "$REGISTRY" ]]; then
    echo "• Registry: $REGISTRY/$IMAGE_NAME:$VERSION"
fi

echo
print_status "To clean up builder:"
echo "docker buildx rm $BUILDER_NAME"