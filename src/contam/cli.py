"""Command-line entry point. Subcommands are added phase by phase."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from contam import __version__
from contam.data.benchmarks import BENCHMARKS, load_benchmark, load_items_jsonl
from contam.data.corpus import stream_documents
from contam.experiment import ExperimentConfig, run_experiment
from contam.inject import Document
from contam.items import BenchmarkItem, View
from contam.synthetic import synthetic_background, synthetic_items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contam",
        description="Detect benchmark test-set contamination in open pretraining corpora.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")

    evaluate = commands.add_parser(
        "evaluate",
        help="plant corrupted benchmark items in a corpus and measure detector recall",
        description=(
            "Tune the detector on a dev half, freeze the settings, and report recall and "
            "false-positive rate on a held-out test half (planted-ground-truth evaluation)."
        ),
    )
    source = evaluate.add_argument_group("benchmark items (choose at least one)")
    source.add_argument("--benchmark", action="append", choices=sorted(BENCHMARKS), default=[])
    source.add_argument("--items-jsonl", action="append", default=[], metavar="PATH")
    source.add_argument("--demo", action="store_true", help="use synthetic items (no network)")
    source.add_argument("--demo-items", type=int, default=300)
    source.add_argument("--split", default="test", help="benchmark split to load")
    source.add_argument("--max-items", type=int, default=None, help="cap items per benchmark")

    background = evaluate.add_argument_group("background corpus")
    background.add_argument("--background", choices=("synthetic", "fineweb"), default="synthetic")
    background.add_argument("--background-docs", type=int, default=2000)

    design = evaluate.add_argument_group("experiment design")
    design.add_argument("--items-per-spec", type=int, default=100)
    design.add_argument("--controls", type=int, default=500)
    design.add_argument("--n", type=int, action="append", dest="ns", default=None)
    design.add_argument("--stop-k", type=int, action="append", dest="stop_ks", default=None)
    design.add_argument("--max-control-fpr", type=float, default=0.05)
    design.add_argument("--seed", type=int, default=0)
    design.add_argument("--out", type=Path, default=Path("results/phase4"))
    design.add_argument("--no-plots", action="store_true")
    return parser


def _collect_items(args: argparse.Namespace) -> list[BenchmarkItem]:
    items: list[BenchmarkItem] = []
    if args.demo:
        items.extend(synthetic_items(args.demo_items, seed=args.seed))
    for name in args.benchmark:
        loaded = load_benchmark(name, split=args.split)
        items.extend(loaded[: args.max_items] if args.max_items else loaded)
    for path in args.items_jsonl:
        loaded = load_items_jsonl(path)
        items.extend(loaded[: args.max_items] if args.max_items else loaded)
    return items


def _collect_background(args: argparse.Namespace) -> list[Document]:
    if args.background == "fineweb":
        return list(stream_documents(max_docs=args.background_docs))
    return synthetic_background(args.background_docs, seed=args.seed)


def _run_evaluate(args: argparse.Namespace) -> int:
    items = _collect_items(args)
    if not items:
        print("error: provide --benchmark, --items-jsonl or --demo", file=sys.stderr)
        return 2
    config = ExperimentConfig(
        ns=tuple(args.ns) if args.ns else (5, 8, 13),
        stop_ks=tuple(args.stop_ks) if args.stop_ks else (None,),
        primary_view=View.QUESTION_CHOICES,
        items_per_spec=args.items_per_spec,
        n_controls=args.controls,
        max_control_fpr_upper=args.max_control_fpr,
        seed=args.seed,
    )
    try:
        result = run_experiment(
            items,
            _collect_background(args),
            config,
            args.out,
            make_plots=not args.no_plots,
            extra_manifest={"background": args.background, "benchmarks": sorted(args.benchmark)},
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    point = result.operating_point
    summary = result.test_summary
    print(f"dev items: {result.n_dev_items}   test items: {result.n_test_items}")
    print(
        f"frozen operating point (chosen on dev): n={point.n}, view={point.view}, "
        f"partial={point.partial}, near_duplicate={point.near_duplicate}"
    )
    print(
        f"TEST macro recall: {summary.macro_recall:.3f}   "
        f"control flagged: {summary.control_flagged}/{summary.control_docs} "
        f"(upper bound {summary.control_fpr_high:.3f})   unindexed plants: {summary.unindexed}"
    )
    print(f"{'condition':24}{'n':>5}{'recall':>9}{'95% CI':>18}")
    for condition in summary.conditions:
        interval = f"[{condition.recall_low:.2f}, {condition.recall_high:.2f}]"
        print(f"{condition.spec:24}{condition.planted:>5}{condition.recall:>9.2f}{interval:>18}")
    print(f"artifacts written to {result.out_dir}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "evaluate":
        return _run_evaluate(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
