import pytest

from open_mechanic.protocols.isotp import (
    CANFrame,
    ISOTPFormatError,
    ISOTPIncompleteError,
    ISOTPMixedResponderError,
    ISOTPSequenceError,
    reassemble_isotp,
)


def test_reassembles_single_frame_payload() -> None:
    assert reassemble_isotp([CANFrame(0x7E8, bytes.fromhex("03590102AABBCCDD"))]) == bytes.fromhex(
        "590102"
    )


def test_rejects_empty_frame_list() -> None:
    with pytest.raises(ISOTPFormatError):
        reassemble_isotp([])


@pytest.mark.parametrize(
    "frame",
    [CANFrame(0x800, b"\x00"), CANFrame(0x7E8, b""), CANFrame(0x7E8, b"\x00" * 9)],
)
def test_rejects_invalid_classic_can_frame(frame: CANFrame) -> None:
    with pytest.raises(ISOTPFormatError):
        reassemble_isotp([frame])


def test_reassembles_multiframe_payload() -> None:
    frames = [
        CANFrame(0x7E8, bytes.fromhex("100A5902ABCDEF01")),
        CANFrame(0x7E8, bytes.fromhex("2123456700000000")),
    ]
    assert reassemble_isotp(frames) == bytes.fromhex("5902ABCDEF0123456700")


def test_rejects_wrong_sequence_number() -> None:
    frames = [
        CANFrame(0x7E8, bytes.fromhex("100A5902ABCDEF01")),
        CANFrame(0x7E8, bytes.fromhex("2223456700000000")),
    ]
    with pytest.raises(ISOTPSequenceError):
        reassemble_isotp(frames)


def test_rejects_incomplete_multiframe_payload() -> None:
    with pytest.raises(ISOTPIncompleteError):
        reassemble_isotp([CANFrame(0x7E8, bytes.fromhex("100A5902ABCDEF01"))])


def test_rejects_first_frame_with_single_frame_length() -> None:
    with pytest.raises(ISOTPFormatError):
        reassemble_isotp([CANFrame(0x7E8, bytes.fromhex("10075902ABCDEF01"))])


def test_rejects_non_consecutive_frame_in_multiframe_response() -> None:
    frames = [
        CANFrame(0x7E8, bytes.fromhex("10085902ABCDEF01")),
        CANFrame(0x7E8, bytes.fromhex("300000")),
    ]
    with pytest.raises(ISOTPFormatError):
        reassemble_isotp(frames)


def test_rejects_frames_from_multiple_responders() -> None:
    frames = [
        CANFrame(0x7E8, bytes.fromhex("100A5902ABCDEF01")),
        CANFrame(0x7E9, bytes.fromhex("2123456700000000")),
    ]
    with pytest.raises(ISOTPMixedResponderError):
        reassemble_isotp(frames)


@pytest.mark.parametrize(
    "data",
    [bytes.fromhex("08"), bytes.fromhex("300000"), bytes.fromhex("10")],
)
def test_rejects_malformed_or_flow_control_frames(data: bytes) -> None:
    with pytest.raises(ISOTPFormatError):
        reassemble_isotp([CANFrame(0x7E8, data)])
