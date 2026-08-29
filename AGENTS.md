# AGENTS.md — open-mechanic

Authoritative contributor rules for this repository.

## Purpose and defaults

open-mechanic provides read-only, local-first OBD-II diagnostics. **No diagnostic history is saved by default.**
Normal CLI/API scan paths must not create profiles,
session logs, database rows, result caches, telemetry, or AI requests.

OBDLink EX is the only supported hardware for the enhanced **2024 Jeep Wrangler JL
4xe** path. It is fixed to 115200 baud and protocol 6 (ISO 15765-4 CAN 11-bit/500
kbit).

## Architecture

- `protocols/` validates requests, performs bounded serial exchange, and parses frames.
- `manufacturers/stellantis/` loads provenance-backed catalogs and returns immutable
  per-module results.
- `api/` exposes dependency-injected read-only endpoints.
- `ai/diagnose.py` requires explicit external sharing and does not cache.

Legacy storage models remain for compatibility; normal diagnostic flows do not call
them.

## Non-negotiable safety boundary

Allowed requests are OBD-II `01`, `02`, `03`, `07`, `09`, `0A`; UDS `0x19`; UDS
`0x22` only for cataloged DIDs; and bounded UDS `0x3E`. Reject arbitrary command text,
unlisted addresses/DIDs, invalid subfunctions, protocol changes, and baud-rate changes
before serial I/O. Never add address sweeps, write services, DTC clear, security access,
actuator tests, coding, flashing, or raw-command escape hatches to this feature.

AutoAuth and an SGW bypass cable are not required or claimed for the supported
public/read-only path. A gateway denial is a structured result, not permission to
bypass it.

## Catalog and result integrity

Every real address, DID, scaling rule, enum, and meaning needs a reviewable public
source. Preserve provenance and applicability in output. `exact_model_year` and
`community_unverified` are not equivalent. Unknown values remain unknown. The current
catalog intentionally has no proprietary cruise DIDs; the cruise group reports
unsupported/not-cataloged without sending guessed reads.

Preserve successful results when another module times out, rejects a request, returns
malformed data, or is unavailable. Commands are finite: timeout and interval are
greater than zero and at most 10 seconds; samples are 1–60.

## Privacy, AI, and safety

- Never persist diagnostic inputs/outputs in normal CLI/API flows.
- Never log or commit a VIN, adapter serial, observed DTCs, raw frames, or live values.
- Fixtures and docs use only invented, clearly labeled **synthetic** data.
- Local scans never call AI.
- Every CLI AI invocation requires `--share-with-ai`. Without it, the command displays
  sharing categories and exits before adapter/AI access; it does not prompt.
  Authorization is not retained and responses are not cached. The
  API `cached` field is compatibility-only and always false.
- Begin parked with the parking brake set and ignition in RUN. During any moving test,
  a passenger or qualified technician operates the computer; never the driver.

## Development

Use Python 3.11+, strict typing, Ruff, pytest, immutable core models where practical,
and 100% package line coverage. Write behavior tests first and observe RED. Never use
live hardware in automated tests.

```bash
pip install -e ".[dev,api]"
ruff format --check src tests scripts
ruff check src tests scripts
mypy src
pytest tests/ -v
```

Hardware acceptance requires separate explicit approval. Never copy its output into the
repository or pull request.
