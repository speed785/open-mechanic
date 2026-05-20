# React Web Dashboard Design

## Summary

Add a full React-style browser dashboard as an optional frontend GUI for open-mechanic. The dashboard runs from a local FastAPI server started by the Python CLI, uses the existing OBD, DTC, AI provider, report, and local profile code paths, and remains useful in offline mode when no adapter is connected.

The first web version is a control-room dashboard, not a marketing page or a desktop wrapper. It focuses on live diagnostics, clear status, visual sensor interpretation, and AI diagnosis output with the required informational disclaimer.

## Goals

- Add an `open-mechanic web` command that starts a local web server.
- Serve a React/Vite/TypeScript dashboard from the same local server for normal use.
- Support local frontend development with Vite during implementation.
- Show adapter, provider, and vehicle status prominently.
- Display live sensor data with gauges, status bars, and time-series graphs where data is available.
- Display DTCs and AI diagnosis output using the existing core logic.
- Preserve all safety rules: no hardcoded keys, no unsupported PID crashes, no web DTC clear path in the first version, and every diagnosis includes the existing disclaimer.

## Non-Goals

- Do not add EV or hybrid-specific logic.
- Do not add DTC clearing to the web dashboard.
- Do not add Electron, Tauri, or native desktop packaging.
- Do not replace the terminal tools or Textual dashboard.
- Do not build multi-vehicle garage/history management beyond showing saved local reports.

## User Experience

The first screen is the dashboard itself. It uses a dense, app-like layout:

- A left rail with Overview, Live Sensors, Fault Codes, AI Diagnosis, Reports, and Settings.
- A main workspace with vehicle context, adapter connection state, live sensor panels, DTC table, and graph area.
- A right-side diagnosis panel showing severity, summary, likely causes, repair steps, cost range, DIY feasibility, urgency, provider, cache state, and disclaimer.

The UI has two useful states:

- Offline/disconnected: The app loads, shows the saved profile if present, reports provider state, and uses empty or sample-safe visual states for sensors/DTCs.
- Connected: The app polls live sensors and DTCs through the Python backend, updates gauges, status bars, and graphs, and can run an AI diagnosis.

## Visual Components

Sensor visuals are grouped by diagnostic use:

- Gauges: RPM, speed, coolant temperature, engine load, throttle position, and module voltage use circular or semicircular gauges with current value, unit, and normal/warning/critical bands where generic ranges are safe.
- Status bars: fuel trims, voltage, temperature, and load show horizontal range bars with a marker and neutral/warning coloring.
- Graphs: key live sensors maintain a short rolling history in the browser, displayed as compact line graphs. The initial graph set is RPM, coolant temperature, module voltage, engine load, throttle position, short fuel trim, and long fuel trim.
- DTC status: fault-code rows show code, status, severity, category, and description. Empty state says no active codes are available rather than implying a complete professional inspection.

Generic visual thresholds are advisory display hints only. They must not replace AI diagnosis or professional mechanical advice.

## Backend Architecture

Add a web package under `src/open_mechanic/web/`:

- `app.py`: FastAPI app factory and static frontend serving.
- `service.py`: dashboard runtime state, OBD connection lifecycle, latest snapshots, and report lookup.
- `schemas.py`: Pydantic request/response models for the HTTP API.
- `__init__.py`: package marker.

The runtime service owns one optional OBD connection and poller. It exposes snapshots to request handlers without duplicating core OBD logic.

Initial API endpoints:

- `GET /api/status`: returns app version, connection status, port, protocol, provider name/configuration state, saved vehicle profile, and latest polling time.
- `POST /api/connect`: connects or reconnects using optional port, protocol, baudrate, timeout, and offline flag.
- `POST /api/disconnect`: disconnects the adapter.
- `GET /api/sensors`: returns the latest sensor snapshot.
- `GET /api/dtcs`: returns current DTCs.
- `POST /api/diagnose`: runs the existing diagnostic engine using a request profile and the latest DTC/sensor context. It injects no disclaimer itself; it relies on `DiagnosticEngine`, which is the required central enforcement point.
- `GET /api/reports`: lists local diagnosis report JSON files written under `local_data/sessions`.

The web backend does not expose `clear_dtcs()`.

## Frontend Architecture

Add a `frontend/` workspace:

- React + Vite + TypeScript.
- Components organized by feature: shell/navigation, status header, sensors, DTCs, diagnosis, reports, settings.
- CSS is local to the app and uses a small token system for color, spacing, radius, and typography.
- Charting should use code-native SVG React components for the first version. This avoids adding a frontend chart dependency while keeping gauges, status bars, and rolling line graphs testable and easy to package.

The production build is written to `src/open_mechanic/web/static/` and served by FastAPI.

## CLI Integration

Add a `web` subcommand to the existing CLI:

```bash
open-mechanic web --offline
open-mechanic web --protocol 6
open-mechanic web --host 127.0.0.1 --port 8000
```

The command starts uvicorn with the FastAPI app. It should print the local URL clearly. Browser auto-open is optional and should not be required.

## Error Handling

- Unsupported PIDs remain non-fatal and are displayed as unavailable.
- Adapter connection failures return structured API errors and keep the dashboard in disconnected mode.
- Provider configuration failures are shown in status and diagnosis views.
- VIN enrichment failures, if used by diagnosis, remain non-fatal.
- API handlers should return actionable messages without exposing secrets.

## Testing

Backend tests:

- App starts in offline mode.
- `/api/status` returns disconnected status without hardware.
- `/api/sensors` and `/api/dtcs` return empty lists/objects offline.
- `/api/diagnose` validates required profile fields and preserves the diagnosis disclaimer in responses when using a fake provider.
- No API route exposes DTC clearing.

Frontend checks:

- `npm run build` succeeds.
- The dashboard renders offline with no overlapping critical text at desktop and mobile widths.
- Gauges, status bars, and graphs render with empty and populated data.

Repository verification remains:

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m ruff check src tests scripts
```

Frontend verification adds:

```bash
npm --prefix frontend run build
```

## Packaging Decision

The first implementation keeps the React source in `frontend/` and writes the production build to `src/open_mechanic/web/static/`. During local development, Vite can proxy API requests to the FastAPI server, but the user-facing `open-mechanic web` command serves the built static assets from the Python package.
