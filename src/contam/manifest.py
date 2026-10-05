"""Run manifests: everything needed to reproduce or audit a result (DECISIONS.md, D-015)."""

from __future__ import annotations

import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import contam


def git_commit(start: Path | None = None) -> str | None:
    """Current commit hash read straight from ``.git`` (no subprocess), or ``None``."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        git_dir = directory / ".git"
        if not git_dir.is_dir():
            continue
        try:
            head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
            if not head.startswith("ref: "):
                return head
            ref = head[5:]
            ref_file = git_dir / ref
            if ref_file.is_file():
                return ref_file.read_text(encoding="utf-8").strip()
            packed = git_dir / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(f" {ref}"):
                        return line.split(" ", 1)[0]
        except OSError:
            return None
        return None
    return None


def build_run_manifest(
    config: dict[str, Any], extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Provenance record for one run."""
    manifest: dict[str, Any] = {
        "contam_version": contam.__version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "config": config,
    }
    if extra:
        manifest["extra"] = extra
    return manifest
