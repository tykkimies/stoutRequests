#!/bin/bash
echo "🔄 Resetting Stout Requests for testing..."
cd /opt/stoutRequests
source venv/bin/activate
python reset_setup.py
echo ""
echo "✅ Reset complete! Ready for testing."