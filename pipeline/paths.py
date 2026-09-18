"""Repo-root paths. Pipeline scripts live in pipeline/; data stays at the root."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def use_repo_root() -> Path:
    """Make relative paths (tray_photos/, runs/, ...) resolve from the repo root."""
    os.chdir(ROOT)
    if str(ROOT / "pipeline") not in sys.path:
        sys.path.insert(0, str(ROOT / "pipeline"))
    return ROOT
