import pytest

from open_mechanic.protocols.requests import DiagnosticProtocol
from open_mechanic.protocols.uds import (
    UDSDTC,
    UDSNegativeResponse,
    UDSProtocolError,
    build_read_did,
    build_read_dtcs,
    parse_negative_response,
    parse_read_did,
    parse_read_dtcs,
)


def test_parses_three_byte_dtcs_and_status_masks() -> None:
    payload = bytes.fromhex("5902FF1234562FABCDEF08")
    assert parse_read_dtcs(payload) == (
        UDSDTC(identifier=0x123456, status_mask=0x2F),
        UDSDTC(identifier=0xABCDEF, status_mask=0x08),
    )


@pytest.mark.parametrize("identifier, status_mask", [(0x1000000, 0), (0, 0x100)])
def test_rejects_invalid_dtc_fields(identifier: int, status_mask: int) -> None:
    with pytest.raises(UDSProtocolError):
        UDSDTC(identifier=identifier, status_mask=status_mask)


def test_accepts_supported_dtc_status_availability_without_records() -> None:
    assert parse_read_dtcs(bytes.fromhex("5902FF")) == ()


@pytest.mark.parametrize(
    "payload",
    [bytes.fromhex("5902"), bytes.fromhex("5902FF01"), bytes.fromhex("5902FF123456")],
)
def test_rejects_malformed_dtc_record_length(payload: bytes) -> None:
    with pytest.raises(UDSProtocolError):
        parse_read_dtcs(payload)


def test_rejects_non_bytes_dtc_payload() -> None:
    with pytest.raises(TypeError):
        parse_read_dtcs(bytearray.fromhex("5902FF"))  # type: ignore[arg-type]


@pytest.mark.parametrize("payload", [bytes.fromhex("5802FF"), bytes.fromhex("5901FF")])
def test_rejects_incorrect_dtc_positive_service(payload: bytes) -> None:
    with pytest.raises(UDSProtocolError):
        parse_read_dtcs(payload)


def test_builds_read_dtcs_with_status_mask() -> None:
    request = build_read_dtcs(tx_id=0x7E0, rx_id=0x7E8, status_mask=0x2F)
    assert request.protocol is DiagnosticProtocol.UDS
    assert request.payload == bytes.fromhex("19022F")


@pytest.mark.parametrize("status_mask", [-1, 0x100, True])
def test_rejects_invalid_read_dtc_status_mask(status_mask: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_read_dtcs(tx_id=0x7E0, rx_id=0x7E8, status_mask=status_mask)


def test_builds_read_did_as_cataloged_uds_request() -> None:
    request = build_read_did(0xF190, tx_id=0x7E0, rx_id=0x7E8)
    assert request.protocol is DiagnosticProtocol.UDS
    assert request.cataloged_did is True
    assert request.payload == bytes.fromhex("22F190")


@pytest.mark.parametrize("did", [-1, 0x10000, True])
def test_rejects_invalid_read_did(did: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_read_did(did, tx_id=0x7E0, rx_id=0x7E8)


def test_parses_read_did_payload_after_matching_echo() -> None:
    assert parse_read_did(bytes.fromhex("62F1904A4C56494E"), 0xF190) == b"JLVIN"


def test_parses_read_did_with_empty_data() -> None:
    assert parse_read_did(bytes.fromhex("620001"), 0x0001) == b""


@pytest.mark.parametrize("payload", [bytes.fromhex("610001"), bytes.fromhex("62F19100")])
def test_rejects_wrong_read_did_service_or_echo(payload: bytes) -> None:
    with pytest.raises(UDSProtocolError):
        parse_read_did(payload, 0xF190)


def test_rejects_truncated_read_did_response() -> None:
    with pytest.raises(UDSProtocolError):
        parse_read_did(bytes.fromhex("62F1"), 0xF190)


def test_rejects_non_bytes_did_payload() -> None:
    with pytest.raises(TypeError):
        parse_read_did(bytearray.fromhex("62F190"), 0xF190)  # type: ignore[arg-type]


def test_decodes_security_denial_without_unlock_attempt() -> None:
    error = parse_negative_response(bytes.fromhex("7F2233"))
    assert error == UDSNegativeResponse(0x22, 0x33, "securityAccessDenied")


_NRC_MEANINGS = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x14: "responseTooLong",
    0x21: "busyRepeatRequest",
    0x22: "conditionsNotCorrect",
    0x24: "requestSequenceError",
    0x25: "noResponseFromSubnetComponent",
    0x26: "failurePreventsExecutionOfRequestedAction",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceedNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x70: "uploadDownloadNotAccepted",
    0x71: "transferDataSuspended",
    0x72: "generalProgrammingFailure",
    0x73: "wrongBlockSequenceCounter",
    0x78: "requestCorrectlyReceivedResponsePending",
    0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
    0x81: "rpmTooHigh",
    0x82: "rpmTooLow",
    0x83: "engineIsRunning",
    0x84: "engineIsNotRunning",
    0x85: "engineRunTimeTooLow",
    0x86: "temperatureTooHigh",
    0x87: "temperatureTooLow",
    0x88: "vehicleSpeedTooHigh",
    0x89: "vehicleSpeedTooLow",
    0x8A: "throttleOrPedalTooHigh",
    0x8B: "throttleOrPedalTooLow",
    0x8C: "transmissionRangeNotInNeutral",
    0x8D: "transmissionRangeNotInGear",
    0x8F: "brakeSwitch(es)NotClosed",
    0x90: "shifterLeverNotInPark",
    0x91: "torqueConverterClutchLocked",
    0x92: "voltageTooHigh",
    0x93: "voltageTooLow",
    0x94: "resourceTemporarilyNotAvailable",
}


@pytest.mark.parametrize("code, meaning", _NRC_MEANINGS.items())
def test_decodes_standard_negative_response_codes(code: int, meaning: str) -> None:
    assert parse_negative_response(bytes((0x7F, 0x22, code))) == UDSNegativeResponse(
        0x22, code, meaning
    )


def test_preserves_unknown_negative_response_code() -> None:
    assert parse_negative_response(bytes.fromhex("7F22FE")) == UDSNegativeResponse(
        0x22, 0xFE, "unknown"
    )


def test_rejects_non_bytes_negative_payload() -> None:
    with pytest.raises(TypeError):
        parse_negative_response(bytearray.fromhex("7F2233"))  # type: ignore[arg-type]


@pytest.mark.parametrize("payload", [b"", b"\x7f\x22", b"\x7e\x22\x33", b"\x7f\x22\x33\x00"])
def test_rejects_malformed_negative_response(payload: bytes) -> None:
    with pytest.raises(UDSProtocolError):
        parse_negative_response(payload)
