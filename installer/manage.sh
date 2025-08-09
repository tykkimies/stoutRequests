#!/bin/bash

# CuePlex Management Script
# Helper commands for managing the CuePlex installation

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_help() {
    echo "🎬 CuePlex Management Commands"
    echo "=============================="
    echo
    echo "Usage: $0 <command>"
    echo
    echo "Commands:"
    echo "  status    - Show service status"
    echo "  logs      - View application logs"
    echo "  start     - Start all services"
    echo "  stop      - Stop all services"
    echo "  restart   - Restart all services"
    echo "  update    - Update to latest version"
    echo "  backup    - Backup application data"
    echo "  reset     - Reset and reinstall"
    echo "  uninstall - Remove everything"
    echo
}

case $1 in
    status)
        echo -e "${BLUE}CuePlex Service Status:${NC}"
        docker compose ps
        ;;
    logs)
        echo -e "${BLUE}CuePlex Logs (Ctrl+C to exit):${NC}"
        docker compose logs -f cueplex
        ;;
    start)
        echo -e "${BLUE}Starting CuePlex...${NC}"
        docker compose start
        echo -e "${GREEN}CuePlex started${NC}"
        ;;
    stop)
        echo -e "${YELLOW}Stopping CuePlex...${NC}"
        docker compose stop
        echo -e "${GREEN}CuePlex stopped${NC}"
        ;;
    restart)
        echo -e "${BLUE}Restarting CuePlex...${NC}"
        docker compose restart
        echo -e "${GREEN}CuePlex restarted${NC}"
        ;;
    update)
        echo -e "${BLUE}Updating CuePlex...${NC}"
        docker compose pull
        docker compose up -d
        echo -e "${GREEN}CuePlex updated${NC}"
        ;;
    backup)
        BACKUP_FILE="cueplex-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
        echo -e "${BLUE}Creating backup: $BACKUP_FILE${NC}"
        docker run --rm -v cueplex_data:/data -v $(pwd):/backup alpine tar czf "/backup/$BACKUP_FILE" -C /data .
        echo -e "${GREEN}Backup created: $BACKUP_FILE${NC}"
        ;;
    reset)
        echo -e "${YELLOW}Resetting CuePlex installation...${NC}"
        read -p "This will destroy all data. Are you sure? (yes/NO): " confirm
        if [[ "$confirm" == "yes" ]]; then
            docker compose down -v
            docker compose up -d
            echo -e "${GREEN}CuePlex reset complete${NC}"
        fi
        ;;
    uninstall)
        echo -e "${YELLOW}Uninstalling CuePlex...${NC}"
        read -p "This will remove everything. Are you sure? (yes/NO): " confirm
        if [[ "$confirm" == "yes" ]]; then
            docker compose down -v
            docker network rm cueplex 2>/dev/null || true
            echo -e "${GREEN}CuePlex uninstalled${NC}"
        fi
        ;;
    *)
        print_help
        ;;
esac