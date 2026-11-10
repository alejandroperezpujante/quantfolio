"""Test configuration: keep matplotlib headless for every test layer."""

import os

os.environ.setdefault("MPLBACKEND", "Agg")
