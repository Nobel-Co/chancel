"""Test fixtures shared across the suite.

Makes ``scripts/`` importable as plain modules (not a package) so tests can
``from generate_corpus import generate`` without turning ``scripts/`` -- which
is meant to stay a standalone CLI directory -- into a package.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
