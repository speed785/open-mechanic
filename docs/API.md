# API Contract

Last reviewed: 2026-05-22

The FastAPI backend is a read-only Phase 3 foundation for dashboards, local automations, and future self-hosted deployments. It wraps the existing OBD, DTC, vehicle profile, and AI diagnostic modules without requiring web callers to know those internals.

## Run Locally

```bash
pip install -e ".[api]"
uvicorn open_mechanic.api:create_app --factory --reload
```

Hardware calls use `OPEN_MECHANIC_API_OBD_TIMEOUT=3.0` and `OPEN_MECHANIC_API_OBD_RETRIES=1` by default so API smoke tests fail fast when no adapter is connected. Override those values for slower adapters.

## Current Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/health` | Service liveness check. |
| `GET` | `/api/vehicle` | Local vehicle profile from `local_data/vehicle_profile.json`. |
| `GET` | `/api/live` | One-shot live sensor snapshot. |
| `GET` | `/api/dtc` | Current fault codes. |
| `GET` | `/api/snapshot` | Combined connection, sensor, and DTC snapshot. |
| `POST` | `/api/diagnose` | AI diagnosis using the current snapshot and submitted vehicle details. |

## Response Shapes

`GET /api/health`

```json
{
  "status": "ok",
  "service": "open-mechanic"
}
```

`GET /api/vehicle`

```json
{
  "configured": true,
  "year": 2018,
  "make": "Ford",
  "model": "F-150",
  "mileage": 85000
}
```

`GET /api/live` and `GET /api/snapshot`

```json
{
  "connected": true,
  "port": "/dev/cu.usbserial-0",
  "protocol": "CAN",
  "sensors": [
    {
      "name": "RPM",
      "value": "750",
      "unit": "rpm",
      "supported": true,
      "timestamp": "2026-05-22T01:02:03"
    }
  ],
  "dtcs": []
}
```

`GET /api/dtc`

```json
[
  {
    "code": "P0420",
    "description": "Catalyst system efficiency below threshold",
    "status": "confirmed",
    "severity": "warning",
    "category": "emissions"
  }
]
```

`POST /api/diagnose`

Request:

```json
{
  "year": 2018,
  "make": "Ford",
  "model": "F-150",
  "mileage": 85000,
  "vin": null,
  "bypass_cache": false
}
```

Response:

```json
{
  "severity": "warning",
  "summary": "Catalyst efficiency below threshold",
  "likely_causes": ["Aged catalytic converter"],
  "repair_steps": ["Inspect O2 sensor waveforms"],
  "estimated_cost_usd": { "low": 100, "high": 500 },
  "diy_feasible": false,
  "diy_difficulty": "moderate",
  "urgency": "soon",
  "disclaimer": "This diagnosis is informational only and does not constitute professional mechanical advice. Consult a qualified mechanic before making safety-critical repairs.",
  "dtc_codes": ["P0420"],
  "vehicle_str": "2018 Ford F-150 (85,000 miles)",
  "cached": false,
  "timestamp": "2026-05-22T01:02:03"
}
```

## Dashboard Contract Notes

- Treat `/api/live` as a polling endpoint for now. A streaming endpoint can be added later without changing the snapshot shape.
- Show `connected=false` as a normal no-adapter state, not as a dashboard crash.
- Read `severity` and `category` as display hints. Do not use either value to clear codes or recommend safety-critical action without the disclaimer.
- The current API is local-first. Auth, sessions, history, and hosted multi-user access are not implemented.

## Planned Endpoints

- `GET /api/history`: past diagnostic sessions once session persistence is promoted from local JSON logs.
- `GET /api/guides/{dtc}`: repair guide content once guide sources and licensing are finalized.
- `GET /api/live/stream`: optional SSE stream for dashboards that need live updates.
