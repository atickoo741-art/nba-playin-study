#!/usr/bin/env bash
# One-time environment setup. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
echo "Environment ready. Run: .venv/bin/python run_all.py"
