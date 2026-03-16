# Decisions — open-mechanic

## Architecture Decisions

### OBD Library: python-obd
- Chosen over raw pyserial for higher-level abstraction
- Handles ELM327 protocol negotiation automatically
- Auto-detects port and baudrate
- Has built-in command definitions for all standard OBD-II PIDs

### Database: SQLAlchemy + SQLite
- SQLite for dev/self-hosted simplicity
- SQLAlchemy ORM for future PostgreSQL migration path
- Session-based logging (one DiagnosticSession per connection)

### AI Model: claude-sonnet-4-5
- Good balance of capability and cost for diagnostic tasks
- Structured JSON output via prompt engineering (not tool use)
- Local cache for repeated DTC sets (24h TTL) to reduce API costs

### DTC Data: Local JSON file
- `data/dtc_codes.json` for offline lookup
- Avoids API calls for known codes
- Community-extensible

### Cross-Platform Support: Phase 1 (not deferred)
- `python-obd` is already cross-platform — no extra work at the OBD protocol layer
- Only `connection.py` needs platform awareness: `get_default_port()` + `scan_ports()` using `platform.system()` + `glob`
- Docs split into `docs/SETUP_LINUX.md`, `docs/SETUP_MACOS.md`, `docs/SETUP_WINDOWS.md`
- Primary dev/test platform: Linux (OBDLink EX on `/dev/ttyUSB0`)
- Windows COM port auto-detection is unreliable → recommend `OBD_PORT` env var override

### Phase 1 Build Order (dependency-driven)
1. SCAFFOLD (everything depends on this)
2. connection.py + db/models.py + dtc_codes.json (parallel — independent)
3. reader.py + dtc.py (parallel — both depend on connection.py)
4. test_connection.py (depends on reader + dtc)
5. ai/prompts.py (depends on data structures from reader + dtc)
6. ai/diagnose.py (depends on prompts.py)
