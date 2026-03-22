"""Environment variables. Import this module early, before library initialization."""

import os

# Suppress Ray GPU override warning
os.environ.setdefault("RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO", "0")
# Prevent Ray from packaging the entire working directory (including .venv) when run via `uv run`
os.environ.setdefault("RAY_ENABLE_UV_RUN_RUNTIME_ENV", "0")
