#!/bin/bash
echo "🔄 Resetting CuePlex for testing..."

# Check if the server is running and suggest stopping it
if pgrep -f "uvicorn.*main:app" > /dev/null; then
    echo "⚠️  Warning: CuePlex server appears to be running!"
    echo "   Please stop it first with: sudo systemctl stop cueplex"
    echo "   Or if running manually: pkill -f uvicorn"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Reset cancelled. Please stop the server first."
        exit 1
    fi
fi

cd /opt/stoutRequests
source venv/bin/activate

# Check if this is a fresh reset or migration
if [ "$1" = "--migrate-only" ]; then
    echo "🔄 Running database migration only..."
    python migrate_db.py
elif [ "$1" = "--force" ]; then
    echo "💥 Running force database reset (drops all tables)..."
    python force_reset_db.py
else
    echo "🗑️ Running standard reset..."
    python reset_setup.py
fi
echo ""
echo "✅ Reset complete! Ready for testing."
echo ""
echo "🚀 To start the server:"
echo "   sudo systemctl start cueplex"
echo "   OR manually: uvicorn app.main:app --host 0.0.0.0 --port 8000"