# Mechanic Web Console Design

## Summary

Improve the local `open-mechanic web` experience from a generic dashboard into a mechanic/engineer diagnostic console. The app should run from a single terminal command with a GUI by default when possible, also support a no-GUI terminal/server mode, clearly distinguish offline/disconnected/connected adapter states, and make the browser surface useful for real diagnostic work: connection readiness, fault triage, live evidence, AI diagnosis, and report review.

This spec targets the local web app in `frontend/` and `src/open_mechanic/web/`. The public marketing site in `website/` is out of scope unless later work needs copy updates to describe the finished local app.

## Goals

- Replace the low-value left-side button rail with a workflow-oriented diagnostic run surface.
- Make `open-mechanic web` feel like one local app launch rather than asking the user to manage a separate frontend server.
- Add an explicit `--no-gui` mode that keeps the same local runtime available without opening a browser.
- Preserve `--offline` so the app can run without trying to connect to an OBD adapter.
- Clearly distinguish UI mode from adapter mode: GUI/no-GUI controls whether a browser opens; offline/disconnected/connected controls whether the vehicle adapter is being used.
- Keep terminal-first tools intact: `open-mechanic dashboard`, direct read-only tools, and AI diagnosis CLI remain available.
- Make the web app useful to mechanics by centering active faults, likely next action, diagnosis, repair steps, cost range, and saved reports.
- Make the web app useful to engineers by exposing adapter/protocol/port state, provider readiness, polling freshness, raw sensor values, unsupported PID state, and diagnostic evidence.
- Preserve safety constraints: no hardcoded API keys, no web DTC clear path in this pass, unsupported PIDs do not crash the app, and every AI diagnosis response includes the central `DiagnosticEngine` disclaimer.

## Non-Goals

- Do not add DTC clearing to the web UI.
- Do not add EV or hybrid-specific logic.
- Do not add Electron, Tauri, or native desktop packaging.
- Do not replace Textual dashboard behavior.
- Do not build full shop management, multi-customer history, invoicing, or cloud sync.
- Do not require internet access for offline/disconnected dashboard rendering.

## Runtime And Connectivity Model

The app has two independent mode axes:

- **Presentation mode:** GUI or no-GUI. GUI opens the local browser interface. No-GUI starts the same local runtime and prints the URL/API endpoint without opening a browser.
- **Adapter mode:** offline, disconnected, connecting, connected, or error. Offline means the user explicitly chose not to attempt hardware access. Disconnected means hardware is not currently connected but the app can still run. Connected means the adapter connection is active and live OBD data can be polled.

These states must not be conflated. `--no-gui` does not mean offline. `--offline` does not mean no GUI. A user can run any combination:

- `open-mechanic web`: start the local runtime, attempt adapter connection using defaults/env vars, and open GUI when possible.
- `open-mechanic web --no-gui`: start the local runtime, attempt adapter connection, print URL, and do not open a browser.
- `open-mechanic web --offline`: start the local runtime, skip adapter connection, and open GUI when possible.
- `open-mechanic web --offline --no-gui`: start the local runtime, skip adapter connection, print URL, and do not open a browser.

The browser UI should display the adapter state explicitly. It should show "Offline mode" only when the user requested offline mode. If the user did not request offline mode but no adapter is connected, it should show "Disconnected" or "Adapter not connected" with a reconnect action.

## User Experience

The default page is a single "Diagnostic Run" workspace rather than a set of side-nav pages. It should answer five questions quickly:

1. Is the adapter connected and polling?
2. Is the AI provider configured?
3. Are there active fault codes?
4. What evidence supports the diagnosis?
5. What should the mechanic inspect, repair, or export next?

The top command area shows vehicle/profile label, adapter state, protocol, port, AI provider state, latest poll time, and run controls. Controls include connecting/reconnecting, explicitly switching offline mode through the backend request, running diagnosis, and refreshing reports. The command area should stay compact and utility-focused.

The main page is organized into four zones:

- **Fault Triage:** DTC rows with code, severity, category, status, description, and empty/unavailable states. This zone should not imply the vehicle is professionally cleared when no codes are returned.
- **Live Evidence:** grouped sensors for powertrain, thermal, electrical, and fuel/air data. Each group shows compact current values, units, support state, and short rolling trends for high-signal sensors.
- **AI Diagnosis:** current diagnosis state, run button, severity, summary, likely causes, repair steps, cost range, DIY feasibility, urgency, provider/cache state, and mandatory disclaimer.
- **Reports:** saved JSON diagnosis reports with timestamp, vehicle, severity, provider, summary, and local path metadata.

The layout should feel like a diagnostic console, not a marketing page. Use dense but readable panels, tables, status strips, and compact visualizations. Avoid a decorative card grid and avoid hiding core information behind navigation where possible.

## Terminal Behavior

`open-mechanic web` should start the local FastAPI runtime and print a clear URL. By default it may open the user's browser after the server starts. Browser opening must be best-effort and non-fatal.

The user should not need to run a separate Vite server for normal use. The production frontend is built into `src/open_mechanic/web/static/` and served by the Python runtime. Vite remains a development-only tool.

`open-mechanic web --no-gui` starts the same local runtime and prints the URL, but must not open a browser. This is useful for remote terminals, SSH sessions, scripts, or users who want to copy the URL manually.

`open-mechanic web --offline` starts without attempting an OBD adapter connection. It should still serve the GUI unless `--no-gui` is also set.

`open-mechanic web --offline --no-gui` starts a disconnected API/static server only and prints the URL.

The terminal command should not block startup on browser opening. If browser launch fails, the command should continue serving the app and print the URL.

If a future top-level launcher is added, it can map to these same modes:

```bash
open-mechanic run --gui
open-mechanic run --no-gui
open-mechanic run --offline --gui
```

That launcher is optional for this pass. The required behavior is the `web` subcommand mode split.

## Backend Architecture

Keep the existing `src/open_mechanic/web/` package:

- `app.py`: FastAPI app factory and static frontend serving.
- `service.py`: dashboard runtime state, OBD lifecycle, latest polling, diagnosis, report lookup.
- `schemas.py`: Pydantic request/response models.

Extend the backend only where it directly supports the workflow console:

- Ensure `/api/status` contains enough readiness data for the top command area: app version, connected state, explicit offline mode, adapter state, port, protocol, provider name/configured state, saved profile, and latest poll time.
- Continue exposing `/api/connect`, `/api/disconnect`, `/api/sensors`, `/api/dtcs`, `/api/diagnose`, and `/api/reports`.
- If the frontend needs to run diagnosis, add a typed frontend client method for `POST /api/diagnose`; the backend endpoint already exists.
- Connection failures should return structured `ok=false` messages through the existing message response instead of crashing the server.
- Provider configuration failure should remain visible in status and diagnosis states.
- Status should expose enough information for the frontend to distinguish explicit offline mode from disconnected adapter state.

The web backend must not expose `clear_dtcs()`.

### Live Updates

A WebSocket is not required for the first useful version. The app currently polls HTTP endpoints, which is adequate for status, DTCs, reports, and low-frequency dashboard refresh. To make the app feel more seamless without adding bidirectional complexity, prefer one of these paths:

1. **Initial implementation:** keep HTTP polling, but make state labels accurate and refresh immediately after connect/disconnect/diagnosis actions.
2. **Optional live stream enhancement:** add a server-sent events endpoint such as `GET /api/events` for status/sensor/DTC updates. SSE fits this app because most live updates flow from Python to the browser, while user actions can remain normal HTTP POST requests.

Use a full WebSocket only if the UI later needs bidirectional streaming commands, continuous low-latency control, or richer session coordination. For this pass, accurate states plus immediate HTTP refresh are sufficient, and SSE is the preferred upgrade if polling feels rough.

## Frontend Architecture

Keep React + Vite + TypeScript in `frontend/`, packaged into `src/open_mechanic/web/static/` for production serving.

The app should use focused local components:

- `CommandHeader`: vehicle, adapter, protocol, provider, poll state, and primary controls.
- `FaultTriage`: DTC table and empty/unavailable states.
- `EvidencePanel`: grouped sensor readings, support status, compact trends, and raw values.
- `DiagnosisPanel`: diagnosis form/run action and result rendering.
- `ReportsPanel`: saved reports list.
- Existing `Gauge`, `LineGraph`, and `StatusBar` components may be reused where they serve the evidence view.

The frontend should keep local rolling sensor history in browser state. It should not invent a connected state when the backend is offline or disconnected. Demo values may be used for visual empty-state scaffolding only when clearly labeled as offline preview data.

The UI should be responsive:

- Desktop: top command header, main diagnostic workspace, right-side diagnosis/report column if space allows.
- Tablet/mobile: command header first, then fault triage, diagnosis, evidence, and reports in a single-column order.

## Data Flow

Startup:

1. Frontend calls `/api/status`, `/api/sensors`, `/api/dtcs`, and `/api/reports`.
2. It updates readiness, explicit adapter state, evidence, triage, and report zones.
3. It repeats status/sensor/DTC polling on an interval while mounted.

Connection:

1. User clicks connect or offline mode control.
2. Frontend posts to `/api/connect`.
3. Frontend immediately refreshes status, sensors, and DTCs.
4. If the backend returns `ok=false`, the top command area shows the message and remains usable.
5. If the backend is in explicit offline mode, the top command area says offline mode rather than disconnected.

Diagnosis:

1. User runs diagnosis from the diagnosis zone.
2. Frontend sends a `DiagnosisRequest` using the saved profile when available.
3. Backend gathers current DTC and sensor context through `DashboardService`.
4. `DiagnosticEngine` returns the normalized `DiagnosisResult` with mandatory disclaimer.
5. Frontend renders result and keeps the disclaimer visible.

Reports:

1. Frontend calls `/api/reports`.
2. Reports render as a compact work history list.
3. Report reading/export can remain a later enhancement if the current backend only lists report summaries.

## Error Handling

- Unsupported PIDs display as unsupported/unavailable and never break rendering.
- Empty DTC responses display "No active fault codes returned" or equivalent wording, not "vehicle cleared".
- Explicit offline mode displays offline mode. A failed or missing OBD adapter displays disconnected/error state with a clear message.
- API fetch errors show a compact error banner while retaining the last known local state.
- Missing AI provider disables or warns on diagnosis actions, but does not prevent sensor/DTC use.
- Browser auto-open failure is printed to the terminal and does not stop the web server.

## Testing

Backend tests should cover:

- `open-mechanic web --help` exposes `--offline`, `--host`, and `--no-gui`.
- No web API route exposes DTC clearing.
- Offline app status returns disconnected state plus explicit offline mode.
- Diagnosis response preserves `DiagnosticEngine` disclaimer with a fake provider.
- Browser opener logic is skipped when `--no-gui` is set and non-fatal when it fails.
- Status schema/service distinguishes explicit offline mode from disconnected adapter state.

Frontend checks should cover:

- `npm --prefix frontend run build` succeeds.
- The offline dashboard renders without relying on live hardware.
- The diagnosis action has a typed API client path to `POST /api/diagnose`.
- Desktop and mobile layouts avoid overlapping text and keep workflow zones visible.

Repository verification:

```bash
.venv/bin/python -m pytest tests/ -v
.venv/bin/python -m ruff check src tests scripts
npm --prefix frontend run build
```

## Acceptance Criteria

- A user can run `open-mechanic web --offline --no-gui` and get a local server URL without any browser launch attempt.
- A user can run `open-mechanic web --offline` and get the local web app in explicit offline mode.
- A user can run `open-mechanic web --protocol 6` and the command still attempts adapter connection through existing backend service logic.
- A user can run `open-mechanic web --no-gui --protocol 6` and still attempt adapter connection without opening a browser.
- The UI distinguishes explicit offline mode from adapter disconnected/error states.
- The browser app no longer depends on the side rail as its primary structure.
- The browser app shows adapter readiness, AI provider readiness, fault triage, live evidence, AI diagnosis, and reports in one coherent workflow.
- Mechanics can see fault codes, diagnosis, likely causes, repair steps, cost range, urgency, and saved report context.
- Engineers can see port/protocol, latest poll time, raw sensor values, support state, and provider/configuration state.
- No web route clears DTCs.
- AI diagnosis output shown in the web app includes the required disclaimer.
