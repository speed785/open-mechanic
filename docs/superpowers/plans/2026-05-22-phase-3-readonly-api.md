# Phase 3 Read-Only API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a read-only FastAPI backend foundation for open-mechanic Phase 3.

**Status:** Implemented and verified on 2026-05-22. The API foundation, service layer, tests, CI install alignment, and docs are complete.

**Architecture:** Add an API package with Pydantic response schemas, a dependency-injected service layer, and a FastAPI app factory. Hardware and AI calls stay behind service methods so endpoint tests use fake services and do not require an OBD adapter or Anthropic credentials.

**Tech Stack:** FastAPI, Pydantic v2, pytest, FastAPI TestClient, existing `open_mechanic` connection/reader/DTC/AI modules.

---

## File Structure

- Create `src/open_mechanic/api/schemas.py`: response and request models for API contracts.
- Create `src/open_mechanic/api/services.py`: `DiagnosticAPIService` with read-only methods for vehicle profile, live sensors, DTCs, health snapshot, and AI diagnosis.
- Create `src/open_mechanic/api/app.py`: `create_app()` and routes under `/api`.
- Modify `src/open_mechanic/api/__init__.py`: export `create_app`.
- Create `tests/test_api_app.py`: endpoint tests using a fake service.
- Create `tests/test_api_services.py`: service behavior tests with mocked OBD/AI dependencies.
- Modify `pyproject.toml`: make test/dev workflows install FastAPI/TestClient support.
- Modify `.github/workflows/ci.yml`: install `.[dev,api]` for tests.
- Modify README/docs: document API run commands and current endpoints.

## Task 1: API Schemas

**Files:**
- Create: `src/open_mechanic/api/schemas.py`
- Test: `tests/test_api_app.py`

- [ ] **Step 1: Write failing endpoint-contract tests**

Create `tests/test_api_app.py` with a fake service and assertions for:

```python
def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app(service=FakeService()))
    assert client.get("/api/health").json() == {"status": "ok", "service": "open-mechanic"}
```

- [ ] **Step 2: Run failing test**

Run: `uv run --extra dev --extra api pytest tests/test_api_app.py::test_health_endpoint_returns_ok --no-cov`

Expected: fail because `create_app` does not exist.

- [ ] **Step 3: Add schemas**

Implement Pydantic models:

```python
class HealthResponse(BaseModel):
    status: str
    service: str

class VehicleProfileResponse(BaseModel):
    configured: bool
    year: int | None = None
    make: str | None = None
    model: str | None = None
    mileage: int | None = None

class SensorReadingResponse(BaseModel):
    name: str
    value: str
    unit: str | None
    supported: bool
    timestamp: datetime

class DTCResponse(BaseModel):
    code: str
    description: str
    status: str
    severity: str
    category: str

class HealthSnapshotResponse(BaseModel):
    connected: bool
    port: str | None
    protocol: str | None
    sensors: list[SensorReadingResponse]
    dtcs: list[DTCResponse]

class DiagnoseRequest(BaseModel):
    year: int
    make: str
    model: str
    mileage: int
    vin: str | None = None
    bypass_cache: bool = False

class DiagnosisResponse(BaseModel):
    severity: str
    summary: str
    likely_causes: list[str]
    repair_steps: list[str]
    estimated_cost_usd: dict[str, int]
    diy_feasible: bool
    diy_difficulty: str
    urgency: str
    disclaimer: str
    dtc_codes: list[str]
    vehicle_str: str
    cached: bool
    timestamp: datetime
```

- [ ] **Step 4: Run focused test**

Run: `uv run --extra dev --extra api pytest tests/test_api_app.py::test_health_endpoint_returns_ok --no-cov`

Expected: still fail until app routes exist.

## Task 2: FastAPI App Factory and Routes

**Files:**
- Create: `src/open_mechanic/api/app.py`
- Modify: `src/open_mechanic/api/__init__.py`
- Test: `tests/test_api_app.py`

- [ ] **Step 1: Write failing route tests**

Add tests for:

```python
GET /api/health
GET /api/vehicle
GET /api/live
GET /api/dtc
GET /api/snapshot
POST /api/diagnose
```

Use a fake service with deterministic return values.

- [ ] **Step 2: Run route tests**

Run: `uv run --extra dev --extra api pytest tests/test_api_app.py --no-cov`

Expected: fail because routes do not exist.

- [ ] **Step 3: Implement `create_app(service=None)`**

Routes delegate to service methods:

```python
app.get("/api/health")
app.get("/api/vehicle")
app.get("/api/live")
app.get("/api/dtc")
app.get("/api/snapshot")
app.post("/api/diagnose")
```

- [ ] **Step 4: Run route tests**

Run: `uv run --extra dev --extra api pytest tests/test_api_app.py --no-cov`

Expected: pass.

## Task 3: Diagnostic API Service

**Files:**
- Create: `src/open_mechanic/api/services.py`
- Test: `tests/test_api_services.py`

- [ ] **Step 1: Write failing service tests**

Add tests for:

- `get_vehicle_profile()` returns configured false when no local profile exists.
- `get_live_sensors()` returns connected false when OBD connection fails.
- `get_snapshot()` disconnects after successful sensor/DTC read.
- `diagnose()` passes `bypass_cache` to `DiagnosticEngine`.

- [ ] **Step 2: Run service tests**

Run: `uv run --extra dev --extra api pytest tests/test_api_services.py --no-cov`

Expected: fail because service does not exist.

- [ ] **Step 3: Implement service**

Implement `DiagnosticAPIService` with dependency-injection constructor args:

```python
connection_factory: Callable[[], OBDConnection]
profile_loader: Callable[[], LocalVehicleProfile | None]
engine_factory: Callable[[], DiagnosticEngine]
```

Service methods:

```python
get_vehicle_profile() -> VehicleProfileResponse
get_live_sensors() -> HealthSnapshotResponse
get_dtcs() -> list[DTCResponse]
get_snapshot() -> HealthSnapshotResponse
diagnose(request: DiagnoseRequest) -> DiagnosisResponse
```

- [ ] **Step 4: Run service tests**

Run: `uv run --extra dev --extra api pytest tests/test_api_services.py --no-cov`

Expected: pass.

## Task 4: Tooling, Docs, and CI

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `docs/FUTURE_DEVELOPMENT_PLAN.md`

- [ ] **Step 1: Update test install commands**

Ensure local and CI commands use:

```bash
uv run --extra dev --extra api pytest
pip install -e ".[dev,api]"
```

- [ ] **Step 2: Document API usage**

Add README section:

```bash
pip install -e ".[dev,api]"
uvicorn open_mechanic.api:create_app --factory --reload
```

List current endpoints under "Current API Endpoints".

- [ ] **Step 3: Update future plan**

Mark FastAPI read-only backend as complete and leave dashboard/provider/distribution items open.

## Task 5: QA Verification

**Files:**
- No new files unless QA notes are needed in docs.

- [ ] **Step 1: Run automated verification**

Run:

```bash
uv run --extra dev --extra api pytest
uv run --extra dev --extra api ruff check src scripts tests
uv run --extra dev --extra api mypy src
cd website && npm run build
```

Expected: all pass, coverage remains 100%.

- [ ] **Step 2: Run API smoke QA**

Start API:

```bash
uv run --extra dev --extra api uvicorn open_mechanic.api:create_app --factory --host 127.0.0.1 --port 8765
```

Probe:

```bash
curl http://127.0.0.1:8765/api/health
curl http://127.0.0.1:8765/api/vehicle
curl http://127.0.0.1:8765/api/snapshot
```

Expected:

- `/api/health` returns status ok.
- `/api/vehicle` returns configured false or the local profile.
- `/api/snapshot` returns JSON and does not crash without an adapter.

- [ ] **Step 3: Commit and push**

```bash
git add .
git commit -m "Add read-only FastAPI backend"
git push origin main
```

---

## Self-Review

- Spec coverage: plan covers docs alignment, FastAPI backend, API contracts for dashboard, no-cache continuation, strict QA verification, and future plan update.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: route/service/schema names match across tasks.
