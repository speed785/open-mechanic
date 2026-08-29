# Private Stellantis Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add private-by-default, read-only Stellantis module DTC and cruise live-data diagnostics for the 2024 Jeep Wrangler JL 4xe using only an OBDLink EX.

**Architecture:** A validated request model blocks unsafe services before a dedicated ELM/STN serial transport sends them. ISO-TP/UDS parsers feed a provenance-backed Stellantis catalog and scanner, which expose ephemeral CLI/API results without profiles, logs, databases, caches, or implicit AI calls.

**Tech Stack:** Python 3.11+, pyserial, Rich, FastAPI/Pydantic, pytest/pytest-cov, Ruff, mypy

**Spec:** `docs/superpowers/specs/2026-08-29-stellantis-private-diagnostics-design.md`

## Global Constraints

- OBDLink EX is the only required diagnostic hardware.
- All vehicle operations are read-only; unsafe OBD/UDS services are rejected before serial transmission.
- Standard OBD-II allowlist: Modes `01`, `02`, `03`, `07`, `09`, and `0A`.
- UDS allowlist: `0x19`, cataloged `0x22`, and bounded `0x3E` only.
- No blind CAN-ID scans or DID sweeps.
- No automatic profile, VIN, JSONL, SQLite, cache, telemetry, or AI persistence/transmission.
- Real vehicle responses never enter tests, fixtures, commits, documentation, or pull-request text.
- Unsupported data stays unknown; definitions and scaling require provenance.
- The complete package test suite retains 100% line coverage.

---

### Task 1: Enforce the outbound read-only protocol boundary

**Files:**
- Create: `src/open_mechanic/protocols/__init__.py`
- Create: `src/open_mechanic/protocols/requests.py`
- Test: `tests/protocols/test_requests.py`

**Interfaces:**
- Produces: `DiagnosticRequest(protocol: DiagnosticProtocol, service: int, parameters: bytes, tx_id: int, rx_id: int, cataloged_did: bool = False)`; `__post_init__` enforces the allowlist.
- Produces: `UnsafeDiagnosticRequest(ValueError)`
- Produces: `build_obd_request(mode, pid, *, tx_id, rx_id) -> DiagnosticRequest`
- Produces: `build_uds_request(service, payload, *, tx_id, rx_id, cataloged_did=False) -> DiagnosticRequest`
- Safety invariant: request bytes are returned only after allowlist validation.

- [ ] **Step 1: Write failing request-validation tests**

```python
import pytest

from open_mechanic.protocols.requests import (
    UnsafeDiagnosticRequest,
    build_obd_request,
    build_uds_request,
)


@pytest.mark.parametrize("mode", [0x01, 0x02, 0x03, 0x07, 0x09, 0x0A])
def test_standard_read_modes_are_allowed(mode: int) -> None:
    request = build_obd_request(mode, tx_id=0x7DF, rx_id=0x7E8)
    assert request.payload == bytes([mode])


@pytest.mark.parametrize("mode", [0x04, 0x05, 0x08])
def test_standard_write_or_control_modes_are_rejected(mode: int) -> None:
    with pytest.raises(UnsafeDiagnosticRequest):
        build_obd_request(mode, tx_id=0x7DF, rx_id=0x7E8)


@pytest.mark.parametrize("service", [0x11, 0x14, 0x27, 0x2E, 0x2F, 0x31, 0x34, 0x36, 0x37])
def test_state_changing_uds_services_are_rejected(service: int) -> None:
    with pytest.raises(UnsafeDiagnosticRequest):
        build_uds_request(service, b"", tx_id=0x7E0, rx_id=0x7E8)


def test_read_data_identifier_requires_catalog_approval() -> None:
    with pytest.raises(UnsafeDiagnosticRequest):
        build_uds_request(0x22, bytes.fromhex("F190"), tx_id=0x7E0, rx_id=0x7E8)
    request = build_uds_request(
        0x22,
        bytes.fromhex("F190"),
        tx_id=0x7E0,
        rx_id=0x7E8,
        cataloged_did=True,
    )
    assert request.payload == bytes.fromhex("22F190")
```

- [ ] **Step 2: Run the request tests and verify import failure**

Run: `.venv/bin/pytest tests/protocols/test_requests.py -v --no-cov`

Expected: collection fails because `open_mechanic.protocols.requests` does not exist.

- [ ] **Step 3: Implement immutable requests and the closed allowlists**

```python
from dataclasses import dataclass
from enum import Enum

READ_ONLY_OBD_MODES = frozenset({0x01, 0x02, 0x03, 0x07, 0x09, 0x0A})
READ_ONLY_UDS_SERVICES = frozenset({0x19, 0x22, 0x3E})


class UnsafeDiagnosticRequest(ValueError):
    """Raised before an unsafe request reaches the serial transport."""


class DiagnosticProtocol(Enum):
    OBD = "obd"
    UDS = "uds"


@dataclass(frozen=True)
class DiagnosticRequest:
    protocol: DiagnosticProtocol
    service: int
    parameters: bytes
    tx_id: int
    rx_id: int
    cataloged_did: bool = False

    def __post_init__(self) -> None:
        allowed = READ_ONLY_OBD_MODES if self.protocol is DiagnosticProtocol.OBD else READ_ONLY_UDS_SERVICES
        if self.service not in allowed:
            raise UnsafeDiagnosticRequest(f"service 0x{self.service:02X} is not read-only")
        if self.protocol is DiagnosticProtocol.UDS and self.service == 0x22 and not self.cataloged_did:
            raise UnsafeDiagnosticRequest("UDS 0x22 requires a cataloged DID")

    @property
    def payload(self) -> bytes:
        return bytes([self.service]) + self.parameters


def build_obd_request(mode: int, pid: int | None = None, *, tx_id: int, rx_id: int) -> DiagnosticRequest:
    parameters = b"" if pid is None else bytes([pid])
    return DiagnosticRequest(DiagnosticProtocol.OBD, mode, parameters, tx_id, rx_id)


def build_uds_request(
    service: int,
    payload: bytes,
    *,
    tx_id: int,
    rx_id: int,
    cataloged_did: bool = False,
) -> DiagnosticRequest:
    return DiagnosticRequest(
        DiagnosticProtocol.UDS,
        service,
        payload,
        tx_id,
        rx_id,
        cataloged_did,
    )
```

- [ ] **Step 4: Run focused tests and package coverage**

Run: `.venv/bin/pytest tests/protocols/test_requests.py -v`

Expected: all request tests pass and the new module has 100% coverage.

- [ ] **Step 5: Commit the safety boundary**

```bash
git add src/open_mechanic/protocols tests/protocols/test_requests.py
git commit -m "feat: enforce read-only diagnostic requests"
```

---

### Task 2: Add bounded OBDLink ELM/STN transport and ISO-TP parsing

**Files:**
- Create: `src/open_mechanic/protocols/elm327.py`
- Create: `src/open_mechanic/protocols/isotp.py`
- Test: `tests/protocols/test_elm327.py`
- Test: `tests/protocols/test_isotp.py`

**Interfaces:**
- Consumes: `DiagnosticRequest`
- Produces: `RawDiagnosticResponse(responder_id: int, payload: bytes)`
- Produces: `ELM327Transport.open()`, `exchange(request)`, and `close()`
- Produces: `reassemble_isotp(frames: list[CANFrame]) -> bytes`
- Dependency injection: serial constructor is passed into the transport for tests.

- [ ] **Step 1: Write failing transport tests using an in-memory serial double**

```python
def test_exchange_initializes_can_and_uses_validated_headers() -> None:
    serial = FakeSerial(
        responses={
            "ATZ": "OBDLink EX\r>",
            "ATE0": "OK\r>",
            "ATL0": "OK\r>",
            "ATS0": "OK\r>",
            "ATH1": "OK\r>",
            "ATSP6": "OK\r>",
            "ATSH7E0": "OK\r>",
            "ATCRA7E8": "OK\r>",
            "22F190": "7E8 10 14 62 F1 90 31 4A\r7E8 21 34 46 59 35 39 30\r>",
        }
    )
    transport = ELM327Transport("/dev/test", serial_factory=lambda **_: serial)
    transport.open()
    request = build_uds_request(
        0x22,
        bytes.fromhex("F190"),
        tx_id=0x7E0,
        rx_id=0x7E8,
        cataloged_did=True,
    )
    result = transport.exchange(request)
    assert result[0].responder_id == 0x7E8
    assert result[0].payload.startswith(bytes.fromhex("62F190"))
```

Also test permission errors, missing prompts, `NO DATA`, `STOPPED`, malformed headers, timeout, mixed responders, and `close()` after exceptions.

- [ ] **Step 2: Write failing ISO-TP tests**

```python
def test_reassembles_multiframe_payload() -> None:
    frames = [
        CANFrame(0x7E8, bytes.fromhex("100A5902ABCDEF01")),
        CANFrame(0x7E8, bytes.fromhex("2123456700000000")),
    ]
    assert reassemble_isotp(frames) == bytes.fromhex("5902ABCDEF01234567")


def test_rejects_wrong_sequence_number() -> None:
    frames = [
        CANFrame(0x7E8, bytes.fromhex("100A5902ABCDEF01")),
        CANFrame(0x7E8, bytes.fromhex("2223456700000000")),
    ]
    with pytest.raises(ISOTPSequenceError):
        reassemble_isotp(frames)
```

- [ ] **Step 3: Run focused tests and verify missing implementations**

Run: `.venv/bin/pytest tests/protocols/test_elm327.py tests/protocols/test_isotp.py -v --no-cov`

Expected: import/definition failures for transport and ISO-TP types.

- [ ] **Step 4: Implement serial framing, parsing, timeouts, and cleanup**

Use `serial.Serial(port, baudrate=115200, timeout=timeout, write_timeout=timeout)`. Normalize only ASCII adapter lines, reject unexpected command echo after `ATE0`, parse 11-bit hexadecimal headers, group frames by responder, and pass each group to `reassemble_isotp`. Never accept arbitrary user-supplied ELM commands.

- [ ] **Step 5: Run transport tests and lint the new protocol package**

Run: `.venv/bin/pytest tests/protocols -v`

Run: `.venv/bin/ruff check src/open_mechanic/protocols tests/protocols`

Expected: tests pass with 100% coverage and Ruff reports no errors.

- [ ] **Step 6: Commit the transport layer**

```bash
git add src/open_mechanic/protocols tests/protocols
git commit -m "feat: add bounded OBDLink transport"
```

---

### Task 3: Parse UDS identities, DTCs, status, and negative responses

**Files:**
- Create: `src/open_mechanic/protocols/uds.py`
- Test: `tests/protocols/test_uds.py`

**Interfaces:**
- Produces: `UDSDTC(identifier: int, status_mask: int)`
- Produces: `UDSNegativeResponse(service: int, code: int, meaning: str)`
- Produces: `build_read_dtcs(*, tx_id: int, rx_id: int, status_mask: int = 0xFF) -> DiagnosticRequest`
- Produces: `parse_read_dtcs(payload: bytes) -> tuple[UDSDTC, ...]`
- Produces: `build_read_did(did: int, *, tx_id: int, rx_id: int) -> DiagnosticRequest` and `parse_read_did(payload, did) -> bytes`

- [ ] **Step 1: Write failing positive and negative response tests**

```python
def test_parses_three_byte_dtcs_and_status_masks() -> None:
    payload = bytes.fromhex("5902FF1234562FABCDEF08")
    assert parse_read_dtcs(payload) == (
        UDSDTC(identifier=0x123456, status_mask=0x2F),
        UDSDTC(identifier=0xABCDEF, status_mask=0x08),
    )


def test_decodes_security_denial_without_unlock_attempt() -> None:
    error = parse_negative_response(bytes.fromhex("7F2233"))
    assert error == UDSNegativeResponse(0x22, 0x33, "securityAccessDenied")
```

Also cover malformed record length, incorrect positive service, wrong DID echo, supported-DTC status availability, and all NRC values displayed by the CLI.

- [ ] **Step 2: Run and verify RED**

Run: `.venv/bin/pytest tests/protocols/test_uds.py -v --no-cov`

Expected: import failure because `protocols.uds` does not exist.

- [ ] **Step 3: Implement strict UDS builders/parsers**

`build_read_dtcs()` produces a validated request whose payload is `19 02 <mask>`. Each returned `0x59 0x02` record is exactly four bytes: three identifier bytes plus one status byte. `build_read_did()` delegates to the Task 1 allowlist. Negative responses never trigger retries with `0x27`.

- [ ] **Step 4: Run UDS and complete protocol tests**

Run: `.venv/bin/pytest tests/protocols -v`

Expected: pass with 100% protocol-package coverage.

- [ ] **Step 5: Commit UDS parsing**

```bash
git add src/open_mechanic/protocols/uds.py tests/protocols/test_uds.py
git commit -m "feat: decode read-only UDS responses"
```

---

### Task 4: Add a provenance-checked 2024 Wrangler JL 4xe catalog

**Files:**
- Create: `src/open_mechanic/manufacturers/__init__.py`
- Create: `src/open_mechanic/manufacturers/stellantis/__init__.py`
- Create: `src/open_mechanic/manufacturers/stellantis/catalog.py`
- Create: `src/open_mechanic/manufacturers/stellantis/catalogs/wrangler_jl_4xe_2024.json`
- Modify: `pyproject.toml`
- Test: `tests/stellantis/test_catalog.py`

**Interfaces:**
- Produces: `ModuleDefinition`, `DIDDefinition`, `VehicleCatalog`
- Produces: `load_catalog("wrangler_jl_4xe_2024") -> VehicleCatalog`
- Each module: stable key/name plus physical `tx_id`/`rx_id`.
- Each DID: identifier, label, group, signedness, width, scale, offset, unit, enum map, and source URL/document identifier.

- [ ] **Step 1: Write catalog-schema and provenance tests**

```python
def test_2024_4xe_catalog_contains_required_module_roles() -> None:
    catalog = load_catalog("wrangler_jl_4xe_2024")
    assert {module.role for module in catalog.modules} >= {
        "powertrain",
        "hybrid",
        "transmission",
        "abs_esc",
        "steering",
        "body_gateway",
        "cluster",
        "adas",
    }


def test_every_cataloged_did_has_provenance() -> None:
    catalog = load_catalog("wrangler_jl_4xe_2024")
    for module in catalog.modules:
        for did in module.dids:
            assert did.source.document
            assert did.source.url.startswith("https://")
```

Add rejection tests for duplicate CAN pairs, duplicate DIDs, unsupported service values, missing provenance, non-finite scaling, and cruise DIDs with no unit/enum mapping.

- [ ] **Step 2: Run and verify RED**

Run: `.venv/bin/pytest tests/stellantis/test_catalog.py -v --no-cov`

Expected: import failure because the Stellantis catalog does not exist.

- [ ] **Step 3: Implement immutable catalog parsing and validation**

Use frozen dataclasses and `importlib.resources` so installed wheels include the JSON catalog. Reject invalid catalog data at load time with `CatalogValidationError`.
Add `build>=1.2` to the development extra before using `python -m build`.

- [ ] **Step 4: Populate only source-verified module and cruise entries**

For every address and DID, record the public service document, standard, or vendor protocol document used. If a desired cruise value has no verifiable identifier, omit it and let the UI display `not cataloged`; do not derive entries from the owner's private scan or copy proprietary service-manual text.

- [ ] **Step 5: Run catalog tests and packaging smoke test**

Run: `.venv/bin/pytest tests/stellantis/test_catalog.py -v`

Run: `.venv/bin/python -m build --wheel`

Run: `.venv/bin/python -c 'from open_mechanic.manufacturers.stellantis.catalog import load_catalog; print(load_catalog("wrangler_jl_4xe_2024").key)'`

Expected: tests pass; the installed-resource smoke test prints `wrangler_jl_4xe_2024`.

- [ ] **Step 6: Commit the reviewed catalog**

```bash
git add src/open_mechanic/manufacturers tests/stellantis/test_catalog.py pyproject.toml
git commit -m "feat: add sourced Wrangler 4xe catalog"
```

---

### Task 5: Build the partial-failure Stellantis scanner and cruise correlation

**Files:**
- Create: `src/open_mechanic/manufacturers/stellantis/models.py`
- Create: `src/open_mechanic/manufacturers/stellantis/scanner.py`
- Create: `src/open_mechanic/manufacturers/stellantis/cruise.py`
- Test: `tests/stellantis/test_scanner.py`
- Test: `tests/stellantis/test_cruise.py`

**Interfaces:**
- Produces: `ModuleState` enum with `responded`, `unsupported`, `timed_out`, `negative_response`, `gateway_blocked`.
- Produces: `ModuleDTC`, `LiveValue`, `ModuleScanResult`, `StellantisScanResult` frozen dataclasses.
- Produces: `StellantisScanner.scan_dtcs() -> StellantisScanResult`
- Produces: `StellantisScanner.read_group("cruise") -> tuple[LiveValue, ...]`
- Produces: `find_speed_disagreement(values, *, threshold_kph: float) -> SpeedDisagreement | None`

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_scan_keeps_successes_when_another_module_times_out() -> None:
    transport = FakeTransport.for_modules(
        powertrain=positive_dtc_response(0x123456, status=0x2F),
        steering=TimeoutError(),
    )
    result = StellantisScanner(transport, synthetic_catalog()).scan_dtcs()
    assert result.module("powertrain").dtcs[0].identifier == 0x123456
    assert result.module("steering").state is ModuleState.TIMED_OUT


def test_security_denial_is_reported_and_never_followed_by_unlock() -> None:
    transport = FakeTransport.responses([bytes.fromhex("7F2233")])
    result = StellantisScanner(transport, synthetic_catalog()).read_group("cruise")
    assert result[0].state is ModuleState.GATEWAY_BLOCKED
    assert all(request.service != 0x27 for request in transport.requests)
```

- [ ] **Step 2: Write failing cruise-correlation tests**

```python
def test_flags_one_wheel_speed_that_diverges_at_cruise_speed() -> None:
    values = synthetic_wheel_speeds(front_left=80.0, front_right=80.2, rear_left=79.9, rear_right=67.0)
    mismatch = find_speed_disagreement(values, threshold_kph=3.0)
    assert mismatch is not None
    assert mismatch.outlier_key == "wheel_speed_rear_right"
```

Also test timestamps/freshness, no false alert below threshold, enum decoding, unknown raw values, and cruise engaged-to-cancelled event markers.

- [ ] **Step 3: Run scanner tests and verify RED**

Run: `.venv/bin/pytest tests/stellantis/test_scanner.py tests/stellantis/test_cruise.py -v --no-cov`

Expected: import failures for scanner/model/correlation modules.

- [ ] **Step 4: Implement scanner orchestration and immutable result models**

Open one transport session, contact only cataloged modules, catch errors per module, decode only cataloged values, redact VIN display, and close in `finally`. Do not create a profile, recorder, database session, or AI engine.

- [ ] **Step 5: Implement deterministic cruise correlation**

Compare only fresh values with matching units and timestamps within one sample interval. Return evidence (`min`, `max`, `delta`, outlier key) rather than a repair diagnosis.

- [ ] **Step 6: Run Stellantis tests and static checks**

Run: `.venv/bin/pytest tests/stellantis -v`

Run: `.venv/bin/ruff check src/open_mechanic/manufacturers tests/stellantis`

Run: `.venv/bin/mypy src/open_mechanic/manufacturers`

- [ ] **Step 7: Commit the scanner**

```bash
git add src/open_mechanic/manufacturers tests/stellantis
git commit -m "feat: scan Stellantis modules read only"
```

---

### Task 6: Make all normal diagnostic flows ephemeral and AI explicit

**Files:**
- Modify: `src/open_mechanic/tools.py`
- Modify: `src/open_mechanic/ai/diagnose.py`
- Modify: `src/open_mechanic/api/schemas.py`
- Modify: `src/open_mechanic/api/services.py`
- Modify: `src/open_mechanic/api/app.py`
- Modify: `scripts/diagnose.py`
- Modify: `tests/test_tools_helpers.py`
- Modify: `tests/test_diagnose.py`
- Modify: `tests/test_api_services.py`
- Modify: `tests/test_api_app.py`
- Create: `tests/test_privacy.py`

**Interfaces:**
- CLI scan paths hold `VehicleProfile` in memory and never call `ensure_local_dirs`, `save_vehicle_profile`, or `SessionLog`.
- `DiagnosticEngine.diagnose(..., external_sharing_authorized: bool = False)` rejects before client invocation unless true.
- `DiagnoseRequest.external_sharing_authorized: bool = False` replaces `bypass_cache`.
- `DiagnosisResult.cached` remains `False` for response compatibility in this PR.

- [ ] **Step 1: Write failing no-write privacy tests**

```python
def test_generic_snapshot_creates_no_files_or_directories(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[object] = []
    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: writes.append((args, kwargs)))
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: writes.append((args, kwargs)))
    assert tools.run_direct_tool("snapshot", args(), console(), profile=profile()) == 0
    assert writes == []


def test_ai_client_is_not_called_without_per_request_authorization() -> None:
    engine = DiagnosticEngine(api_key="test")
    engine._client = RecordingClient()  # type: ignore[assignment]
    with pytest.raises(ExternalSharingNotAuthorized):
        engine.diagnose(vehicle(), dtcs(), snapshot(), external_sharing_authorized=False)
    assert engine._client.calls == []
```

Also assert no cache entries exist after success/fallback, API authorization applies to one request only, and CLI non-interactive diagnosis requires `--share-with-ai`.

- [ ] **Step 2: Run privacy tests and verify RED**

Run: `.venv/bin/pytest tests/test_privacy.py tests/test_diagnose.py -v --no-cov`

Expected: existing CLI persistence and AI caching/implicit sharing assertions fail.

- [ ] **Step 3: Remove automatic CLI persistence and AI caching**

Delete normal-flow calls to `ensure_local_dirs`, `load_vehicle_profile`, `save_vehicle_profile`, and `SessionLog`. Keep compatibility helpers isolated in `local_store.py`, but do not import them from `tools.py`. Remove `_cache`, cache-key methods, writes, and cache reuse from `DiagnosticEngine`.

- [ ] **Step 4: Add explicit external-sharing authorization**

Before creating the Anthropic message, raise `ExternalSharingNotAuthorized` unless the explicit boolean is true. The interactive CLI prints categories—not raw values—then obtains confirmation. Non-interactive invocation requires `--share-with-ai`.

- [ ] **Step 5: Repair API tests with a deterministic ASGI transport**

Replace the hanging synchronous `TestClient` dependency with `httpx2.ASGITransport` and `httpx2.AsyncClient` tests under `pytest.mark.anyio`, keeping production endpoints unchanged except for privacy request fields. Pin compatible minimum versions in the `api` and `dev` extras so a clean install contains its test client.

- [ ] **Step 6: Run privacy, AI, CLI, and API tests**

Run: `.venv/bin/pytest tests/test_privacy.py tests/test_diagnose.py tests/test_tools_helpers.py tests/test_api_app.py tests/test_api_services.py -v`

Expected: all pass, no timeout, no filesystem artifacts under a temporary working directory.

- [ ] **Step 7: Commit privacy defaults**

```bash
git add src/open_mechanic scripts/diagnose.py tests pyproject.toml
git commit -m "feat: make diagnostics private by default"
```

---

### Task 7: Expose Stellantis scan and bounded live views in CLI/API

**Files:**
- Create: `src/open_mechanic/manufacturers/stellantis/cli.py`
- Modify: `src/open_mechanic/tools.py`
- Modify: `src/open_mechanic/api/schemas.py`
- Modify: `src/open_mechanic/api/services.py`
- Modify: `src/open_mechanic/api/app.py`
- Create: `tests/stellantis/test_cli.py`
- Modify: `tests/test_api_app.py`
- Modify: `tests/test_api_services.py`

**Interfaces:**
- CLI: `stellantis-scan --vehicle wrangler_jl_4xe_2024 [connection arguments]`
- CLI: `stellantis-live --vehicle wrangler_jl_4xe_2024 --group cruise --samples N --interval SECONDS`
- API: `GET /api/stellantis/{vehicle}/dtc`
- API: `GET /api/stellantis/{vehicle}/live/{group}` with bounded `samples` and `interval` validation.

- [ ] **Step 1: Write failing CLI rendering tests**

```python
def test_stellantis_scan_labels_module_status_and_unknown_dtcs() -> None:
    result = synthetic_scan_result()
    output = render_scan_to_text(result)
    assert "Electric Power Steering" in output
    assert "0x123456" in output
    assert "unknown" in output
    assert "No diagnostic data was saved" in output
```

Test permission guidance, gateway blocking, partial results, Ctrl-C cleanup, `samples >= 1`, positive interval, and driver-distraction warning.

- [ ] **Step 2: Write failing API contract tests**

Assert module identity, three-byte DTC integer/display form, status mask/flags, provenance, live units/freshness, and structured per-module errors are serialized without VIN or persistence paths.

- [ ] **Step 3: Run CLI/API tests and verify RED**

Run: `.venv/bin/pytest tests/stellantis/test_cli.py tests/test_api_app.py tests/test_api_services.py -v --no-cov`

Expected: commands/routes/models do not exist.

- [ ] **Step 4: Implement Rich renderers and command dispatch**

Use tables grouped by module. Never print a full VIN. Live mode defaults to a finite sample count and requires an explicit positive count; it does not offer an unbounded drive recorder.

- [ ] **Step 5: Implement dependency-injected API routes**

Keep hardware behind service methods so API tests supply fake scanners. Validate catalog and group names against packaged allowlists and cap sample count/interval server-side.

- [ ] **Step 6: Run focused and full CLI/API tests**

Run: `.venv/bin/pytest tests/stellantis/test_cli.py tests/test_api_app.py tests/test_api_services.py -v`

Run: `.venv/bin/open-mechanic --help`

Run: `.venv/bin/open-mechanic stellantis-scan --help`

- [ ] **Step 7: Commit interfaces**

```bash
git add src/open_mechanic tests
git commit -m "feat: expose private Stellantis diagnostics"
```

---

### Task 8: Document, verify, and perform the parked hardware acceptance test

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/SETUP_LINUX.md`
- Modify: `docs/API.md`
- Modify: `docs/AI_PROVIDERS.md`
- Modify: `docs/FUTURE_DEVELOPMENT_PLAN.md`
- Test: all tests

**Interfaces:**
- Documentation names OBDLink EX as the only required hardware for the supported Stellantis path.
- Documentation states the no-history default and exact read-only boundary.
- No personal vehicle results appear in documentation or commits.

- [ ] **Step 1: Write documentation assertions before editing docs**

Create tests that read packaged documentation and require these phrases/concepts: `OBDLink EX`, `2024 Jeep Wrangler JL 4xe`, `read-only`, `No diagnostic history is saved by default`, passenger-only moving test, and explicit external AI sharing.

- [ ] **Step 2: Run documentation tests and verify RED**

Run: `.venv/bin/pytest tests/test_documentation.py -v --no-cov`

Expected: missing privacy/Stellantis documentation assertions fail.

- [ ] **Step 3: Update user and contributor documentation**

Document installation with `.[dev,api]`, serial permissions, parked scan commands, bounded cruise live commands, structured errors, unsupported fields, safety limits, and explicit AI disclosure. Do not paste real output.

- [ ] **Step 4: Run complete automated verification**

Run: `.venv/bin/ruff format --check src tests scripts`

Run: `.venv/bin/ruff check src tests scripts`

Run: `.venv/bin/mypy src`

Run: `.venv/bin/pytest tests/ -v`

Expected: all commands exit zero, package line coverage is 100%, and no resource warnings or hung API tests remain.

- [ ] **Step 5: Inspect repository privacy and diff hygiene**

Run: `git diff --check`

Run: `git status --short`

Review every added fixture and documentation example against the transient hardware session. Expected: no adapter serial number, private observed-code set, raw frame, or live value copied from that session appears in tracked work; only invented synthetic values are present.

- [ ] **Step 6: Run parked OBDLink EX acceptance checks with explicit approval**

With ignition in RUN, engine off, and serial permission confirmed:

Run: `.venv/bin/open-mechanic stellantis-scan --vehicle wrangler_jl_4xe_2024 --port /dev/ttyUSB0 --protocol 6`

Run: `.venv/bin/open-mechanic stellantis-live --vehicle wrangler_jl_4xe_2024 --group cruise --samples 3 --interval 1 --port /dev/ttyUSB0 --protocol 6`

Expected: adapter connects, supported modules/values render, unavailable modules are structured partial results, no write service is emitted, and no local diagnostic artifact is created. Review output transiently; do not copy it into the repository or PR.

- [ ] **Step 7: Commit documentation and final verification updates**

```bash
git add README.md AGENTS.md docs tests/test_documentation.py
git commit -m "docs: document private Stellantis diagnostics"
```

- [ ] **Step 8: Prepare the PR without private diagnostic evidence**

Run: `git log --oneline main..HEAD`

Run: `git diff --stat main...HEAD`

PR title: `feat: add private read-only Stellantis diagnostics`

PR summary must describe protocol safety, supported catalog, ephemeral defaults, and synthetic verification. It must not contain the owner's VIN, adapter serial number, observed DTCs, raw frames, or live sensor values.
