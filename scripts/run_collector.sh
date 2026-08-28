#!/bin/bash
# Run from project root or set absolute paths on server
cd "$(dirname "$0")/../backend"
source ../venv/bin/activate 2>/dev/null || true
python collector.py
