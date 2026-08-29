"""Strict, read-only UDS request builders and response parsers."""

from dataclasses import dataclass

from open_mechanic.protocols.requests import DiagnosticRequest, build_uds_request


class UDSProtocolError(ValueError):
    """Raised when a UDS payload is malformed or has an unexpected header."""


@dataclass(frozen=True)
class UDSDTC:
    """A UDS three-byte diagnostic trouble code and its raw status mask."""

    identifier: int
    status_mask: int

    def __post_init__(self) -> None:
        if type(self.identifier) is not int or not 0 <= self.identifier <= 0xFFFFFF:
            raise UDSProtocolError("DTC identifier must be a three-byte integer")
        if type(self.status_mask) is not int or not 0 <= self.status_mask <= 0xFF:
            raise UDSProtocolError("DTC status mask must be a byte")


@dataclass(frozen=True)
class UDSNegativeResponse:
    """A UDS negative response with its service, NRC, and display meaning."""

    service: int
    code: int
    meaning: str


_NRC_MEANINGS: dict[int, str] = {
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


def build_read_dtcs(*, tx_id: int, rx_id: int, status_mask: int = 0xFF) -> DiagnosticRequest:
    """Build ReadDTCInformation/report-by-status-mask request (0x19 0x02)."""
    _validate_byte(status_mask, "status mask")
    return build_uds_request(0x19, bytes((0x02, status_mask)), tx_id=tx_id, rx_id=rx_id)


def parse_read_dtcs(payload: bytes) -> tuple[UDSDTC, ...]:
    """Parse a 0x59 0x02 response, retaining every raw three-byte DTC."""
    _require_bytes(payload)
    if len(payload) < 3 or payload[:2] != bytes((0x59, 0x02)):
        raise UDSProtocolError("expected a UDS ReadDTCInformation 0x59 0x02 response")
    records = payload[3:]
    if len(records) % 4:
        raise UDSProtocolError("UDS DTC records must contain four bytes each")
    return tuple(
        UDSDTC(int.from_bytes(records[offset : offset + 3], "big"), records[offset + 3])
        for offset in range(0, len(records), 4)
    )


def build_read_did(did: int, *, tx_id: int, rx_id: int) -> DiagnosticRequest:
    """Build a catalog-approved ReadDataByIdentifier request (0x22)."""
    _validate_did(did)
    return build_uds_request(
        0x22,
        did.to_bytes(2, "big"),
        tx_id=tx_id,
        rx_id=rx_id,
        cataloged_did=True,
    )


def parse_read_did(payload: bytes, did: int) -> bytes:
    """Parse a 0x62 response and return data only after an exact DID echo."""
    _require_bytes(payload)
    _validate_did(did)
    expected = did.to_bytes(2, "big")
    if len(payload) < 3 or payload[0] != 0x62:
        raise UDSProtocolError("expected a UDS ReadDataByIdentifier 0x62 response")
    if payload[1:3] != expected:
        raise UDSProtocolError("UDS response DID does not match the requested DID")
    return payload[3:]


def parse_negative_response(payload: bytes) -> UDSNegativeResponse:
    """Decode one exact UDS negative response without attempting a retry or unlock."""
    _require_bytes(payload)
    if len(payload) != 3 or payload[0] != 0x7F:
        raise UDSProtocolError("UDS negative responses must be exactly 0x7F, service, NRC")
    service, code = payload[1], payload[2]
    return UDSNegativeResponse(service, code, _NRC_MEANINGS.get(code, "unknown"))


def _require_bytes(payload: bytes) -> None:
    if not isinstance(payload, bytes):
        raise TypeError("UDS payload must be bytes")


def _validate_byte(value: int, name: str) -> None:
    if type(value) is not int or not 0 <= value <= 0xFF:
        raise ValueError(f"{name} must be a byte")


def _validate_did(did: int) -> None:
    if type(did) is not int or not 0 <= did <= 0xFFFF:
        raise ValueError("DID must be a two-byte integer")
