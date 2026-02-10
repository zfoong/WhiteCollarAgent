#!/bin/bash
echo "Running Google Token Refresh Test..."
echo ""
cd "$(dirname "$0")"
python test_token_refresh.py
