"""Unit tests for infra/deploy.py's credential preflight — W4.6 follow-up.

Only `missing_env_vars` is tested: it's the pure part of `_ensure_credentials()`.
The STS `get_caller_identity()` call in that same function is a real AWS call by
design (it's what turns an expired 12-hour token into a clear message instead of
a stack trace three steps into a real deploy) and CLAUDE.md's hard rule against
calling external APIs from tests covers it, same as every other infra/*.py
script — none of them are unit tested beyond pure helpers like this one.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "infra"))

from deploy import REQUIRED_ENV_VARS, missing_env_vars  # noqa: E402


def test_missing_env_vars_reports_absent_and_empty_values():
    environ = {"AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "", "AWS_REGION": "us-east-1"}
    assert missing_env_vars(environ) == ["AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]


def test_missing_env_vars_empty_when_all_present():
    environ = {name: "value" for name in REQUIRED_ENV_VARS}
    assert missing_env_vars(environ) == []
