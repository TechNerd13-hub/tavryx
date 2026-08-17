#!/usr/bin/env bash
set -euo pipefail
printf '\nTAVRYX 3.0 RELEASE CHECK\n========================\n'
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -r requirements.txt >/tmp/tavryx-pip.log
python -m pytest -q
python -m compileall -q .
python - <<'PY'
from pathlib import Path
required = ["GEMINI_API_KEY", "CASPIAN_API_KEY"]
env = Path('.env').read_text() if Path('.env').exists() else ''
missing = [k for k in required if not any(line.startswith(k+'=') and line.split('=',1)[1].strip() for line in env.splitlines())]
if missing: raise SystemExit('Missing required .env values: ' + ', '.join(missing))
print('Environment: PASS')
print('Python compile: PASS')
print('Test suite: PASS')
print('Production model: gemini-3.6-flash')
print('Adaptive thinking: minimal → low → medium')
print('Release gate: GREEN')
PY
