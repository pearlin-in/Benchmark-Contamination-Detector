"""Command-line entry point. Subcommands are added phase by phase."""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from contam import __version__
from contam.compare import compare_methods, write_compare_csv
from contam.corrupt import DEFAULT_SPECS
from contam.data.benchmarks import BENCHMARKS, load_benchmark, load_items_jsonl
from contam.data.corpus import limit_documents, stream_documents
from contam.data.jsonl import read_jsonl
from contam.dupes import find_near_duplicates
from contam.evaluate import load_operating_point
from contam.experiment import ExperimentConfig, run_experiment
from contam.inject import Document, build_planted_corpus
from contam.items import BenchmarkItem, View
from contam.report import build_report, format_report
from contam.scan import RawDocument, ScanConfig, ScanError, run_scan
from contam.split import split_documents, split_items
from contam.synthetic import synthetic_background, synthetic_items


def _add_source_args(parser: argparse.ArgumentParser) -> None:
    source = parser.add_argument_group("benchmark items (choose at least one)")
    source.add_argument("--benchmark", action="append", choices=sorted(BENCHMARKS), default=[])
    source.add_argument("--items-jsonl", action="append", default=[], metavar="PATH")
    source.add_argument("--demo", action="store_true", help="use synthetic items (no network)")
    source.add_argument("--demo-items", type=int, default=300)
    source.add_argument("--split", default="test", help="benchmark split to load")
    source.add_argument("--max-items", type=int, default=None, help="cap items per benchmark")
    background = parser.add_argument_group("background corpus")
    background.add_argument("--background", choices=("synthetic", "fineweb"), default="synthetic")
    background.add_argument("--background-docs", type=int, default=2000)


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
    _add_source_args(evaluate)
    design = evaluate.add_argument_group("experiment design")
    design.add_argument("--items-per-spec", type=int, default=100)
    design.add_argument("--controls", type=int, default=500)
    design.add_argument("--n", type=int, action="append", dest="ns", default=None)
    design.add_argument("--stop-k", type=int, action="append", dest="stop_ks", default=None)
    design.add_argument("--max-control-fpr", type=float, default=0.05)
    design.add_argument("--seed", type=int, default=0)
    design.add_argument("--out", type=Path, default=Path("results/phase4"))
    design.add_argument("--no-plots", action="store_true")
    design.add_argument(
        "--window-slack",
        type=float,
        action="append",
        dest="window_slacks",
        default=None,
        help="also evaluate window-localized containment with this slack (repeatable)",
    )

    compare = commands.add_parser(
        "compare",
        help="compare exact n-gram containment with fuzzy MinHash matching",
        description=(
            "Run several detectors on the same held-out planted corpus with one fixed "
            "threshold (not tuned on this data) and print recall by corruption condition."
        ),
    )
    _add_source_args(compare)
    study = compare.add_argument_group("comparison design")
    study.add_argument("--items-per-spec", type=int, default=50)
    study.add_argument("--controls", type=int, default=300)
    study.add_argument("--exact-n", type=int, action="append", dest="exact_ns", default=None)
    study.add_argument("--fuzzy-k", type=int, action="append", dest="fuzzy_ks", default=None)
    study.add_argument("--threshold", type=float, default=0.3)
    study.add_argument("--num-perm", type=int, default=64)
    study.add_argument("--bands", type=int, default=32)
    study.add_argument("--windowed-n", type=int, action="append", dest="windowed_ns", default=None)
    study.add_argument("--window-slack", type=float, default=1.5)
    study.add_argument("--seed", type=int, default=0)
    study.add_argument("--out", type=Path, default=Path("results/phase5_compare"))

    dupes = commands.add_parser(
        "dupes",
        help="find near-duplicate benchmark items with MinHash + LSH",
        description="Near-duplicate items within one split, or between two splits.",
    )
    dupes.add_argument("--benchmark", choices=sorted(BENCHMARKS), required=True)
    dupes.add_argument("--split-a", default="test")
    dupes.add_argument("--split-b", default=None, help="compare split A against this split")
    dupes.add_argument("--threshold", type=float, default=0.5, help="minimum Jaccard similarity")
    dupes.add_argument("--k", type=int, default=3, help="word shingle size")
    dupes.add_argument("--num-perm", type=int, default=128)
    dupes.add_argument("--show", type=int, default=10, help="print the top N pairs")
    dupes.add_argument("--out", type=Path, default=None, help="write all pairs to this CSV")
    scan = commands.add_parser(
        "scan",
        help="scan a corpus stream for benchmark items (checkpointed, multi-process)",
        description=(
            "Index the benchmark items and scan a corpus slice. Safe to interrupt: rerun with "
            "--resume. Settings come from an operating_point.json written by 'contam evaluate' "
            "unless overridden by flags."
        ),
    )
    _add_source_args(scan)
    tune = scan.add_argument_group("detector settings")
    tune.add_argument("--operating-point", type=Path, default=None)
    tune.add_argument("--n", type=int, default=None)
    tune.add_argument("--view", choices=[v.value for v in View], default=None)
    tune.add_argument("--partial", type=float, default=None)
    tune.add_argument("--near", type=float, default=None)
    tune.add_argument("--window-slack", type=float, default=None)
    tune.add_argument("--no-window", action="store_true", help="whole-document containment")
    tune.add_argument("--stop-k", type=int, default=None)
    corpus = scan.add_argument_group("corpus slice")
    corpus.add_argument("--corpus-config", default="sample-10BT", help="FineWeb config name")
    corpus.add_argument("--corpus-jsonl", type=Path, default=None, help="scan a local JSONL file")
    corpus.add_argument("--max-tokens", type=int, default=None, help="stop after this many tokens")
    corpus.add_argument("--max-docs", type=int, default=None)
    corpus.add_argument("--demo-docs", type=int, default=200, help="documents for --demo")
    run = scan.add_argument_group("run")
    run.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    run.add_argument("--batch-docs", type=int, default=500)
    run.add_argument("--snippet-chars", type=int, default=200)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--out", type=Path, default=Path("results/scan"))
    run.add_argument("--resume", action="store_true")
    run.add_argument("--overwrite", action="store_true")

    report = commands.add_parser("report", help="summarize a scan folder as a table")
    report.add_argument("--scan", type=Path, required=True, help="folder written by 'contam scan'")
    report.add_argument("--top", type=int, default=10, help="show the strongest N hits")
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
        window_slacks=(None, *(args.window_slacks or ())),
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


def _run_compare(args: argparse.Namespace) -> int:
    items = _collect_items(args)
    if not items:
        print("error: provide --benchmark, --items-jsonl or --demo", file=sys.stderr)
        return 2
    try:
        _, test_items = split_items(items, 0.5, args.seed)
        _, test_background = split_documents(_collect_background(args), 0.5, args.seed)
        corpus = build_planted_corpus(
            test_items,
            test_background,
            DEFAULT_SPECS,
            items_per_spec=args.items_per_spec,
            n_controls=args.controls,
            seed=args.seed,
        )
        rows = compare_methods(
            items,
            corpus,
            exact_ns=tuple(args.exact_ns) if args.exact_ns else (2, 3, 5),
            fuzzy_ks=tuple(args.fuzzy_ks) if args.fuzzy_ks else (3,),
            windowed=tuple((n, args.window_slack) for n in (args.windowed_ns or ())),
            threshold=args.threshold,
            num_perm=args.num_perm,
            bands=args.bands,
            seed=args.seed,
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    write_compare_csv(args.out / "compare.csv", rows)

    methods = list(dict.fromkeys(row.method for row in rows))
    specs = list(dict.fromkeys(row.spec for row in rows))
    recall = {(row.method, row.spec): row.recall for row in rows}
    print(f"threshold {args.threshold} (fixed, not tuned here); recall on the held-out test split")
    if args.windowed_ns:
        print(f"win = window-localized containment, slack {args.window_slack}")
    print(f"{'condition':24}" + "".join(f"{method:>13}" for method in methods))
    for spec in specs:
        print(f"{spec:24}" + "".join(f"{recall[(m, spec)]:>13.2f}" for m in methods))
    first = {row.method: row for row in rows}
    flagged = "".join(f"{first[m].control_flagged:>13}" for m in methods)
    seconds = "".join(f"{first[m].seconds:>13.1f}" for m in methods)
    print(f"{'controls flagged':24}{flagged}")
    print(f"{'seconds':24}{seconds}")
    print(f"artifacts written to {args.out}")
    return 0


def _run_dupes(args: argparse.Namespace) -> int:
    items_a = load_benchmark(args.benchmark, split=args.split_a)
    items_b = load_benchmark(args.benchmark, split=args.split_b) if args.split_b else None
    try:
        pairs = find_near_duplicates(
            items_a,
            items_b,
            k=args.k,
            jaccard_threshold=args.threshold,
            num_perm=args.num_perm,
        )
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    scope = f"{args.split_a} vs {args.split_b}" if args.split_b else f"within {args.split_a}"
    print(f"{args.benchmark} ({scope}): {len(items_a)} items")
    for level in (0.5, 0.7, 0.9):
        if level >= args.threshold:
            count = sum(pair.jaccard >= level for pair in pairs)
            print(f"  near-duplicate pairs with Jaccard >= {level}: {count}")
    text = {item.item_id: item.question for item in [*items_a, *(items_b or [])]}
    for pair in pairs[: args.show]:
        print(f"{pair.jaccard:.2f}  {pair.id_a} ~ {pair.id_b}")
        print(f"      {text[pair.id_a][:90]!r}")
        print(f"      {text[pair.id_b][:90]!r}")
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["id_a", "id_b", "jaccard"])
            writer.writerows((pair.id_a, pair.id_b, f"{pair.jaccard:.4f}") for pair in pairs)
        print(f"wrote {len(pairs)} pairs to {args.out}")
    return 0


def _scan_settings(args: argparse.Namespace) -> ScanConfig:
    point = load_operating_point(args.operating_point) if args.operating_point else None
    defaults = ScanConfig()
    n = args.n if args.n is not None else (point.n if point else defaults.n)
    view = args.view or (point.view if point else defaults.view)
    partial = args.partial if args.partial is not None else (point.partial if point else 0.5)
    near = args.near if args.near is not None else (point.near_duplicate if point else 0.9)
    stop_k = args.stop_k if args.stop_k is not None else (point.stop_ngram_k if point else None)
    slack = args.window_slack if args.window_slack is not None else defaults.window_slack
    if args.window_slack is None and point is not None:
        slack = point.window_slack
    return ScanConfig(
        n=n,
        view=View(view),
        partial=partial,
        near_duplicate=near,
        window_slack=None if args.no_window else slack,
        stop_ngram_k=stop_k,
        snippet_chars=args.snippet_chars,
        batch_docs=args.batch_docs,
        workers=args.workers,
    )


def _scan_source(
    args: argparse.Namespace, items: list[BenchmarkItem]
) -> tuple[Callable[[], Iterable[RawDocument]], str]:
    if args.corpus_jsonl is not None:
        path = args.corpus_jsonl

        def from_file() -> Iterable[RawDocument]:
            return limit_documents(
                read_jsonl(path), max_docs=args.max_docs, max_tokens=args.max_tokens
            )

        size = path.stat().st_size
        return from_file, f"jsonl:{path.name}:{size}:{args.max_docs}:{args.max_tokens}"
    if args.demo:
        corpus = build_planted_corpus(
            items,
            synthetic_background(args.demo_docs, seed=args.seed),
            DEFAULT_SPECS,
            items_per_spec=5,
            n_controls=args.demo_docs,
            seed=args.seed,
        )
        return (lambda: corpus.documents), f"demo:{args.seed}:{args.demo_docs}:{len(items)}"

    def from_fineweb() -> Iterable[RawDocument]:
        return stream_documents(
            name=args.corpus_config, max_docs=args.max_docs, max_tokens=args.max_tokens
        )

    return from_fineweb, f"fineweb:{args.corpus_config}:{args.max_docs}:{args.max_tokens}"


def _run_scan(args: argparse.Namespace) -> int:
    items = _collect_items(args)
    if not items:
        print("error: provide --benchmark, --items-jsonl or --demo", file=sys.stderr)
        return 2
    factory, source = _scan_source(args, items)
    config = replace(_scan_settings(args), source=source)
    print(
        f"scanning {len(items)} items: n={config.n}, view={config.view}, "
        f"partial={config.partial}, near={config.near_duplicate}, "
        f"window_slack={config.window_slack}, workers={config.workers}"
    )

    def show(state: dict[str, Any]) -> None:
        docs = int(state["docs_done"])
        if docs % (config.batch_docs * 10) < config.batch_docs:
            print(
                f"  {docs:,} docs, {int(state['tokens_done']):,} tokens, "
                f"{state['hits_written']} hits"
            )

    try:
        result = run_scan(
            items,
            factory,
            config,
            args.out,
            resume=args.resume,
            overwrite=args.overwrite,
            progress=show,
        )
    except (ScanError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    rate = result.tokens / result.seconds if result.seconds else 0.0
    print(
        f"done: {result.docs:,} docs, {result.tokens:,} tokens in {result.seconds:.0f}s "
        f"({rate:,.0f} tokens/s)"
    )
    print(format_report(build_report(args.out)))
    return 0


def _run_report(args: argparse.Namespace) -> int:
    try:
        print(format_report(build_report(args.scan, args.top)))
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "evaluate":
        return _run_evaluate(args)
    if args.command == "compare":
        return _run_compare(args)
    if args.command == "dupes":
        return _run_dupes(args)
    if args.command == "scan":
        return _run_scan(args)
    if args.command == "report":
        return _run_report(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
