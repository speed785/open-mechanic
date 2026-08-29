from dataclasses import dataclass
from enum import Enum

READ_ONLY_OBD_MODES = frozenset({0x01, 0x02, 0x03, 0x07, 0x09, 0x0A})
READ_ONLY_UDS_SERVICES = frozenset({0x19, 0x22, 0x3E})
TESTER_PRESENT_SUBFUNCTIONS = frozenset({b"\x00", b"\x80"})


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
        if not isinstance(self.protocol, DiagnosticProtocol):
            raise UnsafeDiagnosticRequest("unknown diagnostic protocol")
        allowed = (
            READ_ONLY_OBD_MODES
            if self.protocol is DiagnosticProtocol.OBD
            else READ_ONLY_UDS_SERVICES
        )
        if self.service not in allowed:
            raise UnsafeDiagnosticRequest(f"service 0x{self.service:02X} is not read-only")
        if (
            self.protocol is DiagnosticProtocol.UDS
            and self.service == 0x22
            and not self.cataloged_did
        ):
            raise UnsafeDiagnosticRequest("UDS 0x22 requires a cataloged DID")
        if (
            self.protocol is DiagnosticProtocol.UDS
            and self.service == 0x3E
            and self.parameters not in TESTER_PRESENT_SUBFUNCTIONS
        ):
            raise UnsafeDiagnosticRequest("UDS 0x3E requires an allowed subfunction")

    @property
    def payload(self) -> bytes:
        return bytes([self.service]) + self.parameters


def build_obd_request(
    mode: int, pid: int | None = None, *, tx_id: int, rx_id: int
) -> DiagnosticRequest:
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
