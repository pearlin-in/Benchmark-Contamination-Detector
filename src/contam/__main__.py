"""Allows ``python -m contam ...`` (a reliable alternative to the ``contam`` script)."""

from contam.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
