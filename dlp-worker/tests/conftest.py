"""Pytest configuration — ensure src packages are importable."""

from __future__ import annotations

import sys
from pathlib import Path

# Add the worker src directory to the Python path so that
# `import feed.item` works from within tests.
_SRC = Path(__file__).resolve().parent.parent / "src"

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
