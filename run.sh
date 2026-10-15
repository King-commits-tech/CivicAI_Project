#!/bin/bash
# CivicAI - one-command start for Mac / Linux
cd "$(dirname "$0")"
echo "[1/2] Installing required libraries (first time only)..."
python3 -m pip install -q -r requirements.txt 2>/dev/null || python3 -m pip install -q --break-system-packages -r requirements.txt
echo "[2/2] Starting CivicAI..."
python3 app.py
