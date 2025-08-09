#!/bin/bash

# Setup Local Docker Registry for Testing
# Useful for testing registry workflows locally

set -e

echo "🏗️ Setting up local Docker registry for testing"
echo "==============================================="

REGISTRY_PORT=${1:-5000}
REGISTRY_NAME="local-registry"

# Check if registry is already running
if docker ps --filter name=$REGISTRY_NAME --format '{{.Names}}' | grep -q $REGISTRY_NAME; then
    echo "✅ Local registry already running at localhost:$REGISTRY_PORT"
else
    echo "🚀 Starting local Docker registry..."
    docker run -d \
        --name $REGISTRY_NAME \
        --restart=always \
        -p $REGISTRY_PORT:5000 \
        registry:2
    
    echo "✅ Local registry started at localhost:$REGISTRY_PORT"
fi

# Build and tag image for local registry
echo "🔨 Building and tagging image for local registry..."
docker build -t cueplex-test:latest .
docker tag cueplex-test:latest localhost:$REGISTRY_PORT/cueplex:latest

# Push to local registry
echo "📤 Pushing to local registry..."
docker push localhost:$REGISTRY_PORT/cueplex:latest

echo "🎉 Setup complete!"
echo ""
echo "Usage in Portainer:"
echo "• Image: localhost:$REGISTRY_PORT/cueplex:latest"
echo ""
echo "To stop local registry:"
echo "docker stop $REGISTRY_NAME && docker rm $REGISTRY_NAME"
echo ""
echo "Registry UI available at: http://localhost:$REGISTRY_PORT/v2/_catalog"