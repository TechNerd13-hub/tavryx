# TAVRYX Architecture

TAVRYX treats an incoming message as a possible state transition rather than merely a prompt.

```text
channels
   ↓
Caspian
   ↓
situation model
   ↓
adaptive mode router
   ↓
Gemini structured reasoning
   ↓
deterministic transition/revision layer
   ↓
SQLite memory
   ↓
dynamic response
```

The application, rather than the model alone, owns persistence, state comparison, revision detection, command routing, validation, transport, and health.

Modes:
- INCIDENT
- DECISION
- LEARNING
- CREATIVE
- PLANNING
- GENERAL

The product deliberately does not execute arbitrary actions from model output.
