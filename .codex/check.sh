#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy --follow-untyped-imports --check-untyped-defs src tests
.venv/bin/python -m unittest discover
