"""End-to-end test of the dev -> freeze -> test experiment on synthetic data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from contam.experiment import ExperimentConfig, run_experiment
from contam.synthetic import synthetic_background, synthetic_items

from contam.evaluate import load_operating_point
from contam.inject import read_manifest

pytestmark = pytest.mark.integration

ITEMS = synthetic_items(120, seed=21)
BACKGROUND = synthetic_background(160, seed=21)
CONFIG = ExperimentConfig(
    ns=(5, 8),
    partials=(0.3, 0.5),
    near_duplicates=(0.9,),
    items_per_spec=12,
    n_controls=80,
    seed=21,
)


def test_experiment_writes_every_artifact(tmp_path: Path) -> None:
    run_experiment(ITEMS, BACKGROUND, CONFIG, tmp_path, make_plots=False)
    names = {path.name for path in tmp_path.iterdir()}
    assert {
        "dev_sweep.csv",
        "dev_manifest.jsonl",
        "operating_point.json",
        "test_conditions.csv",
        "test_summary.json",
        "test_manifest.jsonl",
        "test_sweep.csv",
        "run_manifest.json",
    } <= names


def test_dev_and_test_plant_different_items(tmp_path: Path) -> None:
    run_experiment(ITEMS, BACKGROUND, CONFIG, tmp_path, make_plots=False)
    dev_items = {plant.item_id for plant in read_manifest(tmp_path / "dev_manifest.jsonl")}
    test_items = {plant.item_id for plant in read_manifest(tmp_path / "test_manifest.jsonl")}
    assert dev_items
    assert test_items
    assert dev_items.isdisjoint(test_items)


def test_dev_and_test_use_different_host_documents(tmp_path: Path) -> None:
    run_experiment(ITEMS, BACKGROUND, CONFIG, tmp_path, make_plots=False)
    dev_hosts = {plant.host_doc_id for plant in read_manifest(tmp_path / "dev_manifest.jsonl")}
    test_hosts = {plant.host_doc_id for plant in read_manifest(tmp_path / "test_manifest.jsonl")}
    assert dev_hosts.isdisjoint(test_hosts)


def test_the_frozen_point_is_what_the_test_set_was_evaluated_at(tmp_path: Path) -> None:
    result = run_experiment(ITEMS, BACKGROUND, CONFIG, tmp_path, make_plots=False)
    frozen = load_operating_point(tmp_path / "operating_point.json")
    assert frozen == result.operating_point
    summary = json.loads((tmp_path / "test_summary.json").read_text(encoding="utf-8"))
    assert summary["thresholds"] == {
        "partial": frozen.partial,
        "near_duplicate": frozen.near_duplicate,
    }


def test_ground_truth_checks_hold_on_the_held_out_test_set(tmp_path: Path) -> None:
    result = run_experiment(ITEMS, BACKGROUND, CONFIG, tmp_path, make_plots=False)
    by_spec = {c.spec: c for c in result.test_summary.conditions}
    assert by_spec["verbatim"].recall == 1.0
    assert by_spec["format_noise"].recall == 1.0
    assert result.test_summary.control_flagged == 0


def test_experiment_is_reproducible(tmp_path: Path) -> None:
    first = run_experiment(ITEMS, BACKGROUND, CONFIG, tmp_path / "a", make_plots=False)
    second = run_experiment(ITEMS, BACKGROUND, CONFIG, tmp_path / "b", make_plots=False)
    assert first.operating_point == second.operating_point
    assert first.test_summary == second.test_summary
    for name in ("dev_sweep.csv", "test_conditions.csv", "dev_manifest.jsonl"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_too_few_items_fails_with_a_clear_message(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="provide more items"):
        run_experiment(ITEMS[:1], BACKGROUND, CONFIG, tmp_path, make_plots=False)


def test_plots_are_written_when_matplotlib_is_available(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    run_experiment(ITEMS, BACKGROUND, CONFIG, tmp_path, make_plots=True)
    assert (tmp_path / "dev_recall_vs_edit_rate.png").stat().st_size > 1000
    assert (tmp_path / "test_recall_by_condition.png").stat().st_size > 1000
