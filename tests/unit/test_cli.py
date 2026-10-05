"""Smoke tests for the command-line entry point."""

from __future__ import annotations

from pathlib import Path

import pytest

import contam
from contam.cli import main


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert contam.__version__ in capsys.readouterr().out


def test_no_arguments_prints_help_and_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage:" in capsys.readouterr().out


def test_evaluate_demo_runs_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "run"
    code = main(
        [
            "evaluate",
            "--demo",
            "--demo-items",
            "80",
            "--background-docs",
            "120",
            "--items-per-spec",
            "8",
            "--controls",
            "100",
            "--n",
            "5",
            "--out",
            str(out),
            "--no-plots",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "frozen operating point" in output
    assert "TEST macro recall" in output
    assert (out / "operating_point.json").is_file()


def test_evaluate_without_any_items_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["evaluate"]) == 2
    assert "provide --benchmark" in capsys.readouterr().err


def test_evaluate_reports_infeasible_settings_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "evaluate",
            "--demo",
            "--demo-items",
            "40",
            "--background-docs",
            "40",
            "--items-per-spec",
            "3",
            "--controls",
            "5",
            "--n",
            "5",
            "--out",
            str(tmp_path / "run"),
            "--no-plots",
        ]
    )
    assert code == 2
    assert "error:" in capsys.readouterr().err
