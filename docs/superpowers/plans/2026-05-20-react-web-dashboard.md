# React Web Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `open-mechanic web`, an offline-capable FastAPI + React dashboard with gauges, status bars, graphs, DTCs, reports, and AI diagnosis output.

**Architecture:** FastAPI owns OBD, DTC, provider, report, and diagnosis logic through a focused dashboard service. React/Vite/TypeScript owns the browser UI and renders code-native SVG gauges, bars, and rolling line graphs from API responses. The first version exposes no web DTC clear endpoint.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, Pydantic, pytest, React, Vite, TypeScript, CSS, SVG.

---

## File Structure

- Create `src/open_mechanic/web/__init__.py`: web package marker.
- Create `src/open_mechanic/web/schemas.py`: Pydantic API contracts.
- Create `src/open_mechanic/web/service.py`: runtime connection state, sensor/DTC reads, provider status, report listing, and diagnosis adapter.
- Create `src/open_mechanic/web/app.py`: FastAPI app factory, API routes, static serving.
- Modify `src/open_mechanic/tools.py`: add `web` subcommand and uvicorn launcher.
- Modify `pyproject.toml`: include FastAPI/uvicorn in runtime or keep `api` extra and document command failure clearly; first implementation should move them to runtime because `open-mechanic web` is a primary optional GUI command.
- Create `tests/test_web_api.py`: backend API tests using offline mode and fake provider/service where needed.
- Create `frontend/`: Vite React app source.
- Create `src/open_mechanic/web/static/`: production build output placeholder and generated static files.
- Modify docs as needed after implementation.

## Task 1: Backend API Contracts

**Files:**
- Create: `src/open_mechanic/web/schemas.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Write failing schema/API import test**

```python
def test_web_schemas_importable():
    from open_mechanic.web.schemas import SensorResponse, StatusResponse

    status = StatusResponse(
        version="0.1.0",
        connected=False,
        port=None,
        protocol=None,
        provider_name="not configured",
        provider_configured=False,
        vehicle_profile=None,
        latest_poll_at=None,
    )
    sensors = SensorResponse(sensors=[])

    assert status.connected is False
    assert sensors.sensors == []
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_web_schemas_importable -v`
Expected: FAIL because `open_mechanic.web.schemas` does not exist.

- [ ] **Step 3: Implement schemas**

Create Pydantic models for status, sensor, DTC, reports, connection requests, vehicle profile requests, and diagnosis responses. Keep fields primitive and JSON-friendly.

- [ ] **Step 4: Run green test**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_web_schemas_importable -v`
Expected: PASS.

## Task 2: Dashboard Runtime Service

**Files:**
- Create: `src/open_mechanic/web/service.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Write failing offline service test**

```python
def test_dashboard_service_starts_disconnected_offline():
    from open_mechanic.web.service import DashboardService

    service = DashboardService(offline=True)

    status = service.get_status()
    assert status.connected is False
    assert service.get_sensors().sensors == []
    assert service.get_dtcs().dtcs == []
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_dashboard_service_starts_disconnected_offline -v`
Expected: FAIL because `DashboardService` does not exist.

- [ ] **Step 3: Implement service**

Implement `DashboardService` with offline-safe `get_status()`, `connect()`, `disconnect()`, `get_sensors()`, `get_dtcs()`, `list_reports()`, and `diagnose()`. Use existing `OBDConnection`, `SensorPoller`, `DTCReader`, `DiagnosticEngine`, and local profile/report paths.

- [ ] **Step 4: Run green test**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_dashboard_service_starts_disconnected_offline -v`
Expected: PASS.

## Task 3: FastAPI App

**Files:**
- Create: `src/open_mechanic/web/app.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Write failing API tests**

```python
def test_web_api_status_and_no_clear_route():
    from fastapi.testclient import TestClient
    from open_mechanic.web.app import create_app

    client = TestClient(create_app(offline=True))

    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json()["connected"] is False

    assert client.post("/api/clear-dtcs").status_code == 404
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_web_api_status_and_no_clear_route -v`
Expected: FAIL because `create_app` does not exist.

- [ ] **Step 3: Implement FastAPI app**

Create `create_app(offline: bool = False) -> FastAPI`, register the API routes, and mount static assets when present. Unknown frontend paths should return `index.html` only when a built frontend exists.

- [ ] **Step 4: Run green test**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_web_api_status_and_no_clear_route -v`
Expected: PASS.

## Task 4: CLI Web Command

**Files:**
- Modify: `src/open_mechanic/tools.py`
- Modify: `pyproject.toml`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Write failing CLI parser test**

```python
def test_web_command_help_is_registered(capsys):
    from open_mechanic.tools import main

    status = main(["web", "--help"])

    captured = capsys.readouterr()
    assert status == 0
    assert "--host" in captured.out
    assert "--offline" in captured.out
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_web_command_help_is_registered -v`
Expected: FAIL because the `web` command is not registered.

- [ ] **Step 3: Implement CLI command**

Add `web` parser with `--host`, `--port`, `--reload`, `--offline`, connection flags, and provider flag. Add `run_web_server(args)` that imports uvicorn lazily and starts `open_mechanic.web.app:create_app`.

- [ ] **Step 4: Run green test**

Run: `.venv/bin/python -m pytest tests/test_web_api.py::test_web_command_help_is_registered -v`
Expected: PASS.

## Task 5: React Dashboard Source

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/components/*.tsx`
- Create: `frontend/src/styles.css`

- [ ] **Step 1: Scaffold frontend**

Create a Vite React TypeScript app with scripts `dev`, `build`, and `preview`. Configure build output to `../src/open_mechanic/web/static`.

- [ ] **Step 2: Implement API client**

Add typed fetch helpers for `/api/status`, `/api/sensors`, `/api/dtcs`, `/api/diagnose`, and `/api/reports`.

- [ ] **Step 3: Implement visual components**

Add SVG `Gauge`, `StatusBar`, and `LineGraph` components. They must render empty states and populated numeric values without layout shift.

- [ ] **Step 4: Implement dashboard shell**

Build the Control-Room layout with left rail, main sensor/DTC workspace, right diagnosis panel, reports/settings views, and responsive mobile collapse.

- [ ] **Step 5: Run frontend build**

Run: `npm --prefix frontend run build`
Expected: PASS and writes files to `src/open_mechanic/web/static/`.

## Task 6: Verification

**Files:**
- Modify docs if command usage changed.

- [ ] **Step 1: Run backend tests**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 2: Run lint**

Run: `.venv/bin/python -m ruff check src tests scripts`
Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run: `npm --prefix frontend run build`
Expected: PASS.

- [ ] **Step 4: Start local web server**

Run: `.venv/bin/python -m open_mechanic web --offline --host 127.0.0.1 --port 8000`
Expected: server prints `http://127.0.0.1:8000` and serves the dashboard.

- [ ] **Step 5: Browser QA**

Open the dashboard, verify desktop and mobile responsive states, confirm gauges/status bars/graphs render, confirm no DTC clear UI exists, and confirm the app remains useful offline.
