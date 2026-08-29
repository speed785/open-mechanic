from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

import pytest

from open_mechanic.protocols.elm327 import (
    ELM327AdapterError,
    ELM327ConnectionError,
    ELM327Error,
    ELM327ProtocolError,
    ELM327TimeoutError,
    ELM327Transport,
    RawDiagnosticResponse,
)
from open_mechanic.protocols.isotp import ISOTPError
from open_mechanic.protocols.requests import DiagnosticRequest, build_uds_request


class FakeSerial:
    def __init__(self, responses: Mapping[str, str | bytes]) -> None:
        self.responses = dict(responses)
        self.pending = b""
        self.writes: list[bytes] = []
        self.closed = False
        self.close_raises = False
        self.short_writes = False

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        command = data.decode("ascii").strip()
        response = self.responses.get(command, "")
        self.pending = response if isinstance(response, bytes) else response.encode("ascii")
        return len(data) - 1 if self.short_writes else len(data)

    def flush(self) -> None:
        return None

    def read(self, size: int = 1) -> bytes:
        if not self.pending:
            return b""
        result, self.pending = self.pending[:size], self.pending[size:]
        return result

    def close(self) -> None:
        self.closed = True
        if self.close_raises:
            raise OSError("close failed")


@dataclass(frozen=True)
class ForgedRequest:
    protocol: object = object()
    service: int = 0x2E
    parameters: bytes = bytes.fromhex("F19001")
    tx_id: int = 0x7E0
    rx_id: int = 0x7E8
    cataloged_did: bool = True

    @property
    def payload(self) -> bytes:
        return bytes([self.service]) + self.parameters


def _responses(*, exchange: str | bytes) -> dict[str, str | bytes]:
    return {
        "ATZ": "OBDLink EX\r>",
        "ATE0": "OK\r>",
        "ATL0": "OK\r>",
        "ATS0": "OK\r>",
        "ATH1": "OK\r>",
        "ATCAF0": "OK\r>",
        "ATCFC1": "OK\r>",
        "ATSP6": "OK\r>",
        "ATSH7E0": "OK\r>",
        "ATCRA7E8": "OK\r>",
        "0322F190": exchange,
    }


def _factory(serial: FakeSerial) -> Callable[..., FakeSerial]:
    return lambda **_: serial


def _request() -> DiagnosticRequest:
    return build_uds_request(
        0x22,
        bytes.fromhex("F190"),
        tx_id=0x7E0,
        rx_id=0x7E8,
        cataloged_did=True,
    )


def test_exchange_initializes_raw_can_and_uses_validated_headers() -> None:
    serial = FakeSerial(
        _responses(exchange="7E8 10 0B 62 F1 90 31 4A\r7E8 21 34 46 59 35 39 30\r>")
    )
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))

    transport.open()
    result = transport.exchange(_request())

    assert result[0].responder_id == 0x7E8
    assert result[0].payload == bytes.fromhex("62F190314A344659353930")
    assert serial.writes == [
        b"ATZ\r",
        b"ATE0\r",
        b"ATL0\r",
        b"ATS0\r",
        b"ATH1\r",
        b"ATCAF0\r",
        b"ATCFC1\r",
        b"ATSP6\r",
        b"ATSH7E0\r",
        b"ATCRA7E8\r",
        b"0322F190\r",
    ]


def test_exchange_returns_no_responses_for_no_data() -> None:
    serial = FakeSerial(_responses(exchange="NO DATA\r>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()

    assert transport.exchange(_request()) == []


def test_exchange_rejects_forged_request_without_writing_to_serial() -> None:
    serial = FakeSerial(_responses(exchange="NO DATA\r>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()
    serial.writes.clear()

    with pytest.raises(ELM327ProtocolError):
        transport.exchange(cast(DiagnosticRequest, ForgedRequest()))

    assert serial.writes == []


@pytest.mark.parametrize(
    "field, value",
    [("service", 0x2E), ("parameters", "F190")],
)
def test_exchange_revalidates_mutated_request_without_writing_to_serial(
    field: str, value: int | str
) -> None:
    serial = FakeSerial(_responses(exchange="NO DATA\r>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    request = _request()
    object.__setattr__(request, field, value)
    transport.open()
    serial.writes.clear()

    with pytest.raises(ELM327ProtocolError):
        transport.exchange(request)

    assert serial.writes == []


def test_exchange_parses_compact_headers_when_spaces_are_disabled() -> None:
    serial = FakeSerial(_responses(exchange="7E80362F190\r>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()

    assert transport.exchange(_request()) == [RawDiagnosticResponse(0x7E8, bytes.fromhex("62F190"))]


@pytest.mark.parametrize("reply", ["STOPPED\r>", "BUS ERROR\r>"])
def test_exchange_rejects_adapter_errors(reply: str) -> None:
    serial = FakeSerial(_responses(exchange=reply))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()

    with pytest.raises(ELM327AdapterError):
        transport.exchange(_request())


@pytest.mark.parametrize("reply", ["NOT-A-FRAME\r>", "800 03 62 F1 90\r>"])
def test_exchange_rejects_malformed_can_header(reply: str) -> None:
    serial = FakeSerial(_responses(exchange=reply))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()

    with pytest.raises(ELM327ProtocolError):
        transport.exchange(_request())


def test_exchange_keeps_mixed_responders_separate() -> None:
    serial = FakeSerial(_responses(exchange="7E8 03 62 F1 90\r7E9 03 62 F1 91\r>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()

    assert transport.exchange(_request()) == [
        RawDiagnosticResponse(0x7E8, bytes.fromhex("62F190")),
        RawDiagnosticResponse(0x7E9, bytes.fromhex("62F191")),
    ]


def test_exchange_partitions_multiple_complete_messages_from_one_responder() -> None:
    serial = FakeSerial(
        _responses(
            exchange=(
                "7E8 03 7F 22 78\r"
                "7E8 10 0B 62 F1 90 31 4A\r"
                "7E8 21 34 46 59 35 39 30\r>"
            )
        )
    )
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()

    assert transport.exchange(_request()) == [
        RawDiagnosticResponse(0x7E8, bytes.fromhex("7F2278")),
        RawDiagnosticResponse(0x7E8, bytes.fromhex("62F190314A344659353930")),
    ]


@pytest.mark.parametrize(
    "exchange",
    [
        "7E8 03 62 F1 90\r7E8 21 AA BB CC DD EE FF 00\r>",
        "7E8 10 0B 62 F1 90 31 4A\r7E8 03 7F 22 78\r>",
    ],
)
def test_exchange_rejects_trailing_or_interleaved_message_sequences(exchange: str) -> None:
    serial = FakeSerial(_responses(exchange=exchange))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()

    with pytest.raises(ISOTPError):
        transport.exchange(_request())


def test_open_wraps_permission_errors() -> None:
    def denied(**_: object) -> FakeSerial:
        raise PermissionError("denied")

    with pytest.raises(ELM327ConnectionError):
        ELM327Transport("/dev/test", serial_factory=denied).open()


def test_open_uses_default_serial_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    serial = FakeSerial(_responses(exchange="NO DATA\r>"))
    captured: dict[str, object] = {}

    def create_serial(**kwargs: object) -> FakeSerial:
        captured.update(kwargs)
        return serial

    monkeypatch.setattr("open_mechanic.protocols.elm327.serial.Serial", create_serial)
    ELM327Transport("/dev/test", timeout=2.5).open()

    assert captured == {
        "port": "/dev/test",
        "baudrate": 115200,
        "timeout": 2.5,
        "write_timeout": 2.5,
    }


def test_open_accepts_expected_ate0_echo_before_disabling_echo() -> None:
    replies = _responses(exchange="NO DATA\r>")
    replies["ATE0"] = "ATE0\rOK\r>"
    transport = ELM327Transport("/dev/test", serial_factory=_factory(FakeSerial(replies)))

    transport.open()


def test_constructor_rejects_nonpositive_timeouts() -> None:
    with pytest.raises(ValueError):
        ELM327Transport("/dev/test", timeout=0)


def test_open_rejects_second_open() -> None:
    serial = FakeSerial(_responses(exchange="NO DATA\r>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()

    with pytest.raises(ELM327ConnectionError):
        transport.open()


def test_exchange_rejects_requests_that_do_not_fit_a_single_can_frame() -> None:
    serial = FakeSerial(_responses(exchange="NO DATA\r>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()
    request = build_uds_request(0x19, b"\x00" * 7, tx_id=0x7E0, rx_id=0x7E8)

    with pytest.raises(ELM327ProtocolError):
        transport.exchange(request)


def test_exchange_rejects_out_of_range_can_headers() -> None:
    serial = FakeSerial(_responses(exchange="NO DATA\r>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()
    request = build_uds_request(0x19, b"", tx_id=0x800, rx_id=0x7E8)

    with pytest.raises(ELM327ProtocolError):
        transport.exchange(request)


def test_exchange_rejects_partial_serial_writes() -> None:
    serial = FakeSerial(_responses(exchange="NO DATA\r>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()
    serial.short_writes = True

    with pytest.raises(ELM327ProtocolError):
        transport.exchange(_request())


def test_exchange_rejects_non_ascii_adapter_response() -> None:
    serial = FakeSerial(_responses(exchange=b"\xff>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()

    with pytest.raises(ELM327ProtocolError):
        transport.exchange(_request())


def test_exchange_rejects_oversized_adapter_response() -> None:
    serial = FakeSerial(_responses(exchange=("A" * 4097) + ">"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()

    with pytest.raises(ELM327ProtocolError):
        transport.exchange(_request())


def test_open_rejects_missing_prompt() -> None:
    serial = FakeSerial({"ATZ": "OBDLink EX\r"})
    with pytest.raises(ELM327TimeoutError):
        ELM327Transport("/dev/test", timeout=0.001, serial_factory=_factory(serial)).open()


@pytest.mark.parametrize(
    "reply, error",
    [("?\r>", ELM327AdapterError), (">", ELM327ProtocolError), ("NO\r>", ELM327ProtocolError)],
)
def test_open_rejects_bad_initialization_reply(reply: str, error: type[ELM327Error]) -> None:
    replies = _responses(exchange="NO DATA\r>")
    replies["ATZ" if reply != "NO\r>" else "ATE0"] = reply
    serial = FakeSerial(replies)
    with pytest.raises(error):
        ELM327Transport("/dev/test", serial_factory=_factory(serial)).open()


def test_open_rejects_echo_after_echo_is_disabled() -> None:
    replies = _responses(exchange="NO DATA\r>")
    replies["ATL0"] = "ATL0\rOK\r>"
    serial = FakeSerial(replies)

    with pytest.raises(ELM327ProtocolError):
        ELM327Transport("/dev/test", serial_factory=_factory(serial)).open()


def test_open_preserves_initialization_error_when_cleanup_fails() -> None:
    replies = _responses(exchange="NO DATA\r>")
    replies["ATE0"] = "NO\r>"
    serial = FakeSerial(replies)
    serial.close_raises = True

    with pytest.raises(ELM327ProtocolError, match="did not acknowledge ATE0"):
        ELM327Transport("/dev/test", serial_factory=_factory(serial)).open()

    assert serial.closed is True


def test_close_closes_serial_after_exchange_exception() -> None:
    serial = FakeSerial(_responses(exchange="BROKEN\r>"))
    transport = ELM327Transport("/dev/test", serial_factory=_factory(serial))
    transport.open()
    with pytest.raises(ELM327ProtocolError):
        transport.exchange(_request())

    transport.close()
    assert serial.closed is True


def test_exchange_requires_an_open_adapter() -> None:
    with pytest.raises(ELM327ConnectionError):
        ELM327Transport("/dev/test", serial_factory=lambda **_: FakeSerial({})).exchange(_request())
