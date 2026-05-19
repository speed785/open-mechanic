from __future__ import annotations

import threading
import time

# pyright: reportMissingTypeStubs=false, reportUnknownArgumentType=false
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import obd

from open_mechanic.connection import OBDConnection


@dataclass
class SensorValue:
    name: str
    value: str
    unit: str | None
    timestamp: datetime
    supported: bool


SENSOR_COMMANDS: list[str] = [
    "RPM",
    "SPEED",
    "COOLANT_TEMP",
    "INTAKE_TEMP",
    "MAF",
    "THROTTLE_POS",
    "O2_B1S1",
    "O2_B1S2",
    "SHORT_FUEL_TRIM_1",
    "LONG_FUEL_TRIM_1",
    "CONTROL_MODULE_VOLTAGE",
    "ENGINE_LOAD",
    "TIMING_ADVANCE",
]


class SensorPoller:
    def __init__(self, connection: OBDConnection, interval: float = 1.0) -> None:
        self._connection: OBDConnection = connection
        self._interval: float = interval
        self._polling: bool = False
        self._thread: threading.Thread | None = None

    def get_snapshot(self) -> dict[str, SensorValue]:
        conn = self._connection.get_connection()
        if conn is None or not conn.is_connected():
            return {}

        snapshot: dict[str, SensorValue] = {}
        now = datetime.now()

        for name in SENSOR_COMMANDS:
            if name not in obd.commands:
                continue

            try:
                cmd = obd.commands[name]
                if cmd not in conn.supported_commands:
                    snapshot[name] = SensorValue(
                        name=name,
                        value="N/A",
                        unit=None,
                        timestamp=now,
                        supported=False,
                    )
                    continue

                response = conn.query(cmd)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                if response is None or response.is_null():  # pyright: ignore[reportUnknownMemberType]
                    snapshot[name] = SensorValue(
                        name=name,
                        value="N/A",
                        unit=None,
                        timestamp=now,
                        supported=False,
                    )
                    continue

                raw_value = response.value  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                magnitude = getattr(raw_value, "magnitude", raw_value)
                unit_value = getattr(raw_value, "units", None)
                value = f"{magnitude:.2f}" if isinstance(magnitude, float) else str(magnitude)
                unit = str(unit_value) if unit_value is not None else None  # pyright: ignore[reportAny]

                snapshot[name] = SensorValue(
                    name=name,
                    value=value,
                    unit=unit,
                    timestamp=now,
                    supported=True,
                )
            except Exception:
                snapshot[name] = SensorValue(
                    name=name,
                    value="N/A",
                    unit=None,
                    timestamp=now,
                    supported=False,
                )

        return snapshot

    def start_polling(self, callback: Callable[[dict[str, SensorValue]], None]) -> None:
        if self._polling:
            return

        def poll_loop() -> None:
            while self._polling:
                snapshot = self.get_snapshot()
                callback(snapshot)
                time.sleep(self._interval)

        self._polling = True
        self._thread = threading.Thread(target=poll_loop, daemon=True)
        self._thread.start()

    def stop_polling(self) -> None:
        self._polling = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def is_polling(self) -> bool:
        return self._polling
