from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

LOCAL_DATA_DIR = Path("local_data")
PROFILE_PATH = LOCAL_DATA_DIR / "vehicle_profile.json"
SESSIONS_DIR = LOCAL_DATA_DIR / "sessions"


@dataclass
class VehicleProfile:
    year: int
    make: str
    model: str
    mileage: int | None = None

    @property
    def label(self) -> str:
        parts = [str(self.year), self.make.strip(), self.model.strip()]
        return " ".join(part for part in parts if part)


def ensure_local_dirs() -> None:
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def load_vehicle_profile() -> VehicleProfile | None:
    try:
        payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(payload, dict):
        return None

    year = payload.get("year")
    make = payload.get("make")
    model = payload.get("model")
    mileage = payload.get("mileage")
    if not isinstance(year, int) or not isinstance(make, str) or not isinstance(model, str):
        return None
    if mileage is not None and not isinstance(mileage, int):
        mileage = None

    return VehicleProfile(year=year, make=make, model=model, mileage=mileage)


def save_vehicle_profile(profile: VehicleProfile) -> None:
    ensure_local_dirs()
    PROFILE_PATH.write_text(
        json.dumps(asdict(profile), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class SessionLog:
    def __init__(self, tool_name: str, profile: VehicleProfile | None) -> None:
        ensure_local_dirs()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_tool = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in tool_name)
        self.path = SESSIONS_DIR / f"{timestamp}-{safe_tool}.jsonl"
        self.write(
            "session_started",
            {
                "tool": tool_name,
                "vehicle": asdict(profile) if profile is not None else None,
            },
        )

    def write(self, event: str, payload: dict[str, Any]) -> None:
        row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
