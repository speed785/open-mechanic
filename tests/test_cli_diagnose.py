from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from rich.console import Console

from open_mechanic.ai.providers import DiagnosticProvider
from open_mechanic.diagnosis_cli import run_ai_diagnosis
from open_mechanic.tools import MENU_ITEMS, main


class FakeProvider(DiagnosticProvider):
    name = "fake-cloud"

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            {
                "severity": "warning",
                "summary": "Catalyst efficiency is below expected range.",
                "likely_causes": ["Aged catalytic converter", "Exhaust leak"],
                "repair_steps": ["Inspect exhaust", "Test oxygen sensors"],
                "estimated_cost_usd": {"low": 150, "high": 1200},
                "diy_feasible": False,
                "diy_difficulty": "hard",
                "urgency": "soon",
                "disclaimer": "ignored",
            }
        )


def test_tools_menu_exposes_ai_diagnosis() -> None:
    assert ("diagnose", "AI Diagnosis") in MENU_ITEMS


def test_main_accepts_diagnose_help(capsys) -> None:  # type: ignore[no-untyped-def]
    status = main(["diagnose", "--help"])
    captured = capsys.readouterr()

    assert status == 0
    assert "--provider" in captured.out
    assert "--offline" in captured.out


def test_run_ai_diagnosis_offline_renders_provider_and_report(tmp_path: Path) -> None:
    output = Console(record=True, width=100)
    args = Namespace(
        vehicle="2018 Ford F-150",
        mileage=85000,
        vin=None,
        port=None,
        protocol=None,
        timeout=10.0,
        baudrate=115200,
        provider="auto",
        offline=True,
        no_vin_decode=False,
        report_dir=str(tmp_path),
    )

    status = run_ai_diagnosis(args, output, provider=FakeProvider())

    rendered = output.export_text()
    reports = list(tmp_path.glob("*-diagnosis.json"))
    assert status == 0
    assert "fake-cloud" in rendered
    assert "Catalyst efficiency is below expected range." in rendered
    assert reports
