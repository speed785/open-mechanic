from __future__ import annotations

# pyright: reportMissingTypeStubs=false,reportUnknownVariableType=false,reportUnknownMemberType=false,reportUnknownArgumentType=false,reportAttributeAccessIssue=false
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import obd

from .connection import OBDConnection

logger = logging.getLogger(__name__)


class DTCClearNotConfirmed(Exception):
    """Raised when clear_dtcs() is called without confirmed=True."""


@dataclass
class DTCCode:
    code: str
    description: str
    status: str
    severity: str
    category: str


class DTCReader:
    def __init__(self, connection: OBDConnection, dtc_db_path: str = "data/dtc_codes.json") -> None:
        self._connection: OBDConnection = connection
        self._db: dict[str, dict[str, str]] = self._load_dtc_db(dtc_db_path)

    def _load_dtc_db(self, dtc_db_path: str) -> dict[str, dict[str, str]]:
        db_path = Path(dtc_db_path)
        try:
            payload: object = json.loads(db_path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
        except FileNotFoundError:
            logger.warning("DTC database file not found at %s; proceeding with empty database", dtc_db_path)
            return {}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed loading DTC database at %s: %s", dtc_db_path, exc)
            return {}

        if not isinstance(payload, list):
            logger.warning("DTC database at %s is not a list; proceeding with empty database", dtc_db_path)
            return {}

        db: dict[str, dict[str, str]] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue

            entry = item
            raw_code = entry.get("code")
            if not isinstance(raw_code, str):
                continue

            code = raw_code.strip().upper()
            if not code:
                continue

            description = entry.get("description")
            severity = entry.get("severity")
            category = entry.get("category")
            db[code] = {
                "description": description if isinstance(description, str) and description else "Unknown code",
                "severity": severity if isinstance(severity, str) and severity else "unknown",
                "category": category if isinstance(category, str) and category else "unknown",
            }

        return db

    def _read_dtc_command(self, command: object, status: str) -> list[DTCCode]:
        conn = self._connection.get_connection()
        if conn is None:
            return []

        try:
            response = conn.query(command)
        except Exception as exc:
            logger.warning("Failed querying DTC command: %s", exc)
            return []

        if response is None or response.is_null() or response.value is None:
            return []

        if not isinstance(response.value, list):
            return []

        parsed_codes: list[DTCCode] = []
        for item in response.value:
            if not isinstance(item, tuple) or not item:
                continue

            raw_code = item[0]
            if not isinstance(raw_code, str):
                continue

            code = raw_code.strip().upper()
            if not code:
                continue

            details = self._db.get(code)
            parsed_codes.append(
                DTCCode(
                    code=code,
                    description=details["description"] if details else "Unknown code",
                    status=status,
                    severity=details["severity"] if details else "unknown",
                    category=details["category"] if details else "unknown",
                )
            )

        return parsed_codes

    def get_dtcs(self) -> list[DTCCode]:
        conn = self._connection.get_connection()
        if conn is None or not self._connection.is_connected():
            return []

        pending_command: object | None = getattr(obd.commands, "GET_CURRENT_DTC", None)
        confirmed_command: object | None = getattr(obd.commands, "GET_DTC", None)
        if pending_command is None and confirmed_command is None:
            return []

        pending_codes = (
            self._read_dtc_command(pending_command, status="pending") if pending_command is not None else []
        )
        confirmed_codes = (
            self._read_dtc_command(confirmed_command, status="confirmed")
            if confirmed_command is not None
            else []
        )

        deduplicated: dict[str, DTCCode] = {dtc.code: dtc for dtc in pending_codes}
        for dtc in confirmed_codes:
            deduplicated[dtc.code] = dtc

        return sorted(deduplicated.values(), key=lambda dtc: dtc.code)

    def decode(self, code: str) -> DTCCode:
        normalized_code = code.upper()
        details = self._db.get(normalized_code)
        if details is None:
            return DTCCode(
                code=code,
                description="Unknown code",
                status="unknown",
                severity="unknown",
                category="unknown",
            )

        return DTCCode(
            code=normalized_code,
            description=details["description"],
            status="unknown",
            severity=details["severity"],
            category=details["category"],
        )

    def clear_dtcs(self, confirmed: bool = False) -> bool:
        if confirmed is not True:
            raise DTCClearNotConfirmed(
                "Call clear_dtcs(confirmed=True) to confirm clearing fault codes."
            )

        conn = self._connection.get_connection()
        if conn is None or not self._connection.is_connected():
            return False

        clear_command: object | None = getattr(obd.commands, "CLEAR_DTC", None)
        if clear_command is None:
            return False

        try:
            _ = conn.query(clear_command)
        except Exception as exc:
            logger.warning("Failed clearing DTCs: %s", exc)
            return False

        logger.warning("DTC codes were cleared")
        return True
