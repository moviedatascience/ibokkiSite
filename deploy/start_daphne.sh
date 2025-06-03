#!/bin/bash

# Start Daphne ASGI server for WebSocket connections
echo "Starting Daphne ASGI server..."

# Set environment variables
export DJANGO_SETTINGS_MODULE=ibokki.settings

# Activate virtual environment if needed
# source venv/bin/activate

# Start Daphne
exec daphne -b 0.0.0.0 -p 8001 ibokki.asgi:application 