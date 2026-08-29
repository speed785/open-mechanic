from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from rich.console import Console
from scripts import diagnose as diagnose_script

from open_mechanic import tools
from open_mechanic.local_store import VehicleProfile


class _Connection:
    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def get_connection(self) -> object:
        return type("Raw", (), {"protocol_name": lambda self: "CAN", "supported_commands": []})()

    def get_port(self) -> str:
        return "/dev/test"


def test_generic_snapshot_creates_no_files_or_directories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[object] = []
    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: writes.append((args, kwargs)))
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: writes.append((args, kwargs)))
    monkeypatch.setattr(tools, "OBDConnection", lambda **kwargs: _Connection())
    monkeypatch.setattr(tools, "show_health_snapshot", lambda *args: None)
    args = argparse.Namespace(port=None, protocol=None, baudrate=115200, timeout=1)
    profile = VehicleProfile(2020, "Example", "Vehicle")

    assert tools.run_direct_tool("snapshot", args, Console(file=None), profile=profile) == 0
    assert writes == []


def test_tools_module_does_not_import_persistence_helpers() -> None:
    for name in (
        "ensure_local_dirs",
        "load_vehicle_profile",
        "save_vehicle_profile",
        "SessionLog",
    ):
        assert not hasattr(tools, name)


def test_noninteractive_ai_diagnosis_requires_share_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        diagnose_script,
        "_parse_args",
        lambda: diagnose_script._Args(
            vehicle="2020 Example Vehicle",
            mileage=1,
            vin=None,
            port=None,
            protocol=None,
            model=None,
            share_with_ai=False,
        ),
    )
    monkeypatch.setattr(
        diagnose_script,
        "OBDConnection",
        lambda **kwargs: pytest.fail("adapter must not be accessed without authorization"),
    )

    assert diagnose_script.main() == 1
