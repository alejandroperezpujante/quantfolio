"""Test configuration: force a headless matplotlib backend."""

import os

os.environ.setdefault("MPLBACKEND", "Agg")
