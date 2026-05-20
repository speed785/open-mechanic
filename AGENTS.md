# AGENTS.md — open-mechanic

> Read this first. Authoritative guide for AI agents working on this codebase.

---

## Project Overview

**open-mechanic** is an open-source, AI-powered OBD-II car diagnostics platform. It reads live sensor data and fault codes from a vehicle via a USB OBD-II adapter, feeds that data to an AI model of your choice with vehicle context, and returns plain-English diagnosis, severity ratings, repair steps, and cost estimates. Target users are car owners who want real diagnostic visibility without paying dealer fees.

---

## Current Build Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 — Foundation | ✅ COMPLETE | OBD connection, sensor polling, DTC reading, SQLite logging |
| Phase 2 — AI Diagnostics | ✅ COMPLETE | Claude API integration, JSON output, 24h cache, disclaimer |
| Phase 3 — Interface | PENDING | CLI, FastAPI, React dashboard |
| Phase 4 — Community | FUTURE | Public release, community DTC DB |

Phase 1 and Phase 2 are fully implemented and tested on a real vehicle (2026-03-18).
Confirmed working: ISO 15765-4 CAN 11/500 protocol, OBDLink EX on `/dev/ttyUSB0` at 115200 baud.

---

## Repository Structure

```
open-mechanic/
├── README.md
├── CONTRIBUTING.md
├── AGENTS.md
├── LICENSE                        (MIT)
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── src/
│   └── open_mechanic/             (package name: open_mechanic, underscore)
│       ├── __init__.py
│       ├── connection.py          OBD-II connection management
│       ├── reader.py              Live sensor data polling
│       ├── dtc.py                 DTC code reading + decoding
│       ├── ai/
│       │   ├── __init__.py
│       │   ├── diagnose.py        Claude API integration
│       │   └── prompts.py         Prompt templates
│       ├── api/
│       │   ├── __init__.py
│       │   └── routes.py          FastAPI routes (Phase 3)
│       └── db/
│           ├── __init__.py
│           └── models.py          SQLAlchemy models
│
├── scripts/
│   ├── test_connection.py         Standalone adapter test (no package import needed)
│   └── seed_dtc_db.py             Populate local DTC database
│
├── data/
│   └── dtc_codes.json             Offline DTC reference database (522 codes)
│
├── tests/
│
├── docs/
│   ├── SETUP_LINUX.md
│   ├── SETUP_MACOS.md
│   └── SETUP_WINDOWS.md
│
└── .github/
    ├── workflows/ci.yml
    └── ISSUE_TEMPLATE/
```

---

## Architecture

Data flows through the system in this order:

```
OBD-II Adapter (USB)
    ↓
connection.py — OBDConnection class
    Manages serial port, auto-detection, reconnect backoff
    ↓
reader.py — SensorPoller          dtc.py — DTCReader
    Live sensor snapshots              DTC code reading + decoding
    ↓                                  ↓
db/models.py — SQLAlchemy
    VehicleProfile, DiagnosticSession, SensorReading, DTCRecord, DiagnosisResult
    ↓
ai/prompts.py — format_diagnostic_prompt()
    Assembles vehicle context + DTCs + sensor snapshot into Claude prompt
    ↓
ai/diagnose.py — DiagnosticEngine
    Calls Claude API, parses JSON response, injects disclaimer, caches result
    ↓
Output: DiagnosisResult dataclass
    {severity, summary, likely_causes, repair_steps, estimated_cost_usd, diy_feasible, ...}
```

---

## Key Files and Their Roles

| File | Role |
|------|------|
| `src/open_mechanic/connection.py` | OBD connection management, port auto-detection, reconnect logic |
| `src/open_mechanic/reader.py` | Live sensor polling, `SensorPoller` class, `get_snapshot()` |
| `src/open_mechanic/dtc.py` | DTC reading, decoding from `data/dtc_codes.json`, clear gate |
| `src/open_mechanic/db/models.py` | SQLAlchemy models, `init_db()`, `get_session()` |
| `src/open_mechanic/ai/prompts.py` | Prompt templates, `format_diagnostic_prompt()` |
| `src/open_mechanic/ai/diagnose.py` | Provider-agnostic diagnosis engine, JSON parsing, 24h cache, disclaimer injection |
| `src/open_mechanic/ai/providers.py` | OpenAI, Anthropic, Ollama, and OpenAI-compatible local provider adapters |
| `src/open_mechanic/diagnosis_cli.py` | Guided Rich CLI diagnosis flow and JSON report writing |
| `src/open_mechanic/enrichment.py` | Optional NHTSA vPIC VIN decode enrichment |
| `data/dtc_codes.json` | Offline DTC reference: `{code, description, severity, category}` |
| `scripts/test_connection.py` | Standalone adapter test, uses `python-obd` directly (no package import) |

---

## Conventions

- **Package name**: `open_mechanic` (underscore, not hyphen)
- **Source layout**: `src/open_mechanic/` (src layout, not flat)
- **Python**: 3.11+ minimum
- **Type hints**: everywhere, mypy strict (`--ignore-missing-imports` for now)
- **Data structures**: dataclasses (not dicts, not Pydantic models in core layer)
- **Linting**: ruff (`ruff check` + `ruff format`)
- **Tests**: pytest
- **AI providers**: provider-agnostic via `AI_PROVIDER`; `auto` prefers OpenAI, then Anthropic, then Ollama, then OpenAI-compatible local
- **Database**: SQLite dev path configurable via `DB_PATH` env var

---

## Cross-Platform Port Detection

Hardware: OBDLink EX FORScan USB adapter (FTDI chip on all platforms).

| Platform | Default port | Port pattern | Driver needed |
|----------|-------------|--------------|---------------|
| Linux | `/dev/ttyUSB0` | `/dev/ttyUSB*` | None (built-in FTDI) |
| macOS | `/dev/cu.usbserial-*` | `/dev/cu.usbserial-*`, `/dev/tty.usbserial-*` | FTDI VCP driver OR native macOS 12+ |
| Windows | `COM3` (varies) | `COM*` | FTDI CDM driver |

Use `platform.system()` which returns `"Linux"`, `"Darwin"` (macOS), or `"Windows"`.
Use `glob.glob()` for macOS port scanning.
`python-obd`'s `obd.OBD()` auto-detects on all platforms — `scan_ports()` is a fallback helper.
On Windows, auto-detection is unreliable; recommend `OBD_PORT` env var override.

---

## CRITICAL CONSTRAINTS

Never violate these. They exist for safety and legal reasons.

1. **DTC clear requires explicit confirmation.** `clear_dtcs()` MUST require `confirmed: bool = False` parameter. If called without `confirmed=True`, raise `DTCClearNotConfirmed`. No exceptions.

2. **All AI diagnostic output MUST include the disclaimer.** Inject this into every `DiagnosisResult`: `"This diagnosis is informational only and does not constitute professional mechanical advice. Consult a qualified mechanic before making safety-critical repairs."` The `DiagnosticEngine` is responsible for always injecting this — never rely on callers to add it.

3. **Never hardcode API keys.** Always read from env vars or `.env` via `python-dotenv`. The `ANTHROPIC_API_KEY` must never appear in source code.

4. **Handle unsupported OBD PIDs gracefully.** Not all cars support all OBD-II commands. When a PID is unsupported, skip it silently and continue. Never crash on an unsupported command.

5. **EV/Hybrid support is out of scope for Phase 1-2.** Don't add EV-specific logic. Document it as a future module if asked.

---

## Running the Project

```bash
git clone https://github.com/yourusername/open-mechanic
cd open-mechanic
pip install -e ".[dev]"

cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY

python scripts/test_connection.py
# If connection hangs, add: --protocol 6  (ISO 15765-4 CAN, most 2008+ cars)
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Environment Variables

All configured in `.env` (copy from `.env.example`):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AI_PROVIDER` | No | `auto` | Provider selection: `auto`, `openai`, `anthropic`, `ollama`, `openai_compatible` |
| `OPENAI_API_KEY` | No | — | OpenAI API key, preferred by `auto` when present |
| `OPENAI_MODEL` | No | `gpt-4o` | OpenAI model to use |
| `ANTHROPIC_API_KEY` | No | — | Anthropic API key |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-5` | Anthropic model to use |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama local API URL |
| `OLLAMA_MODEL` | No | — | Ollama model to use |
| `LOCAL_OPENAI_BASE_URL` | No | — | OpenAI-compatible local API base URL |
| `LOCAL_OPENAI_API_KEY` | No | `local` | OpenAI-compatible local API key if required |
| `LOCAL_OPENAI_MODEL` | No | — | OpenAI-compatible local model to use |
| `OBD_PORT` | No | platform default | Override OBD port (e.g. `COM3`, `/dev/ttyUSB0`) |
| `OBD_BAUDRATE` | No | auto | Serial baudrate |
| `OBD_PROTOCOL` | No | auto | OBD protocol number. Set `6` for ISO 15765-4 CAN 11/500 (most 2008+ cars). Skips slow auto-detection. |
| `DB_PATH` | No | `data/sessions.db` | SQLite database path |

---

## What NOT To Do

- Do not clear DTCs without the `confirmed=True` gate
- Do not add AI diagnostic output without the disclaimer
- Do not commit `.env` files (they're in `.gitignore`)
- Do not add Windows-only or macOS-only code without a Linux equivalent
- Do not make OBD commands blocking without timeout handling
- Do not import from `open_mechanic` in `scripts/test_connection.py` (it's a standalone script)
- Do not add EV/Hybrid-specific logic in Phase 1-2
- Do not use merge commits or rebase merges (squash-merge only repo)
- Do not rely on OBD protocol auto-detection in production — always set OBD_PROTOCOL in .env
- See `docs/AGENT_WORKFLOWS.md` before changing provider selection, VIN enrichment, or agent-facing workflows
