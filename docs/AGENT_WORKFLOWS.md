# Agent Workflows

This repository is safe for coding agents to work in when they preserve the diagnostic safety gates.

## AI Diagnosis CLI

Use the installed CLI entrypoint for the primary workflow:

```bash
open-mechanic diagnose --vehicle "2018 Ford F-150" --mileage 85000 --offline
open-mechanic diagnose --vehicle "2018 Ford F-150" --mileage 85000 --vin 1FTFW1E58JFC12345 --provider openai
```

Provider selection is controlled by `AI_PROVIDER` or `--provider`.

`auto` precedence is:

1. OpenAI cloud when `OPENAI_API_KEY` is set
2. Anthropic cloud when `ANTHROPIC_API_KEY` is set
3. Ollama when `OLLAMA_MODEL` is set
4. OpenAI-compatible local when `LOCAL_OPENAI_BASE_URL` and `LOCAL_OPENAI_MODEL` are set

Local providers are useful for privacy and offline work, but their diagnostic quality depends on the installed model. Always preserve the informational disclaimer.

## Free API Enrichment

When a VIN is present, the CLI automatically calls NHTSA vPIC for vehicle context. This must remain non-fatal: network failures, malformed responses, and missing VIN data should not block diagnosis.

## Safety Rules

- Never remove the DTC clear confirmation gate.
- Never remove or delegate the diagnosis disclaimer to a caller.
- Never hardcode API keys.
- Never crash on unsupported OBD PIDs.
- Keep EV/hybrid-specific behavior out of the current core workflow.

## Verification

Before claiming completion, run:

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m ruff check src tests scripts
```
