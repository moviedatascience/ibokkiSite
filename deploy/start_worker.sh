#!/bin/bash

# Start Django Channels worker for background task processing
echo "Starting Django Channels worker..."

# Set environment variables
export DJANGO_SETTINGS_MODULE=ibokki.settings

# Activate virtual environment if needed
# source venv/bin/activate

# Start worker
exec python manage.py runworker 