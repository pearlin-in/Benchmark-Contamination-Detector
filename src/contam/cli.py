"""Command-line entry point. Subcommands are added phase by phase."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from contam import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contam",
        description="Detect benchmark test-set contamination in open pretraining corpora.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
