from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from types import MappingProxyType

import pytest

from open_mechanic.manufacturers.stellantis.catalog import (
    DIDDefinition,
    ModuleDefinition,
    Provenance,
    VehicleCatalog,
)
from open_mechanic.manufacturers.stellantis.models import (
    ModuleScanResult,
    ModuleState,
    StellantisScanResult,
)
from open_mechanic.manufacturers.stellantis.scanner import StellantisScanner
from open_mechanic.protocols.elm327 import ELM327AdapterError
from open_mechanic.protocols.requests import DiagnosticRequest


@dataclass(frozen=True)
class _Response:
    payload: bytes
    responder_id: int = 0x608


class FakeTransport:
    def __init__(self, replies: dict[int, object]) -> None:
        self._replies = replies
        self.requests: list[DiagnosticRequest] = []
        self.opened = 0
        self.closed = 0

    def open(self) -> None:
        self.opened += 1

    def close(self) -> None:
        self.closed += 1

    def exchange(self, request: DiagnosticRequest) -> list[_Response]:
        self.requests.append(request)
        reply = self._replies[request.tx_id]
        if isinstance(reply, deque):
            reply = reply.popleft()
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, bytes):
            return [_Response(reply, request.rx_id)]
        return reply  # type: ignore[return-value]


def _source(*, applicability: str = "exact_model_year") -> Provenance:
    return Provenance(
        document="Synthetic test fixture",
        url="https://example.test/fixture",
        evidence="vehicle_fixture" if applicability == "exact_model_year" else "community_reference",
        applicability=applicability,
    )


def _did(
    identifier: int,
    label: str,
    *,
    width: int = 1,
    unit: str | None = "kph",
    enum_map: dict[int, str] | None = None,
) -> DIDDefinition:
    return DIDDefinition(
        identifier=identifier,
        label=label,
        group="cruise",
        signed=False,
        width=width,
        scale=1.0,
        offset=0.0,
        unit=unit,
        enum_map=MappingProxyType(enum_map or {}),
        source=_source(),
    )


def _module(
    key: str,
    tx_id: int,
    *,
    services: frozenset[int] = frozenset({0x19, 0x22}),
    dids: tuple[DIDDefinition, ...] = (),
    applicability: str = "exact_model_year",
) -> ModuleDefinition:
    return ModuleDefinition(
        key=key,
        name=f"Synthetic {key}",
        role=key,
        tx_id=tx_id,
        rx_id=tx_id + 8,
        services=services,
        dids=dids,
        source=_source(applicability=applicability),
    )


def _catalog(*, dids: tuple[DIDDefinition, ...] = ()) -> VehicleCatalog:
    return VehicleCatalog(
        key="synthetic",
        name="Synthetic test vehicle",
        model_year=2024,
        modules=(
            _module("powertrain", 0x600, dids=dids),
            _module("steering", 0x620, applicability="community_unverified"),
        ),
    )


def test_scan_keeps_successes_when_another_module_times_out() -> None:
    transport = FakeTransport(
        {0x600: bytes.fromhex("5902FF1234562F"), 0x620: TimeoutError("bounded timeout")}
    )

    result = StellantisScanner(transport, _catalog()).scan_dtcs()

    assert result.module("powertrain").dtcs[0].identifier == 0x123456
    assert result.module("steering").state is ModuleState.TIMED_OUT
    assert result.module("steering").applicability == "community_unverified"
    assert transport.opened == transport.closed == 1


def test_security_denial_is_reported_without_an_unlock_request() -> None:
    transport = FakeTransport({0x600: bytes.fromhex("7F2233")})
    catalog = _catalog(dids=(_did(0x1234, "cruise_state", unit=None, enum_map={1: "engaged"}),))

    values = StellantisScanner(transport, catalog).read_group("cruise")

    assert values[0].state is ModuleState.GATEWAY_BLOCKED
    assert all(request.service != 0x27 for request in transport.requests)
    assert transport.opened == transport.closed == 1


def test_gateway_denial_stops_the_remaining_cataloged_dids_for_that_module() -> None:
    transport = FakeTransport({0x600: deque([bytes.fromhex("7F2233"), bytes.fromhex("62123550")])})
    catalog = _catalog(
        dids=(
            _did(0x1234, "cruise_state", unit=None, enum_map={1: "engaged"}),
            _did(0x1235, "wheel_speed"),
        )
    )

    values = StellantisScanner(transport, catalog).read_group("cruise")

    assert [value.state for value in values] == [
        ModuleState.GATEWAY_BLOCKED,
        ModuleState.GATEWAY_BLOCKED,
    ]
    assert values[1].fresh is False
    assert "securityAccessDenied" in (values[1].error or "")
    assert [request.payload for request in transport.requests] == [bytes.fromhex("221234")]


def test_mismatched_negative_response_service_is_malformed_not_gateway_blocked() -> None:
    transport = FakeTransport({0x600: bytes.fromhex("7F2733")})
    catalog = _catalog(dids=(_did(0x1234, "wheel_speed"),))

    value = StellantisScanner(transport, catalog).read_group("cruise")[0]

    assert value.state is ModuleState.NEGATIVE_RESPONSE
    assert "expected 0x22" in (value.error or "")
    assert "got 0x27" in (value.error or "")


def test_read_group_decodes_known_enum_and_retains_unknown_raw_value() -> None:
    transport = FakeTransport({0x600: bytes.fromhex("62123402")})
    catalog = _catalog(
        dids=(_did(0x1234, "cruise_state", unit=None, enum_map={0: "off", 1: "engaged"}),)
    )

    value = StellantisScanner(transport, catalog).read_group("cruise")[0]

    assert value.value == "unknown (0x02)"
    assert value.raw_value == 2
    assert value.state is ModuleState.RESPONDED


def test_read_group_marks_absent_catalog_data_unsupported_without_transport_io() -> None:
    transport = FakeTransport({})

    values = StellantisScanner(transport, _catalog()).read_group("cruise")

    assert [value.state for value in values] == [ModuleState.UNSUPPORTED, ModuleState.UNSUPPORTED]
    assert all(value.error == "not cataloged for group cruise" for value in values)
    assert transport.opened == transport.closed == 0


def test_read_group_redacts_vin_display() -> None:
    transport = FakeTransport({0x600: bytes.fromhex("62F190314A344641414239433132333435363738")})
    catalog = _catalog(dids=(_did(0xF190, "VIN", width=17, unit=None),))

    value = StellantisScanner(transport, catalog).read_group("cruise")[0]

    assert value.value == "[redacted]"
    assert value.raw_value is None


def test_scan_reports_unsupported_and_negative_responses_without_dropping_modules() -> None:
    transport = FakeTransport({0x600: [], 0x620: bytes.fromhex("7F1922")})

    result = StellantisScanner(transport, _catalog()).scan_dtcs()

    assert result.module("powertrain").state is ModuleState.UNSUPPORTED
    assert result.module("steering").state is ModuleState.NEGATIVE_RESPONSE
    assert "conditionsNotCorrect" in (result.module("steering").error or "")


def test_scan_does_not_open_transport_when_dtc_service_is_not_cataloged() -> None:
    transport = FakeTransport({})
    catalog = VehicleCatalog(
        key="synthetic",
        name="Synthetic test vehicle",
        model_year=2024,
        modules=(_module("cluster", 0x600, services=frozenset({0x22})),),
    )

    result = StellantisScanner(transport, catalog).scan_dtcs()

    assert result.module("cluster").state is ModuleState.UNSUPPORTED
    assert transport.opened == transport.closed == 0


def test_scan_retains_an_ineligible_module_as_unsupported_alongside_a_success() -> None:
    transport = FakeTransport({0x600: bytes.fromhex("5902FF")})
    catalog = VehicleCatalog(
        key="synthetic",
        name="Synthetic test vehicle",
        model_year=2024,
        modules=(
            _module("powertrain", 0x600),
            _module("cluster", 0x620, services=frozenset({0x22})),
        ),
    )

    result = StellantisScanner(transport, catalog).scan_dtcs()

    assert result.module("powertrain").state is ModuleState.RESPONDED
    assert result.module("cluster").state is ModuleState.UNSUPPORTED


def test_scan_converts_adapter_and_malformed_uds_failures_to_module_results() -> None:
    adapter_transport = FakeTransport(
        {0x600: ELM327AdapterError("adapter failure"), 0x620: bytes.fromhex("5902FF")}
    )
    malformed_transport = FakeTransport(
        {0x600: bytes.fromhex("5903FF"), 0x620: bytes.fromhex("5902FF")}
    )

    adapter_result = StellantisScanner(adapter_transport, _catalog()).scan_dtcs()
    malformed_result = StellantisScanner(malformed_transport, _catalog()).scan_dtcs()

    assert adapter_result.module("powertrain").state is ModuleState.NEGATIVE_RESPONSE
    assert malformed_result.module("powertrain").state is ModuleState.NEGATIVE_RESPONSE


def test_live_read_reports_adapter_and_protocol_failures_per_value() -> None:
    transport = FakeTransport({0x600: ELM327AdapterError("adapter rejected read")})
    catalog = _catalog(dids=(_did(0x1234, "wheel speed"),))

    value = StellantisScanner(transport, catalog).read_group("cruise")[0]

    assert value.key == "wheel_speed"
    assert value.state is ModuleState.NEGATIVE_RESPONSE
    assert value.fresh is False


def test_live_read_reports_timeouts_malformed_responses_and_wrong_responders() -> None:
    did = _did(0x1234, "wheel speed")
    timeout_transport = FakeTransport({0x600: TimeoutError("read timed out")})
    malformed_transport = FakeTransport({0x600: bytes.fromhex("7F")})
    wrong_responder_transport = FakeTransport({0x600: [_Response(bytes.fromhex("62123450"), 0x609)]})

    timeout_value = StellantisScanner(timeout_transport, _catalog(dids=(did,))).read_group("cruise")[0]
    malformed_value = StellantisScanner(malformed_transport, _catalog(dids=(did,))).read_group("cruise")[0]
    wrong_responder_value = StellantisScanner(
        wrong_responder_transport, _catalog(dids=(did,))
    ).read_group("cruise")[0]

    assert timeout_value.state is ModuleState.TIMED_OUT
    assert malformed_value.state is ModuleState.NEGATIVE_RESPONSE
    assert wrong_responder_value.state is ModuleState.UNSUPPORTED


def test_live_read_rejects_a_positive_response_for_the_wrong_did() -> None:
    transport = FakeTransport({0x600: bytes.fromhex("62123550")})

    value = StellantisScanner(
        transport, _catalog(dids=(_did(0x1234, "wheel speed"),))
    ).read_group("cruise")[0]

    assert value.state is ModuleState.NEGATIVE_RESPONSE


def test_live_read_decodes_scaled_numeric_value_and_rejects_wrong_width() -> None:
    scaled = _did(0x1234, "wheel speed", width=2)
    scaled = DIDDefinition(
        scaled.identifier,
        scaled.label,
        scaled.group,
        scaled.signed,
        scaled.width,
        0.5,
        -1.0,
        scaled.unit,
        scaled.enum_map,
        scaled.source,
    )
    transport = FakeTransport({0x600: deque([bytes.fromhex("6212340066"), bytes.fromhex("62123401")])})
    scanner = StellantisScanner(transport, _catalog(dids=(scaled,)))

    first = scanner.read_group("cruise")[0]
    second = scanner.read_group("cruise")[0]

    assert first.value == 50.0
    assert second.state is ModuleState.NEGATIVE_RESPONSE


def test_cruise_transition_adds_evidence_marker_only_after_an_engaged_sample() -> None:
    state = _did(0x1234, "cruise state", unit=None, enum_map={1: "engaged", 2: "cancelled"})
    transport = FakeTransport({0x600: deque([bytes.fromhex("62123401"), bytes.fromhex("62123402")])})
    scanner = StellantisScanner(transport, _catalog(dids=(state,)))

    first = scanner.read_group("cruise")[0]
    second = scanner.read_group("cruise")[0]

    assert first.event_marker is None
    assert second.event_marker == "engaged_to_cancelled"


def test_scan_closes_transport_when_opening_fails() -> None:
    class _OpeningTransport(FakeTransport):
        def open(self) -> None:
            super().open()
            raise ELM327AdapterError("cannot open")

    transport = _OpeningTransport({})

    with pytest.raises(ELM327AdapterError, match="cannot open"):
        StellantisScanner(transport, _catalog()).scan_dtcs()

    assert transport.closed == 1


def test_scanner_accepts_byte_payload_fakes_for_minimal_transport_tests() -> None:
    class _BytesTransport(FakeTransport):
        def exchange(self, request: DiagnosticRequest) -> list[bytes]:
            self.requests.append(request)
            return [bytes.fromhex("5902FF")]

    result = StellantisScanner(_BytesTransport({}), _catalog()).scan_dtcs()

    assert result.module("powertrain").state is ModuleState.RESPONDED


def test_scan_result_rejects_unknown_module_key() -> None:
    result = StellantisScanResult(
        (ModuleScanResult("powertrain", "PCM", ModuleState.RESPONDED, (), "exact_model_year"),)
    )

    with pytest.raises(KeyError, match="not present"):
        result.module("unknown")
