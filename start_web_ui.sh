#!/bin/bash

# LectureCrewLLM Web UI Startup Script
# This script starts the Flask web application

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "=========================================="
echo "🚀 LectureCrewLLM Web UI Launcher"
echo "=========================================="
echo ""

# Check if conda is available
if ! command -v conda &> /dev/null; then
    echo "❌ Error: Conda is not installed or not in PATH"
    echo "Please install Anaconda/Miniconda first"
    exit 1
fi

# Check if the camel environment exists
if ! conda env list | grep -q "^camel "; then
    echo "❌ Error: Conda environment 'camel' not found"
    echo "Please create the environment first: conda create -n camel python=3.13"
    exit 1
fi

# Check if Flask is installed
echo "📦 Checking Flask installation..."
if ! conda run -n camel python -c "import flask" 2>/dev/null; then
    echo "⚠️  Flask not found. Installing Flask..."
    conda run -n camel pip install Flask==3.0.0 > /dev/null 2>&1
    if conda run -n camel python -c "import flask" 2>/dev/null; then
        echo "✅ Flask installed successfully"
    else
        echo "❌ Failed to install Flask"
        exit 1
    fi
else
    echo "✅ Flask is installed"
fi

# Check if required directories exist
echo ""
echo "📁 Checking directories..."
mkdir -p "$SCRIPT_DIR/knowledge"
mkdir -p "$SCRIPT_DIR/conversations"
mkdir -p "$SCRIPT_DIR/conversations/sessions"
mkdir -p "$SCRIPT_DIR/cache"
mkdir -p "$SCRIPT_DIR/output"
mkdir -p "$SCRIPT_DIR/templates"
mkdir -p "$SCRIPT_DIR/static"
echo "✅ All directories ready"

# Display startup information
echo ""
echo "=========================================="
echo "✅ Ready to start Web UI"
echo "=========================================="
echo ""
echo "📍 Web UI URL:      http://localhost:7860"
echo "📂 Lecture files:   $SCRIPT_DIR/knowledge/"
echo "💾 Conversations:   $SCRIPT_DIR/conversations/"
echo "📊 Cache:           $SCRIPT_DIR/cache/"
echo "📄 Outputs:         $SCRIPT_DIR/output/"
echo ""
echo "🎯 Press Ctrl+C to stop the server"
echo "=========================================="
echo ""

# Start the web UI
cd "$SCRIPT_DIR"
WEB_UI_PORT=7860 conda run -n camel python web_ui.py
