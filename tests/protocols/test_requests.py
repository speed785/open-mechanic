import pytest

from open_mechanic.protocols.requests import (
    DiagnosticProtocol,
    DiagnosticRequest,
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


def test_read_dtc_information_is_allowed() -> None:
    request = build_uds_request(0x19, b"", tx_id=0x7E0, rx_id=0x7E8)
    assert request.payload == bytes.fromhex("19")


@pytest.mark.parametrize("payload", [b"\x00", b"\x80"])
def test_tester_present_allows_bounded_subfunctions(payload: bytes) -> None:
    request = build_uds_request(0x3E, payload, tx_id=0x7E0, rx_id=0x7E8)
    assert request.payload == bytes([0x3E]) + payload


@pytest.mark.parametrize("payload", [b"", b"\x01", b"\x00\x00", b"\x80\x00"])
def test_tester_present_rejects_malformed_or_unbounded_payload(payload: bytes) -> None:
    with pytest.raises(UnsafeDiagnosticRequest):
        build_uds_request(0x3E, payload, tx_id=0x7E0, rx_id=0x7E8)


def test_direct_construction_rejects_unknown_protocol() -> None:
    with pytest.raises(UnsafeDiagnosticRequest):
        DiagnosticRequest("uds", 0x19, b"", 0x7E0, 0x7E8)  # type: ignore[arg-type]


def test_direct_construction_validates_protocol_allowlist() -> None:
    with pytest.raises(UnsafeDiagnosticRequest):
        DiagnosticRequest(DiagnosticProtocol.OBD, 0x22, b"", 0x7DF, 0x7E8)
