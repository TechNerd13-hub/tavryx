#!/bin/bash
set -e
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
echo "TAVRYX environment ready. Edit .env, then run: python main.py"
