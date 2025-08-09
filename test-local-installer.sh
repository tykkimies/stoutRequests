#!/bin/bash

# Test Local CuePlex Installer
# Uses local cueplex-test image instead of pulling from registry

set -e

echo "🧪 Testing CuePlex Local Installer"
echo "================================="

# Make sure local image exists
if ! docker image inspect cueplex-test:latest >/dev/null 2>&1; then
    echo "❌ Local image cueplex-test:latest not found"
    echo "Build it first: docker build -t cueplex-test:latest ."
    exit 1
fi

echo "✅ Local image found"

# Run installer with local image
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e CUEPLEX_IMAGE=cueplex-test:latest \
  -e CUEPLEX_PORT=8001 \
  -e DATA_PATH=/opt/cueplex-test \
  cueplex/installer:latest

echo "🎉 Test installer complete!"
echo "Check: http://localhost:8001"