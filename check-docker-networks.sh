#!/bin/bash

# Docker Network Diagnosis Script for CuePlex + Servarr Integration

echo "🔍 Docker Network Diagnosis for CuePlex"
echo "========================================"

# Find Radarr containers
echo "📡 Finding Radarr containers..."
RADARR_CONTAINERS=$(docker ps --filter "name=radarr" --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}")
if [[ -n "$RADARR_CONTAINERS" ]]; then
    echo "$RADARR_CONTAINERS"
else
    echo "❌ No Radarr containers found"
fi

echo ""

# Find Sonarr containers
echo "📺 Finding Sonarr containers..."
SONARR_CONTAINERS=$(docker ps --filter "name=sonarr" --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}")
if [[ -n "$SONARR_CONTAINERS" ]]; then
    echo "$SONARR_CONTAINERS"
else
    echo "❌ No Sonarr containers found"
fi

echo ""

# List all networks
echo "🌐 Docker Networks:"
docker network ls --format "table {{.Name}}\t{{.Driver}}\t{{.Scope}}"

echo ""

# Check what networks Radarr/Sonarr are on
echo "🔗 Network connections:"
for container in $(docker ps --filter "name=radarr" --filter "name=sonarr" --format "{{.Names}}"); do
    echo "Container: $container"
    docker inspect $container --format '  Networks: {{range $net, $conf := .NetworkSettings.Networks}}{{$net}} ({{$conf.IPAddress}}) {{end}}'
    echo ""
done

# Find CuePlex containers
echo "🎬 Finding CuePlex containers..."
CUEPLEX_CONTAINERS=$(docker ps --filter "name=cueplex" --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}")
if [[ -n "$CUEPLEX_CONTAINERS" ]]; then
    echo "$CUEPLEX_CONTAINERS"
    echo ""
    for container in $(docker ps --filter "name=cueplex" --format "{{.Names}}"); do
        echo "CuePlex Container: $container"
        docker inspect $container --format '  Networks: {{range $net, $conf := .NetworkSettings.Networks}}{{$net}} ({{$conf.IPAddress}}) {{end}}'
    done
else
    echo "❌ No CuePlex containers found"
fi

echo ""
echo "💡 Recommendations:"
echo "1. Use container names instead of IPs: http://radarr-container-name:7878"
echo "2. Ensure CuePlex is on the same network as Radarr/Sonarr"  
echo "3. Check if Radarr/Sonarr have base URLs configured"