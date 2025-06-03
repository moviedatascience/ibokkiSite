#!/bin/bash

# Start Gunicorn WSGI server for HTTP requests
echo "Starting Gunicorn WSGI server..."

# Set environment variables
export DJANGO_SETTINGS_MODULE=ibokki.settings

# Activate virtual environment if needed
# source venv/bin/activate

# Start Gunicorn
exec gunicorn --bind 0.0.0.0:8000 --workers 3 --timeout 120 ibokki.wsgi:application 