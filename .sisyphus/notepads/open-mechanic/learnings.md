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
