# Future Development Plan

Last reviewed: 2026-08-29

This is a working plan, not a release promise.

## Current state

- Generic read-only OBD-II CLI/API diagnostics are available.
- The **2024 Jeep Wrangler JL 4xe** has an enhanced, ephemeral Stellantis module scan
  using OBDLink EX, fixed protocol 6, and 115200 baud.
- The request boundary allowlists read services and catalog entries before serial I/O.
- Scanner results preserve per-module errors, unknowns, provenance, and applicability.
- Normal diagnostic flows save no history and make no implicit AI request.
- External AI diagnosis requires per-request consent and is not cached.
- Automated tests use synthetic data and maintain 100% package line coverage.

## Catalog maturity

The current catalog distinguishes exact-model-year evidence from
`community_unverified` address references. Manufacturer-specific cruise DIDs remain
empty because acceptable public provenance has not been found. This is intentional:
unsupported is safer and more truthful than a guessed request or interpretation.

Future catalog contributions must provide stable public sources for every address, DID,
scale, enum, and meaning. Review must verify vehicle applicability and preserve the
source in packaged data and output. Observed data from a contributor's vehicle is not a
fixture or a definition source and must not be committed.

## Priorities

1. Obtain reviewable public provenance for Wrangler 4xe cruise-related DIDs and add
   them through schema tests before implementation.
2. Validate `community_unverified` module applicability through publishable evidence,
   without copying private vehicle traces into the repository.
3. Add more vehicle catalogs only through the same closed, provenance-backed request
   model; do not add generic address/DID scanning.
4. Build an optional local-only diagnosis provider that preserves ephemeral defaults.
5. Add user-controlled export only as a separate opt-in design with redaction,
   destination preview, and tests proving the default still writes nothing.
6. Build a dashboard that faithfully renders partial errors, unknowns, freshness, and
   provenance without introducing browser history or telemetry by default.

## Invariants for future work

- No writes, security unlock, actuator control, coding, flashing, DTC clear, arbitrary
  command input, or gateway bypass in the read-only feature.
- No AutoAuth or SGW bypass requirement may be claimed unless a separately designed
  supported workflow actually needs and implements it.
- A moving observation is passenger-only: a passenger or qualified technician operates
  the computer, never the driver.
- Never publish a VIN, adapter serial, observed DTC set, raw frame, or live value.
- External AI sharing remains explicit for every request.
