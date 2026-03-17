from __future__ import annotations

# pyright: reportMissingTypeStubs=false
import enum
import glob
import logging
import os
import platform
import time

import obd
from dotenv import load_dotenv
from serial.tools import list_ports

_ = load_dotenv()

logger = logging.getLogger(__name__)


class ConnectionStatus(enum.Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


def get_default_port() -> str:
    system_name = platform.system()
    if system_name == "Linux":
        return "/dev/ttyUSB0"

    if system_name == "Darwin":
        cu_matches = glob.glob("/dev/cu.usbserial-*")
        if cu_matches:
            return cu_matches[0]

        tty_matches = glob.glob("/dev/tty.usbserial-*")
        if tty_matches:
            return tty_matches[0]

        return "/dev/cu.usbserial-0"

    if system_name == "Windows":
        return "COM3"

    return "/dev/ttyUSB0"


def scan_ports() -> list[str]:
    system_name = platform.system()
    ports: list[str] = []

    if system_name == "Linux":
        ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    elif system_name == "Darwin":
        ports = glob.glob("/dev/cu.usbserial-*") + glob.glob("/dev/tty.usbserial-*")
    elif system_name == "Windows":
        ports = [port.device for port in list_ports.comports()]

    return sorted(ports)


class OBDConnection:
    def __init__(
        self,
        port: str | None = None,
        baudrate: int | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        env_port = os.getenv("OBD_PORT")
        scanned_ports = scan_ports()
        resolved_port = port or env_port or (scanned_ports[0] if scanned_ports else get_default_port())

        self._connection: obd.OBD | None = None
        self._status: ConnectionStatus = ConnectionStatus.DISCONNECTED
        self._port: str = resolved_port
        self._baudrate: int | None = baudrate
        self._timeout: float = timeout
        self._max_retries: int = max_retries
        self._platform: str = platform.system()

    def connect(self) -> bool:
        self._status = ConnectionStatus.CONNECTING
        for attempt in range(1, self._max_retries + 1):
            logger.info(
                "Connecting to OBD adapter on %s (attempt %s/%s)",
                self._port,
                attempt,
                self._max_retries,
            )
            try:
                connection = obd.OBD(
                    portstr=self._port,
                    baudrate=self._baudrate or 0,
                    timeout=self._timeout,
                    check_voltage=False,
                )
                if connection.is_connected():
                    self._connection = connection
                    self._status = ConnectionStatus.CONNECTED
                    protocol_name = connection.protocol_name()
                    logger.info(
                        "Connected to OBD adapter on %s using protocol %s",
                        self._port,
                        protocol_name,
                    )
                    return True

                logger.warning("Connection attempt %s failed: adapter not connected", attempt)
            except Exception as exc:
                logger.warning("Connection attempt %s failed with error: %s", attempt, exc)

            self._connection = None

            if attempt < self._max_retries:
                if attempt == 1:
                    delay_seconds = 0.5
                elif attempt == 2:
                    delay_seconds = 1.0
                else:
                    delay_seconds = 2.0
                logger.warning("Retrying OBD connection in %.1f seconds", delay_seconds)
                time.sleep(delay_seconds)

        self._status = ConnectionStatus.FAILED
        logger.error(
            "Failed to connect to OBD adapter on %s after %s attempts",
            self._port,
            self._max_retries,
        )
        return False

    def disconnect(self) -> None:
        if self._connection is not None:
            self._connection.close()
            logger.info("Disconnected OBD adapter on %s", self._port)

        self._status = ConnectionStatus.DISCONNECTED
        self._connection = None

    def is_connected(self) -> bool:
        return (
            self._status == ConnectionStatus.CONNECTED
            and self._connection is not None
            and self._connection.is_connected()
        )

    def get_status(self) -> ConnectionStatus:
        return self._status

    def get_port(self) -> str:
        return self._port

    def get_connection(self) -> obd.OBD | None:
        return self._connection

    def __enter__(self) -> OBDConnection:
        _ = self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.disconnect()
