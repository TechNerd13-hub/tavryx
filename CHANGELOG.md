# TAVRYX 3.0

## What changed
- Situation portfolio selection: TAVRYX can resume an older relevant situation instead of following only the latest message.
- Adaptive reasoning tuned for latency: `minimal` for normal requests, `low` for complex requests, `medium` for critical incidents.
- Situation Radar dashboard with live thread overview.
- Situation evolution timeline.
- `/timeline` command.
- `/ready` deployment readiness endpoint.
- Lightweight HTTP rate limiting.
- Improved failure boundary and production-safe responses.
- Expanded offline test coverage.
- Gemini 3.6 Flash pinned as the stable production model.
