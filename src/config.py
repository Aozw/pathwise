"""Constants for Pathwise.

FROZEN after PR #1, same as state.py.

Nothing in here does any work. No imports from the rest of src/, no I/O, no logic.
If you find yourself wanting to put a function here, it belongs in scoring.py.

Model ids are read from this file and never written inline anywhere else.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# The one piece of I/O in this file. Every entry point needs the .env loaded and
# making each of them remember it is how you get a confusing auth failure at 2am.
# Local development only: the deployed Lambda and AgentCore Runtime get their
# credentials from their IAM execution role, never from a .env file.
load_dotenv()

# ---------------------------------------------------------------------------
# AWS
# ---------------------------------------------------------------------------

# us-east-1, per the organisers' access guide. Bedrock permissions in the
# sandbox account are granted there. A wall of "Access denied to
# bedrock:ListFoundationModels" almost always means wrong region, not missing
# permissions. Do not change this without checking with the whole team.
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Run scripts/verify_aws.py and paste the exact ids it prints. Depending on what
# the sandbox has enabled these are either bare model ids
# ("anthropic.claude-3-haiku-20240307-v1:0") or region-prefixed inference
# profiles ("us.anthropic.claude-haiku-4-5-..."). They are not interchangeable
# and a string copied from a blog post will not work.
MODEL_HAIKU = os.environ.get("MODEL_HAIKU", "")

# Only for transcript parsing, and only if Haiku proves unreliable there.
# Try Haiku first. Every Sonnet call is roughly an order of magnitude more expensive.
MODEL_SONNET = os.environ.get("MODEL_SONNET", "")

# W2.1b's module embedding index (offline build) and the single per-query embedding
# call at runtime (src/tools/retrieval.py) both use this. Confirmed available
# ON_DEMAND in this account's region via `bedrock list-foundation-models`.
MODEL_EMBEDDING = os.environ.get("MODEL_EMBEDDING", "amazon.titan-embed-text-v2:0")

S3_BUCKET = os.environ.get("S3_BUCKET", "pathwise-state")
S3_STATE_PREFIX = "profiles/"
S3_RUNS_PREFIX = "runs/"

# ---------------------------------------------------------------------------
# Hard caps. Every model-influenced loop reads its bound from here.
# ---------------------------------------------------------------------------

MAX_REFINE_ITERATIONS = 3
MAX_CANDIDATES_SCORED = 30  # never send more than this to the scoring model
SHORTLIST_K = 25  # semantic shortlist size, if W2.1b gets built
SCORE_THRESHOLD = 0.55  # below this a candidate is not shown

TOOL_TIMEOUT_SECONDS = 8
TOOL_RETRIES = 1  # one retry, then fall back to the fixture

# The score node's one batched Bedrock call judges up to MAX_CANDIDATES_SCORED
# candidates in a single structured-output response (up to 4000 output tokens),
# which measured ~12s end to end during Step 15 verification - several times
# TOOL_TIMEOUT_SECONDS, which is sized for a single lightweight tool call. Reusing
# that constant here made the score call time out on every real run, so it never
# had anything but the neutral-default fallback and `ranked` stayed empty.
SCORE_TIMEOUT_SECONDS = 30

# ---------------------------------------------------------------------------
# Scoring. gap_coverage and role_fit come from the model; the other two are
# computed in Python. redundancy_penalty is subtracted, everything else added.
# ---------------------------------------------------------------------------

SCORE_WEIGHTS = {
    "gap_coverage": 0.40,
    "role_fit": 0.25,
    "time_cost": 0.15,
    "redundancy_penalty": -0.20,
}

# How much each dimension matters for a given target role. Values per role must
# sum to 1.0. Add a role here rather than special-casing it in the scorer.
ROLE_DIMENSION_WEIGHTS: dict[str, dict[str, float]] = {
    "backend_infrastructure": {
        "programming": 0.25,
        "systems": 0.35,
        "data": 0.20,
        "tooling": 0.15,
        "communication": 0.05,
    },
    "data_engineering": {
        "programming": 0.20,
        "systems": 0.20,
        "data": 0.40,
        "tooling": 0.15,
        "communication": 0.05,
    },
    "product_engineering": {
        "programming": 0.30,
        "systems": 0.15,
        "data": 0.15,
        "tooling": 0.20,
        "communication": 0.20,
    },
}

DEFAULT_ROLE = "backend_infrastructure"

# Rough hours of commitment, used to normalise time_cost. A module is a semester,
# a hackathon is a weekend. Deliberately coarse; precision here is false comfort.
TIME_COST_HOURS = {
    "module": 120.0,
    "hackathon": 40.0,
    "project": 60.0,
}
MAX_TIME_COST_HOURS = 120.0  # divisor when normalising to 0..1

# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

# Action types the student may set to auto-approve in settings.
AUTO_APPROVABLE_ACTIONS = {"add_to_roadmap", "draft_application", "track_deadline"}

# Never automatable under any setting. The toggle for these is permanently
# disabled in the UI, and the graph must refuse even if state says otherwise.
NEVER_AUTOMATED_ACTIONS = {"submit_application"}

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Budget. The lease card shows $30, but the real cap is $20: at $20 account
# access is revoked, and at $30 the account and everything in it is terminated.
# Cost reporting lags by hours, so the bar you are looking at is always stale.
# Treat $12 as the point where you stop experimenting, because that is where the
# organisers send the warning email.
# ---------------------------------------------------------------------------

BUDGET_HARD_CAP_USD = 20.0
BUDGET_WARNING_USD = 12.0

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

NUSMODS_ACADEMIC_YEAR = "2025-2026"
NUSMODS_BASE_URL = "https://api.nusmods.com/v2"

AGENT_NAMES = ["Module Agent", "Event Agent", "Project Agent"]