# Private Stellantis Diagnostics Design

## Summary

Add a read-only Stellantis diagnostic path that uses the documented OBDLink EX already recommended by open-mechanic. The first supported target is the 2024 Jeep Wrangler JL 4xe family, but the code is organized so later Stellantis catalogs can be added without changing the transport or UDS parser.

The feature reads standard OBD-II data, identifies allowlisted control modules, retrieves full UDS diagnostic trouble code records, and displays selected manufacturer-specific live values related to cruise-control availability. All vehicle data remains ephemeral by default. The application must not create profiles, session logs, database rows, caches, telemetry, or external AI requests during a local scan.

## Goals

- Require only an OBDLink EX connected to the vehicle's standard diagnostic connector.
- Read DTCs from known powertrain, hybrid, transmission, ABS/ESC, electric power steering, body/gateway, instrument-cluster, and driver-assistance modules when those modules respond through the Security Gateway.
- Preserve three-byte UDS DTC identifiers, failure subtype information, status bits, and responder identity instead of flattening all responses into generic two-byte Mode 03 codes.
- Read an allowlisted set of documented live values needed to investigate speed-dependent cruise cancellation, including wheel speeds, vehicle speed sources, steering data, brake/cruise inputs, transmission state, module supply voltage, and cruise state/cancellation reason where the vehicle exposes them without authentication.
- Make unsupported, timed-out, gateway-blocked, and negatively acknowledged requests visible without aborting the scan.
- Keep every normal scan in memory only and discard its data when the command exits.
- Maintain 100% automated line coverage for package code with synthetic transport fixtures.

## Non-goals

- DTC clearing, actuator tests, resets, relearns, coding, flashing, key programming, SecurityAccess, or Security Gateway unlocking.
- AutoAuth integration or support for physical Security Gateway bypass cables.
- Blind CAN-ID probing, broad DID sweeps, passive reverse engineering while driving, or transmission of arbitrary CAN frames.
- Claiming that an unknown DTC, module, or DID has a known meaning.
- Saving a user's vehicle history in the repository, filesystem, database, logs, analytics, crash reports, or an AI cache.
- Replacing a qualified technician for high-voltage, braking, steering, or other safety-critical repairs.

## Safety Boundary

The transport enforces an outbound allowlist before any bytes reach the adapter. Allowed application services are:

- Standard OBD-II Modes `01`, `02`, `03`, `07`, `09`, and `0A`.
- UDS `0x19` ReadDTCInformation.
- UDS `0x22` ReadDataByIdentifier for cataloged identifiers only.
- UDS `0x3E` TesterPresent only when required to complete an active read sequence.

Mode `04` and UDS services that can alter state, including `0x11`, `0x14`, `0x27`, `0x2E`, `0x2F`, `0x31`, `0x34`, `0x36`, and `0x37`, are rejected locally with a typed `UnsafeDiagnosticRequest` before serial transmission. Callers cannot disable the allowlist with a flag or environment variable.

Module discovery is catalog-driven. The scanner contacts only cataloged request addresses and does not sweep the CAN address space. A negative response is decoded and reported; it is never followed by a security-unlock attempt.

## Privacy Boundary

Local scans are private and ephemeral by default:

- No automatic `local_data/` directory creation.
- No saved vehicle profile or VIN.
- No JSONL session log.
- No SQLite diagnostic session.
- No diagnostic-result cache, including a long-lived in-memory API cache.
- No telemetry or crash-report payload containing vehicle data.
- No external AI call from `scan`, `stellantis-scan`, or live-data commands.

The existing CLI is changed to stop persisting profiles and sessions. Vehicle context is supplied as command arguments or held only for the current interactive process. Existing persistence helpers may remain for compatibility with library consumers, but normal CLI and API diagnostic flows must not call them.

AI diagnosis is a separate, explicit action. Before sending data, the command shows the exact categories to be transmitted and requires an interactive confirmation for that invocation. Non-interactive AI use requires an explicit `--share-with-ai` flag. AI responses are not cached. The local read-only scan remains fully useful without an API key or network connection.

Tests use invented VINs, DTCs, module addresses, and sensor values. Real scan output and raw frames must never be added to fixtures, snapshots, issue templates, documentation, commits, or pull-request text.

## Architecture

### Serial and adapter transport

`open_mechanic.protocols.elm327` owns the OBDLink serial session, adapter initialization, bounded timeouts, header selection, request serialization, and response collection. It returns immutable raw response objects containing the responder CAN identifier and payload bytes.

The transport has no knowledge of DTC meanings or live-data scaling. Its public request method accepts a validated read operation rather than arbitrary command text. Raw ELM/STN command escape hatches are not exposed through the CLI or API.

### ISO-TP and UDS

`open_mechanic.protocols.isotp` validates and reassembles single- and multi-frame ISO-TP responses with sequence, length, and responder checks. Malformed or incomplete responses become structured per-module errors.

`open_mechanic.protocols.uds` builds allowlisted read requests and parses positive and negative responses. UDS DTC results retain:

- Three-byte numeric DTC identifier.
- Display code when a documented mapping exists.
- Failure subtype when supplied by the catalog or response format.
- Raw status mask and decoded status flags.
- Request and response CAN identifiers.
- Reporting module key and display name.
- Definition provenance or `unknown`.

### Stellantis catalog

`open_mechanic.manufacturers.stellantis.catalog` loads packaged, reviewable data for supported vehicle families. Each entry contains a stable module key, display name, physical request/response addresses, supported read operations, cataloged DIDs, scaling rules, units, and source/provenance notes.

The 2024 Wrangler JL 4xe catalog covers the modules needed for powertrain, hybrid, transmission, ABS/ESC, steering, gateway/body, cluster, and cruise/ADAS diagnosis. A missing or unverified DID is omitted rather than guessed. Catalog validation rejects duplicate addresses, unsafe services, invalid scaling, and identifiers without provenance metadata.

### Stellantis scanner

`open_mechanic.manufacturers.stellantis.scanner` orchestrates one adapter session:

1. Establish standard CAN communication and verify adapter identity.
2. Read non-persisted vehicle identification needed to select a catalog; redact the VIN from normal output.
3. Contact cataloged modules with bounded retries.
4. Read module identity where supported.
5. Retrieve DTCs with UDS `0x19` and retain module/status metadata.
6. Read the allowlisted live-data group requested by the user.
7. Return an immutable in-memory `StellantisScanResult`.
8. Close the serial connection and release all result references on command exit.

A failure in one module does not discard successful results from other modules. The result distinguishes `responded`, `unsupported`, `timed_out`, `negative_response`, and `gateway_blocked` states.

### CLI and API

Add these CLI operations:

- `open-mechanic stellantis-scan`: module discovery plus full read-only DTC report.
- `open-mechanic stellantis-live --group cruise --samples N --interval SECONDS`: bounded ephemeral cruise-related live display.
- `open-mechanic diagnose --share-with-ai`: explicit external analysis after disclosure and confirmation.

The existing generic commands remain available but become non-persistent. Direct diagnostic commands do not require a saved profile.

The local API returns the same structured module, DTC, live-value, and error models. It must not persist requests or responses. An AI endpoint rejects requests unless the request explicitly marks external sharing as authorized; authorization applies only to that request.

## Live Cruise Investigation

The `cruise` live group displays only verified, cataloged values. It presents multiple speed sources side by side so a discrepancy becomes visible, and includes source module, timestamp, value, unit, and freshness. It highlights disagreement using deterministic thresholds defined in the catalog; it does not assign a component failure automatically.

The display includes an event marker when cruise state changes from engaged to unavailable or cancelled. If the vehicle exposes a documented cancellation-reason DID, its decoded value is shown. Otherwise the tool reports that the reason is unavailable and correlates only observable state transitions.

Road-speed collection is never started by default. The CLI warns that the driver must not operate the computer. Any moving test must be operated by a passenger or performed by a qualified technician on appropriate equipment. Automated verification for the PR uses synthetic traces and parked-vehicle reads only.

## Error Handling

- Serial permission errors identify the port and required Linux group/ACL without suggesting root execution of the application.
- Adapter initialization failures include the failed stage and preserve no raw history.
- Timeouts are bounded per request and per scan.
- ISO-TP sequence or length failures are attributed to the responder.
- UDS negative responses include the service and NRC meaning.
- Security-related negative responses are reported as blocked and end that module's protected path.
- Unknown DTCs retain their numeric bytes, status, and module identity with no invented description.
- An interrupted live view closes the adapter in `finally` and leaves no session file.

## Testing Strategy

Implementation follows red-green-refactor cycles. Tests use a fake serial transport and synthetic response transcripts; no automated test requires a vehicle or adapter.

Coverage includes:

- Safety allowlist acceptance and rejection, asserting rejected bytes never reach the fake serial port.
- ISO-TP single-frame, multi-frame, wrong-sequence, truncated, timeout, and mixed-responder cases.
- UDS DTC/status decoding and negative-response decoding.
- Catalog schema validation and representative 2024 Wrangler JL 4xe module/live-data entries.
- Partial module availability and Security Gateway denial.
- Deterministic live-value scaling and speed-disagreement detection.
- CLI output for known, unknown, unsupported, blocked, and interrupted reads.
- Privacy tests that fail if scan paths create directories/files, write database rows, retain cache entries, or invoke an AI client without per-request authorization.
- API contract tests using an in-process ASGI client compatible with the project's supported Python versions.

Before completion, run the full pytest suite with 100% coverage, Ruff checks and formatting, mypy strict checks, CLI help smoke tests, and a parked read-only scan through the OBDLink EX. No real vehicle results are committed.

## Delivery

The work ships as one pull request with reviewable commits for transport safety, protocol parsing, Stellantis catalog/scanner, ephemeral CLI/API behavior, and documentation. The README names OBDLink EX as the only required hardware, clearly separates generic from enhanced Stellantis coverage, documents the no-history default, and states that unsupported or protected functions require professional tooling rather than a bypass.

