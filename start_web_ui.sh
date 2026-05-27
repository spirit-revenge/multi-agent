#!/bin/bash
# LectureCrewLLM Web UI Startup Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "=========================================="
echo "  LectureCrewLLM Web UI"
echo "=========================================="
echo ""

# Ensure required directories exist
mkdir -p "$SCRIPT_DIR/knowledge"
mkdir -p "$SCRIPT_DIR/conversations/sessions"
mkdir -p "$SCRIPT_DIR/cache"
mkdir -p "$SCRIPT_DIR/output"

# Load .env (export only WEB_UI_PORT, let web_ui.py handle the rest)
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    . "$SCRIPT_DIR/.env"
    set +a
fi
PORT=${WEB_UI_PORT:-7860}

echo "  URL:       http://localhost:$PORT"
echo "  Lectures:  $SCRIPT_DIR/knowledge/"
echo "  Output:    $SCRIPT_DIR/output/"
echo "  Press Ctrl+C to stop"
echo "=========================================="
echo ""

cd "$SCRIPT_DIR"
python web_ui.py
