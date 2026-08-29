# API Contract

Last reviewed: 2026-08-29

The local FastAPI service exposes read-only diagnostic calls. Responses are transient
and **not persisted**: no history, database row, result cache, telemetry, or implicit AI
request is created.

## Run locally

```bash
pip install -e ".[dev,api]"
uvicorn open_mechanic.api:create_app --factory --reload
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Service liveness. |
| `GET` | `/api/vehicle` | Ephemeral vehicle context if supplied to the service. |
| `GET` | `/api/live` | Generic one-shot sensor snapshot. |
| `GET` | `/api/dtc` | Generic emissions DTCs. |
| `GET` | `/api/snapshot` | Combined generic snapshot. |
| `POST` | `/api/diagnose` | Explicitly authorized external AI diagnosis. |
| `GET` | `/api/stellantis/{vehicle}/dtc` | Catalog-bounded module DTC scan. |
| `GET` | `/api/stellantis/{vehicle}/live/{group}` | Finite catalog-bounded live view. |

The only enhanced catalog/group values are `wrangler_jl_4xe_2024` and `cruise`.
Stellantis hardware is OBDLink EX at fixed protocol 6 and 115200 baud. The API accepts
an explicit `port` and a timeout greater than zero and at most 10 seconds. Live requests
also require `samples` 1–60 and `interval` greater than zero and at most 10 seconds.

Example URLs:

```text
/api/stellantis/wrangler_jl_4xe_2024/dtc?port=/dev/ttyUSB0&timeout=1
/api/stellantis/wrangler_jl_4xe_2024/live/cruise?port=/dev/ttyUSB0&timeout=1&samples=3&interval=1
```

Responses preserve structured per-module states, provenance, applicability, unknown
definitions, unsupported values, and partial errors. An adapter/permission failure is
HTTP `503`; an unsupported catalog or group is `404`; invalid bounds are `422`. No
endpoint exposes arbitrary commands, address scans, writes, security access, DTC clear,
coding, flashing, or gateway bypass.

## AI authorization

`POST /api/diagnose` sends vehicle context and the current generic diagnostic snapshot
to the configured external provider only when the request includes
`external_sharing_authorized: true`.

```json
{
  "year": 2030,
  "make": "Synthetic",
  "model": "Example",
  "mileage": 10000,
  "vin": null,
  "external_sharing_authorized": true
}
```

This is invented synthetic data. Omitting authorization or setting it false returns
HTTP `403` and makes no provider call. Authorization applies to that request only. AI
responses are not cached; the response field `cached` remains for compatibility and is
always false.

## Consumer requirements

- Render `unknown`, `unsupported`, and partial-error states as such; never substitute
  zero or a guessed definition.
- Display provenance/applicability, especially `community_unverified`.
- Do not add client-side history by default.
- Never ask a driver to operate a client while moving; use a passenger or qualified
  technician.
- Treat all output as informational, not professional mechanical advice.
