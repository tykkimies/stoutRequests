#!/bin/bash

# Build CuePlex Installer Image

set -e

echo "🔨 Building CuePlex Installer Image"
echo "==================================="

# Build the installer image
docker build -f Dockerfile.installer -t cueplex/installer:latest .

echo "✅ Installer image built successfully"
echo ""
echo "Usage:"
echo "  docker run --rm -v /var/run/docker.sock:/var/run/docker.sock cueplex/installer:latest"
echo ""
echo "Advanced usage:"
echo "  docker run --rm \\"
echo "    -v /var/run/docker.sock:/var/run/docker.sock \\"
echo "    -e CUEPLEX_PORT=8080 \\"
echo "    -e DATA_PATH=/opt/cueplex \\"
echo "    cueplex/installer:latest"