#!/bin/bash

# Cleanup previous test installations

echo "🧹 Cleaning up previous CuePlex test installations"
echo "================================================="

# Stop and remove any existing cueplex containers
echo "Stopping containers..."
docker stop cueplex-app cueplex-postgres cueplex-test cueplex-test-postgres 2>/dev/null || true
docker rm cueplex-app cueplex-postgres cueplex-test cueplex-test-postgres 2>/dev/null || true

# Remove test networks
echo "Removing test networks..."
docker network rm cueplex-test cueplex 2>/dev/null || true

# Remove test volumes (optional - uncomment if you want clean slate)
# echo "Removing test volumes..."
# docker volume rm cueplex_data cueplex_logs postgres_data 2>/dev/null || true
# docker volume rm cueplex_test_data cueplex_test_logs cueplex_test_postgres 2>/dev/null || true

# Clean up installation directories
echo "Cleaning installation directories..."
sudo rm -rf /opt/cueplex-test /opt/cueplex 2>/dev/null || true

echo "✅ Cleanup complete!"
echo ""
echo "Now you can run the installer fresh:"
echo "./test-local-installer.sh"