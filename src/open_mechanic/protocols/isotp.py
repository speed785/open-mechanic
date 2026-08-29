"""ISO-TP frame validation and payload reassembly for classic CAN."""

from dataclasses import dataclass


class ISOTPError(ValueError):
    """Base error for malformed or incomplete ISO-TP responses."""


class ISOTPFormatError(ISOTPError):
    """Raised when frames do not follow the supported ISO-TP format."""


class ISOTPSequenceError(ISOTPError):
    """Raised when a consecutive frame has the wrong sequence number."""


class ISOTPIncompleteError(ISOTPError):
    """Raised when a declared multi-frame payload is incomplete."""


class ISOTPMixedResponderError(ISOTPError):
    """Raised when a frame group contains more than one CAN sender."""


@dataclass(frozen=True)
class CANFrame:
    """A classic 11-bit CAN frame rendered by the adapter in raw mode."""

    responder_id: int
    data: bytes


def reassemble_isotp(frames: list[CANFrame]) -> bytes:
    """Reassemble one responder's raw ISO-TP frames without sending flow control."""
    if not frames:
        raise ISOTPFormatError("response has no CAN frames")

    responder_id = frames[0].responder_id
    _validate_frame(frames[0])
    for frame in frames[1:]:
        _validate_frame(frame)
        if frame.responder_id != responder_id:
            raise ISOTPMixedResponderError("ISO-TP frames came from multiple responders")

    first = frames[0].data
    frame_type = first[0] >> 4
    if frame_type == 0:
        return _single_frame_payload(first)
    if frame_type != 1:
        raise ISOTPFormatError("response must begin with a single or first ISO-TP frame")
    return _multiframe_payload(frames)


def _validate_frame(frame: CANFrame) -> None:
    if not 0 <= frame.responder_id <= 0x7FF:
        raise ISOTPFormatError("CAN responder ID must be an 11-bit value")
    if not 1 <= len(frame.data) <= 8:
        raise ISOTPFormatError("classic CAN frames must contain one to eight bytes")


def _single_frame_payload(data: bytes) -> bytes:
    length = data[0] & 0x0F
    if length > 7 or len(data) < length + 1:
        raise ISOTPFormatError("single frame length does not match its data")
    return data[1 : length + 1]


def _multiframe_payload(frames: list[CANFrame]) -> bytes:
    first = frames[0].data
    if len(first) < 2:
        raise ISOTPFormatError("first frame is missing its length byte")
    length = ((first[0] & 0x0F) << 8) | first[1]
    if length < 8:
        raise ISOTPFormatError("first frame must declare at least eight bytes")

    payload = bytearray(first[2:])
    expected_sequence = 1
    for frame in frames[1:]:
        data = frame.data
        if data[0] >> 4 != 2:
            raise ISOTPFormatError("multi-frame response contains a non-consecutive frame")
        if data[0] & 0x0F != expected_sequence:
            raise ISOTPSequenceError("consecutive frame sequence number is invalid")
        payload.extend(data[1:])
        expected_sequence = (expected_sequence + 1) & 0x0F
        if len(payload) >= length:
            break

    if len(payload) < length:
        raise ISOTPIncompleteError("multi-frame response ended before its declared length")
    return bytes(payload[:length])
