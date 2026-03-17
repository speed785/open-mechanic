# Learnings — open-mechanic

## Project Conventions

- Package name: `open_mechanic` (underscore, not hyphen)
- Source layout: `src/open_mechanic/` (src layout, not flat)
- Python 3.11+
- OBD library: `python-obd` (import as `obd`)
- AI model: `claude-sonnet-4-5` (configurable via env)
- Database: SQLite for dev, path configurable via `DB_PATH` env var

## Cross-Platform Port Detection

Hardware: OBDLink EX FORScan USB adapter (FTDI chip on all platforms)

| Platform | Default port | Port pattern | Driver needed |
|----------|-------------|--------------|---------------|
| Linux | `/dev/ttyUSB0` | `/dev/ttyUSB*` | None (built-in FTDI) |
| macOS | `/dev/cu.usbserial-*` | `/dev/cu.usbserial-*`, `/dev/tty.usbserial-*` | FTDI VCP driver (ftdichip.com) OR native on macOS 12+ |
| Windows | `COM3` (varies) | `COM*` | FTDI CDM driver (ftdichip.com) |

Use `platform.system()` → `"Linux"`, `"Darwin"` (macOS), `"Windows"`.
Use `glob.glob()` for macOS port scanning.
`python-obd`'s `obd.OBD()` auto-detects on all platforms — our `scan_ports()` is a fallback/helper.

## Linux-specific

- User needs `dialout` group: `sudo usermod -a -G dialout $USER` then re-login
- OBDLink EX shows as `/dev/ttyUSB0` (FTDI USB Serial Device)

## macOS-specific

- FTDI VCP driver: https://ftdichip.com/drivers/vcp-drivers/
- macOS 12+ may have native FTDI support (no driver needed)
- Port shows as `/dev/cu.usbserial-XXXXXXXX` (cu = call-up, preferred over tty)

## Windows-specific

- FTDI CDM driver: https://ftdichip.com/drivers/vcp-drivers/
- Port shows as `COM3`, `COM4`, etc. — check Device Manager
- User should set `OBD_PORT=COM3` in `.env` (auto-detection less reliable on Windows)

## Critical Rules

- **NEVER clear DTC codes without `confirmed=True` explicit parameter** — raise `DTCClearNotConfirmed` exception
- **Always inject disclaimer** into AI diagnostic output: "informational only, not professional advice"
- **Handle unsupported PIDs gracefully** — not all cars support all OBD-II commands, skip silently
- **EV/Hybrid**: out of scope for Phase 1+2, document as future module

## Hardware Context

- OBDLink EX USB: FTDI chip, shows as `/dev/ttyUSB0`, no extra Linux drivers needed
- User may need: `sudo usermod -a -G dialout $USER` for serial port access
- Generic ELM327 USB adapters also work for standard OBD-II

## Dependencies (pyproject.toml)

- `obd` — python-obd library
- `pyserial` — serial communication
- `anthropic` — Claude API SDK
- `fastapi` — REST backend (Phase 3)
- `sqlalchemy` — ORM + SQLite
- `rich` — CLI output
- `python-dotenv` — env var loading
- `pydantic` — data validation

## Scaffolding Completed (Phase 1)

Files created:
- `pyproject.toml` — hatchling build, src layout, all deps pinned
- `.gitignore` — Python + project-specific (data/*.db, .env, logs/)
- `.env.example` — ANTHROPIC_API_KEY, OBD_PORT, OBD_BAUDRATE, DB_PATH
- `LICENSE` — MIT 2026, open-mechanic contributors
- `src/open_mechanic/__init__.py` — __version__ = "0.1.0", __all__ = []
- `src/open_mechanic/__main__.py` — minimal CLI stub, Phase 3 placeholder
- `src/open_mechanic/ai/__init__.py` — subpackage docstring
- `src/open_mechanic/api/__init__.py` — subpackage docstring
- `src/open_mechanic/db/__init__.py` — subpackage docstring
- `scripts/.gitkeep`, `data/.gitkeep` — directory placeholders
- `tests/__init__.py` — empty
- `docs/SETUP_LINUX.md` — dialout group, dmesg detection, troubleshooting
- `docs/SETUP_MACOS.md` — FTDI VCP driver, cu.usbserial-* detection
- `docs/SETUP_WINDOWS.md` — FTDI CDM driver, Device Manager COM port, OBD_PORT required

## pyproject.toml Notes

- Entry point: `open-mechanic = "open_mechanic.__main__:main"`
- Optional extras: `[dev]` (pytest, ruff, mypy) and `[api]` (fastapi, uvicorn)
- Wheel target: `packages = ["src/open_mechanic"]`
- ruff: line-length=100, selects E/F/I/UP/B/SIM

## Connection Module Implementation Notes (2026-03-16)

- Implemented src/open_mechanic/connection.py with ConnectionStatus, get_default_port, scan_ports, and OBDConnection.
- Port resolution order: explicit port argument, OBD_PORT environment variable, first scan_ports result, then get_default_port fallback.
- connect() uses obd.OBD(..., check_voltage=False) and retry backoff delays of 0.5s, 1.0s, and 2.0s with INFO/WARNING/ERROR logging.
- scan_ports behavior: Linux scans /dev/ttyUSB* and /dev/ttyACM*, macOS scans /dev/cu.usbserial-* and /dev/tty.usbserial-*, Windows uses serial.tools.list_ports.comports().
- Module loads dotenv at import time so OBD_PORT is available before connection resolution.

## db/models.py — SQLAlchemy 2.0 ORM (implemented 2026-03-17)

- Use `from sqlalchemy import Engine` at top level — do NOT use quoted forward refs or local imports for `Engine`; it's available in SQLAlchemy 2.0 top-level namespace.
- `Generator` must come from `collections.abc`, not `typing` — ruff UP035 enforces this for Python 3.11+.
- `os.getenv("DB_PATH", "data/sessions.db")` returns `str | None` even with a default (mypy sees it that way); use `os.getenv("DB_PATH") or "data/sessions.db"` to get a clean `str`.
- `from __future__ import annotations` enables `str | None` union syntax in `Mapped[]` without issues on 3.11.
- `mapped_column(default=datetime.utcnow)` (no call parens) is correct SQLAlchemy 2.0 style for callable defaults.
- `Base.metadata.create_all(engine)` is idempotent — safe to call on every `init_db()` invocation.

## data/dtc_codes.json (2026-03-17)
- Created with 522 DTC codes (well above 150 minimum)
- Used Python script to generate + validate in one pass — avoids mcp_write size limits
- Coverage: P0xxx (powertrain), B0xxx (body), C0xxx (chassis), U0xxx (network)
- Category breakdown: sensors(63), transmission(64), engine(60), chassis(50), network(200), evap(20), body(20), emissions(19), fuel(13), ignition(9), electrical(4)
- Severity breakdown: warning(401), info(63), critical(58)
- All entries validated: correct fields, valid severity/category values, no duplicates
- File loaded by dtc.py via: json.load(open("data/dtc_codes.json"))

## reader.py implementation notes (2026-03-17)

- Implemented `SensorValue` dataclass and `SENSOR_COMMANDS` ordered polling list in `src/open_mechanic/reader.py`.
- `SensorPoller.get_snapshot()` returns `{}` when raw OBD connection is missing or disconnected, matching `OBDConnection.get_connection() -> obd.OBD | None` behavior.
- Unsupported command names are skipped silently when not present in `obd.commands`; per-command query failures are caught and mapped to `supported=False` with `value="N/A"`.
- Null/empty responses (`None` or `response.is_null()`) are represented as `SensorValue(..., supported=False)` without raising.
- Polling loop uses a daemon `threading.Thread`, calls callback on each snapshot, sleeps by configured interval, and `stop_polling()` joins with a 5s timeout.

## dtc.py implementation notes (2026-03-17)

- Implemented `src/open_mechanic/dtc.py` with `DTCCode` dataclass, `DTCReader`, and mandatory `DTCClearNotConfirmed` safety exception.
- `DTCReader` loads `data/dtc_codes.json` into an uppercase-keyed in-memory map and falls back to an empty DB with warning logs when missing/invalid.
- `get_dtcs()` queries both `obd.commands.GET_DTC` (confirmed) and `obd.commands.GET_CURRENT_DTC` (pending), decodes from local DB, deduplicates by code with confirmed overriding pending, and returns sorted results.
- `decode(code)` normalizes lookup with `code.upper()` and returns unknown placeholders when code metadata is missing.
- `clear_dtcs(confirmed=False)` hard-fails unless `confirmed is True`, then issues `obd.commands.CLEAR_DTC`, returning `True` on successful query and `False` on connection/query failure.

## scripts/test_connection.py implementation notes (2026-03-17)

- Standalone script — no `open_mechanic` package imports, uses `python-obd` and `rich` directly.
- `logging.getLogger("obd").setLevel(logging.CRITICAL)` suppresses python-obd's internal connection error logs (e.g. "could not open port") — must be placed AFTER all imports to avoid ruff E402.
- `# pyright: reportMissingTypeStubs=false` and `# pyright: reportAttributeAccessIssue=false` pragmas needed because python-obd has no type stubs — `obd.OBD.supportedCommands`, `obd.commands.GET_DTC`, etc. are all untyped.
- pint Quantity values from `response.value` need `hasattr(value, "magnitude")` guard AND `value is not None` check to satisfy pyright.
- Port detection logic duplicated from `connection.py` (intentional — standalone constraint). Uses `glob.glob` for Linux/macOS, `serial.tools.list_ports` for Windows.
- DTC lookup: loads `data/dtc_codes.json` via `Path(__file__).parent.parent / "data" / "dtc_codes.json"` — works regardless of cwd.
- Script exits with code 0 even when no adapter found — graceful degradation is the design intent.
- `--timeout` default is 10s (shorter than production 30s) for quick testing UX.

## prompts.py (ai/prompts.py) — implemented

- `DIAGNOSTIC_SYSTEM_PROMPT`: module-level string constant; instructs Claude to return ONLY valid JSON, defines severity/urgency enums, mandates disclaimer text, instructs conservative severity escalation and graceful handling of N/A sensors.
- `format_sensor_snapshot(snapshot)`: accepts `dict[str, Any]` — handles both `SensorValue` dataclass (via `hasattr(sensor, "supported")`) and plain dicts. Shows `"N/A (unsupported)"` when `supported=False` or value is `"N/A"`.
- `format_diagnostic_prompt(vehicle, dtcs, snapshot)`: assembles user message. VIN line only included if `vehicle.vin is not None`. DTC section shows count in header; falls back to `"Fault Codes: None"`. Calls `format_sensor_snapshot` internally.
- No `anthropic` import — pure string formatting module.
- `# type: ignore[assignment]` needed on `sensor.unit` because mypy can't infer the attribute type from `hasattr` guard alone.
- `ruff`, `mypy --ignore-missing-imports`, and import smoke test all pass.
- 2026-03-17: Implemented ai/diagnose.py with DiagnosticEngine using Anthropic Messages API, deterministic in-memory cache key (vehicle + sorted DTCs), 24h TTL validation, JSON fence stripping, safe default parsing, and mandatory DISCLAIMER override on every DiagnosisResult path (success + JSON fallback).
