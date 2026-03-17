# open-mechanic — Build Plan

> AI-powered OBD-II car diagnostics platform. Phase 1 + Phase 2 implementation.
> Context: See OPEN_MECHANIC_PROJECT.md for full project context, hardware decisions, and architecture.
> Hardware: OBDLink EX FORScan USB adapter. Primary dev platform: Linux. Cross-platform (macOS, Windows) supported from Phase 1.

---

## Phase 1: Foundation

- [x] **[SCAFFOLD]** Create project scaffolding: `pyproject.toml` (python-obd, pyserial, anthropic, fastapi, sqlalchemy, rich, python-dotenv, pydantic deps; Python 3.11+; cross-platform markers where needed), full directory structure (`src/open_mechanic/`, `src/open_mechanic/ai/`, `src/open_mechanic/api/`, `src/open_mechanic/db/`, `scripts/`, `data/`, `docs/`), `LICENSE` (MIT), `.gitignore`, `.env.example` (ANTHROPIC_API_KEY, OBD_PORT, OBD_BAUDRATE, DB_PATH), all `__init__.py` files, `docs/SETUP_LINUX.md` + `docs/SETUP_MACOS.md` + `docs/SETUP_WINDOWS.md` with platform-specific driver and port instructions

- [x] **[CONNECTION]** Implement `src/open_mechanic/connection.py` — OBD connection management with full cross-platform support. `get_default_port() -> str` uses `platform.system()` to return the right default: Linux → `/dev/ttyUSB0`, macOS → first match of `/dev/cu.usbserial-*` or `/dev/tty.usbserial-*` (use `glob`), Windows → `COM3` (fallback, user should override via env). `scan_ports() -> list[str]` scans platform-appropriate patterns. `OBDConnection` class: auto-detect port from env `OBD_PORT` → `scan_ports()` → platform default, configurable baudrate, connection status enum (CONNECTED/DISCONNECTED/CONNECTING), reconnect with exponential backoff (max 3 attempts), context manager (`with OBDConnection() as conn:`), `is_connected()`, `get_status()`, `get_port()`, `disconnect()`. Use `python-obd` library. Log connection events with platform info.

- [x] **[DB]** Implement `src/open_mechanic/db/models.py` — SQLAlchemy models with SQLite: `VehicleProfile` (id, year, make, model, mileage, vin), `DiagnosticSession` (id, vehicle_id, started_at, ended_at, port_used), `SensorReading` (id, session_id, timestamp, sensor_name, value, unit), `DTCRecord` (id, session_id, timestamp, code, description, status[pending/confirmed]), `DiagnosisResult` (id, session_id, timestamp, severity, summary, raw_json). Include `init_db()` function and `get_session()` context manager.

- [x] **[DTC-DATA]** Create `data/dtc_codes.json` — offline DTC reference database. Include at minimum 150+ common codes across: P0xxx (powertrain generic), P1xxx (powertrain manufacturer), B0xxx (body), C0xxx (chassis), U0xxx (network). Each entry: `{"code": "P0420", "description": "Catalyst System Efficiency Below Threshold (Bank 1)", "severity": "warning", "category": "emissions"}`. Cover the most common real-world codes (O2 sensors, catalytic converter, MAF, throttle, transmission, ABS, EVAP system).

- [x] **[READER]** Implement `src/open_mechanic/reader.py` — live sensor data polling. Depends on `connection.py`. Sensors to poll: RPM, SPEED, COOLANT_TEMP, INTAKE_TEMP, MAF, THROTTLE_POS, O2_B1S1, O2_B1S2, FUEL_TRIM_SHORT_B1, FUEL_TRIM_LONG_B1, CONTROL_MODULE_VOLTAGE, ENGINE_LOAD, TIMING_ADVANCE. `SensorPoller` class with configurable interval (default 1s), `get_snapshot() -> dict[str, SensorValue]`, `start_polling(callback)`, `stop_polling()`. Handle unsupported sensors gracefully (not all cars support all PIDs). `SensorValue` dataclass with `name`, `value`, `unit`, `timestamp`.

- [x] **[DTC]** Implement `src/open_mechanic/dtc.py` — DTC code reading + decoding. Depends on `connection.py` and `data/dtc_codes.json`. `DTCReader` class: `get_dtcs() -> list[DTCCode]` (reads both pending + confirmed), `decode(code: str) -> DTCInfo` (local lookup from dtc_codes.json, fallback to code only), `clear_dtcs(confirmed: bool = False) -> bool` — MUST require `confirmed=True` explicitly, raise `DTCClearNotConfirmed` exception otherwise. `DTCCode` dataclass: `code`, `description`, `status`, `severity`, `category`.

- [x] **[TEST-SCRIPT]** Write `scripts/test_connection.py` — standalone adapter test script using `rich` for output. Shows: detected OS + expected port pattern, connection attempt with spinner, connection status (port, baudrate, protocol), list of supported commands count, live snapshot of all readable sensors in a rich Table, current DTC codes (or "No fault codes" message), total test duration. Should work without a car connected (graceful degradation with clear "no vehicle detected" message). Accepts optional `--port` CLI arg to override auto-detection (useful on Windows where COM port may vary). No imports from `open_mechanic` package needed — can use `python-obd` directly for simplicity.

---

## Phase 2: AI Diagnostics

- [x] **[PROMPTS]** Implement `src/open_mechanic/ai/prompts.py` — prompt templates. `format_diagnostic_prompt(vehicle: VehicleProfile, dtcs: list[DTCCode], snapshot: dict) -> str`. Include: vehicle context block, DTC codes with descriptions, sensor snapshot formatted as key-value pairs, JSON output schema enforcement, disclaimer instruction ("include a note that this is informational only"). `DIAGNOSTIC_SYSTEM_PROMPT` constant. `format_sensor_snapshot(snapshot: dict) -> str` helper.

- [x] **[DIAGNOSE]** Implement `src/open_mechanic/ai/diagnose.py` — Claude API integration. `DiagnosticEngine` class: `__init__(api_key: str, model: str = "claude-sonnet-4-5")`, `diagnose(vehicle, dtcs, snapshot) -> DiagnosisResult`. Use `anthropic` Python SDK. Parse and validate JSON response against schema: `{severity, summary, likely_causes[], repair_steps[], estimated_cost_usd{low,high}, diy_feasible, diy_difficulty, urgency}`. Handle API errors gracefully (rate limit, auth, network). Local cache: if same DTC set seen before within 24h, return cached result. Always inject disclaimer into result. `DiagnosisResult` dataclass with all schema fields.

---

## Phase 3: Interface (Future)

- [ ] **[CLI]** Rich CLI entry point with color-coded severity output, vehicle profile setup wizard, diagnose command, history command
- [ ] **[API]** FastAPI backend: `GET /api/vehicle`, `GET /api/live` (SSE), `GET /api/dtc`, `POST /api/diagnose`, `GET /api/history`, `GET /api/guides/{dtc}`
- [ ] **[FRONTEND]** React + Tailwind dashboard: live sensor display, DTC history, diagnosis viewer, repair guide renderer

---

## Phase 4: Community (Future)

- [ ] **[RELEASE]** Public open-source release: CONTRIBUTING.md, issue templates, GitHub Actions CI
- [ ] **[COMMUNITY-DB]** Community DTC database with crowdsourced repair success stories
- [ ] **[MANUFACTURER]** Ford extended PIDs module (OBDLink EX MS-CAN), then VW/BMW
- [ ] **[SAAS]** Optional SaaS hosted tier ($9.99/mo)
