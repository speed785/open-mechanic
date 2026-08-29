"""Bounded ELM/STN serial transport for read-only diagnostic requests."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast

import serial

from open_mechanic.protocols.isotp import CANFrame, reassemble_isotp
from open_mechanic.protocols.requests import DiagnosticRequest


class ELM327Error(RuntimeError):
    """Base error for the bounded ELM/STN transport."""


class ELM327ConnectionError(ELM327Error):
    """Raised when the serial adapter cannot be opened."""


class ELM327TimeoutError(ELM327Error):
    """Raised when an adapter reply does not terminate with a prompt."""


class ELM327ProtocolError(ELM327Error):
    """Raised for malformed adapter replies or unsupported request framing."""


class ELM327AdapterError(ELM327Error):
    """Raised for a terminal diagnostic error reported by the adapter."""


class SerialPort(Protocol):
    def write(self, data: bytes) -> int: ...

    def flush(self) -> None: ...

    def read(self, size: int = 1) -> bytes: ...

    def close(self) -> None: ...


SerialFactory = Callable[..., SerialPort]


@dataclass(frozen=True)
class RawDiagnosticResponse:
    responder_id: int
    payload: bytes


_CAN_LINE = re.compile(r"^([0-9A-F]{3}) ((?:[0-9A-F]{2})(?: [0-9A-F]{2})*)$")
_COMPACT_CAN_LINE = re.compile(r"^([0-9A-F]{3})((?:[0-9A-F]{2})+)$")
_ADAPTER_ERRORS = frozenset(
    {"?", "ERROR", "STOPPED", "BUS ERROR", "CAN ERROR", "BUFFER FULL", "UNABLE TO CONNECT"}
)
_INITIALIZATION_COMMANDS = ("ATZ", "ATE0", "ATL0", "ATS0", "ATH1", "ATCAF0", "ATCFC1", "ATSP6")


def _default_serial_factory(**kwargs: object) -> SerialPort:
    return cast(SerialPort, serial.Serial(**kwargs))


class ELM327Transport:
    """Serial transport that only emits CAN frames built from ``DiagnosticRequest``."""

    def __init__(
        self,
        port: str,
        *,
        timeout: float = 1.0,
        serial_factory: SerialFactory = _default_serial_factory,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._port = port
        self._timeout = timeout
        self._serial_factory = serial_factory
        self._serial: SerialPort | None = None
        self._echo_disabled = False

    def open(self) -> None:
        """Open and configure the adapter for raw CAN response formatting."""
        if self._serial is not None:
            raise ELM327ConnectionError("adapter is already open")
        try:
            self._serial = self._serial_factory(
                port=self._port,
                baudrate=115200,
                timeout=self._timeout,
                write_timeout=self._timeout,
            )
            for command in _INITIALIZATION_COMMANDS:
                lines = self._command(command)
                self._validate_initialization(command, lines)
                if command == "ATE0":
                    self._echo_disabled = True
        except (OSError, serial.SerialException) as error:
            self.close()
            raise ELM327ConnectionError(f"could not open OBD adapter at {self._port}") from error
        except Exception:
            self.close()
            raise

    def exchange(self, request: DiagnosticRequest) -> list[RawDiagnosticResponse]:
        """Send one bounded single-frame request and parse raw ISO-TP responses."""
        self._require_open()
        self._validate_can_id(request.tx_id, "transmit")
        self._validate_can_id(request.rx_id, "receive")
        payload = request.payload
        if len(payload) > 7:
            raise ELM327ProtocolError("transport only permits bounded single-frame requests")

        self._expect_ok(self._command(f"ATSH{request.tx_id:03X}"), "ATSH")
        self._expect_ok(self._command(f"ATCRA{request.rx_id:03X}"), "ATCRA")
        lines = self._command(f"{len(payload):02X}{payload.hex().upper()}")
        if lines == ["NO DATA"]:
            return []
        if any(line in _ADAPTER_ERRORS for line in lines):
            raise ELM327AdapterError("adapter rejected diagnostic request")

        frames_by_responder: dict[int, list[CANFrame]] = defaultdict(list)
        for line in lines:
            frame = self._parse_can_frame(line)
            frames_by_responder[frame.responder_id].append(frame)
        return [
            RawDiagnosticResponse(responder_id, reassemble_isotp(frames))
            for responder_id, frames in frames_by_responder.items()
        ]

    def close(self) -> None:
        """Close the current serial connection, if one is open."""
        current_serial, self._serial = self._serial, None
        self._echo_disabled = False
        if current_serial is not None:
            current_serial.close()

    def _command(self, command: str) -> list[str]:
        serial_port = self._require_open()
        encoded = f"{command}\r".encode("ascii")
        if serial_port.write(encoded) != len(encoded):
            raise ELM327ProtocolError("adapter did not accept a complete command")
        serial_port.flush()
        lines = self._read_until_prompt(serial_port)
        if self._echo_disabled and any(line == command for line in lines):
            raise ELM327ProtocolError("adapter echoed a command after ATE0")
        return lines

    def _read_until_prompt(self, serial_port: SerialPort) -> list[str]:
        reply = bytearray()
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            byte = serial_port.read(1)
            if not byte:
                continue
            if byte == b">":
                return self._normalize_lines(bytes(reply))
            reply.extend(byte)
            if len(reply) > 4096:
                raise ELM327ProtocolError("adapter response exceeded 4096 bytes")
        raise ELM327TimeoutError("adapter response did not include a prompt")

    @staticmethod
    def _normalize_lines(reply: bytes) -> list[str]:
        try:
            decoded = reply.decode("ascii")
        except UnicodeDecodeError as error:
            raise ELM327ProtocolError("adapter response was not ASCII") from error
        return [" ".join(line.upper().split()) for line in decoded.splitlines() if line.strip()]

    @staticmethod
    def _validate_initialization(command: str, lines: list[str]) -> None:
        if any(line in _ADAPTER_ERRORS or line == "NO DATA" for line in lines):
            raise ELM327AdapterError(f"adapter rejected {command}")
        if command == "ATZ":
            if not lines:
                raise ELM327ProtocolError("adapter did not identify itself after reset")
            return
        ELM327Transport._expect_ok(lines, command)

    @staticmethod
    def _expect_ok(lines: list[str], command: str) -> None:
        if lines != ["OK"]:
            raise ELM327ProtocolError(f"adapter did not acknowledge {command}")

    @staticmethod
    def _parse_can_frame(line: str) -> CANFrame:
        match = _CAN_LINE.fullmatch(line) or _COMPACT_CAN_LINE.fullmatch(line)
        if match is None:
            raise ELM327ProtocolError("adapter response did not contain an 11-bit CAN frame")
        responder_id = int(match.group(1), 16)
        if responder_id > 0x7FF:
            raise ELM327ProtocolError("adapter response used a non-11-bit CAN header")
        data = bytes.fromhex(match.group(2))
        return CANFrame(responder_id, data)

    @staticmethod
    def _validate_can_id(can_id: int, direction: str) -> None:
        if not 0 <= can_id <= 0x7FF:
            raise ELM327ProtocolError(f"{direction} CAN ID must be an 11-bit value")

    def _require_open(self) -> SerialPort:
        if self._serial is None:
            raise ELM327ConnectionError("adapter is not open")
        return self._serial
