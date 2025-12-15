#!/bin/bash
# Development server startup script
# This script loads environment variables and starts the FastAPI dev server

# Activate virtual environment
source .venv/bin/activate

# Check if .env file exists, exit if not
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please copy .env.example to .env and fill in your values:"
    echo "  cp .env.example .env"
    exit 1
fi

# Load environment variables from .env file
export $(grep -v '^#' .env | xargs)

# Add current directory to PYTHONPATH so app module can be imported
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

fastapi dev