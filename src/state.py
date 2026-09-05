"""Shared type contract for Pathwise.

FROZEN after PR #1. Three workstreams build against these types, so a change here
breaks W2, W3 and W4 at the same time. If something genuinely does not fit, open an
issue and let Alvin change it in a dedicated PR that everyone rebases onto.

RunState is a TypedDict rather than a Pydantic model because that is the most
reliably documented LangGraph state shape. Everything inside it is Pydantic, so
validation still happens at every boundary.
"""

from __future__ import annotations

import operator
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums. Use these instead of bare strings so typos fail at parse time.
# ---------------------------------------------------------------------------


class Dimension(StrEnum):
    """The five readiness dimensions shown as bars in the interface."""

    PROGRAMMING = "programming"
    SYSTEMS = "systems"
    DATA = "data"
    TOOLING = "tooling"
    COMMUNICATION = "communication"


class SourceName(StrEnum):
    NUSMODS = "nusmods"
    DEVPOST = "devpost"
    GITHUB = "github"
    FIXTURE = "fixture"  # set when a tool falls back to committed sample data


class CandidateKind(StrEnum):
    MODULE = "module"
    HACKATHON = "hackathon"
    PROJECT = "project"


class TraceKind(StrEnum):
    """Entry types in the unified decision log. The UI styles each differently."""

    OBSERVED = "observed"  # something read from data
    PLANNED = "planned"  # the planner deciding what to do
    DECIDED = "decided"  # a ranking or selection made
    CHANGED = "changed"  # a re-plan caused by new information
    ACTION = "action"  # something the agent did or proposes to do
    USER = "user"  # something the student said or logged


# ---------------------------------------------------------------------------
# Profile. Produced by W3 (Stevson) from an uploaded transcript and resume.
# ---------------------------------------------------------------------------


class CompletedModule(BaseModel):
    code: str  # "CS2106"
    title: str
    units: float
    grade: str | None = None


class Evidence(BaseModel):
    """Something the student has already demonstrably done.

    This is what the redundancy penalty checks against. A candidate that closes a
    gap the student already has evidence for scores lower than one that does not.
    Keep `label` in a small consistent vocabulary or the set intersection will miss.
    """

    label: str  # "rest api", lowercase, normalised
    dimension: Dimension
    source_text: str  # the resume line it came from, for the UI to cite


class StudentProfile(BaseModel):
    name: str
    year: int
    major: str
    target_role: str  # must be a key in config.ROLE_DIMENSION_WEIGHTS
    completed_modules: list[CompletedModule] = Field(default_factory=list)
    units_completed: float = 0
    units_required: float = 160
    evidence: list[Evidence] = Field(default_factory=list)

    @property
    def completed_codes(self) -> set[str]:
        return {m.code for m in self.completed_modules}

    @property
    def evidence_labels(self) -> set[str]:
        return {e.label for e in self.evidence}


# ---------------------------------------------------------------------------
# Readiness assessment. Produced by W3, consumed by the planner and the scorer.
# ---------------------------------------------------------------------------


class DimensionScore(BaseModel):
    dimension: Dimension
    score: float = Field(ge=0.0, le=1.0)
    rationale: str


class Gap(BaseModel):
    dimension: Dimension
    label: str  # "Distributed systems" - human readable, shown in the UI
    priority: int  # 1 is highest
    current: float = Field(ge=0.0, le=1.0)
    target: float = Field(ge=0.0, le=1.0)

    @property
    def size(self) -> float:
        return max(0.0, self.target - self.current)


class Readiness(BaseModel):
    dimensions: list[DimensionScore]
    gaps: list[Gap]  # ranked, priority 1 first


# ---------------------------------------------------------------------------
# Candidates and scoring. Produced by W2, scored by W1.
# ---------------------------------------------------------------------------


class ScoreComponents(BaseModel):
    """Four decomposable parts, not one opaque match percentage.

    gap_coverage and role_fit come from the model. time_cost and
    redundancy_penalty are computed in Python. Keeping the split visible is what
    makes a ranking defensible to a judge.
    """

    gap_coverage: float = Field(ge=0.0, le=1.0)  # model
    role_fit: float = Field(ge=0.0, le=1.0)  # model
    time_cost: float = Field(ge=0.0, le=1.0)  # code, 1.0 means cheap
    redundancy_penalty: float = Field(ge=0.0, le=1.0)  # code, 1.0 means fully redundant
    total: float  # code, weighted sum from config.SCORE_WEIGHTS
    rationale: str = ""


class Candidate(BaseModel):
    """Anything a sub-agent can return, whatever the source.

    One shape for modules, hackathons and projects so the scorer and the UI do not
    branch on kind. Fields that only apply to one kind are optional.
    """

    id: str  # stable and unique: "nusmods:CS3210", "devpost:hack-abc"
    kind: CandidateKind
    source: SourceName
    title: str
    description: str = ""
    url: str | None = None

    # module only
    units: float | None = None
    prerequisites_met: bool | None = None

    # hackathon and project
    deadline: date | None = None

    time_cost_hours: float | None = None
    closes_gaps: list[str] = Field(default_factory=list)  # Gap.label values
    scores: ScoreComponents | None = None


# ---------------------------------------------------------------------------
# Trace, actions, metrics.
# ---------------------------------------------------------------------------


class TraceEvent(BaseModel):
    """One entry in the decision log.

    This is the real execution record and it renders directly in the UI. Never
    write a trace entry describing something the code did not actually do.
    """

    kind: TraceKind
    agent: str  # "Career Agent", "Module Agent", "Profile Agent"
    message: str  # one line, shown in the log
    detail: str | None = None  # expandable second line
    at: datetime = Field(default_factory=datetime.now)


class PendingAction(BaseModel):
    id: str
    action_type: str  # "add_to_roadmap", "draft_application", "submit_application"
    label: str  # shown in the approval dialog
    candidate_id: str | None = None
    auto_approvable: bool = True  # False for submit_application, always


class Outcome(BaseModel):
    """A result the student logs, which causes a re-plan. Act two of the demo."""

    candidate_id: str
    result: str  # "not_shortlisted", "accepted", "withdrew"
    logged_at: datetime = Field(default_factory=datetime.now)


class RunMetrics(BaseModel):
    """Filled by W3.4. These numbers are the testing slide, so they must be real."""

    tool_calls_attempted: int = 0
    tool_calls_succeeded: int = 0
    schema_validations_passed: int = 0
    schema_validations_failed: int = 0
    fallbacks_used: int = 0
    refine_iterations: int = 0
    candidates_before_filter: int = 0
    candidates_after_filter: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# Graph state.
# ---------------------------------------------------------------------------


class RunState(TypedDict, total=False):
    """LangGraph state.

    `candidates` and `trace` use operator.add as their reducer, so concurrent
    sub-agent nodes append rather than overwrite each other. Every other key is
    last-write-wins, so only one node should ever set each of them.
    """

    run_id: str
    profile: StudentProfile | None
    readiness: Readiness | None

    # planner output
    dispatch: list[str]  # agent names to run
    skipped: list[str]  # agent names deliberately not run

    # fan-out results, appended concurrently
    candidates: Annotated[list[Candidate], operator.add]
    trace: Annotated[list[TraceEvent], operator.add]

    pending: list[PendingAction]
    approved: list[str]  # PendingAction ids
    outcomes: list[Outcome]

    iteration: int  # checked against config.MAX_REFINE_ITERATIONS
    metrics: RunMetrics


def new_run_state(run_id: str) -> RunState:
    """Build an empty state. Use this rather than assembling the dict by hand."""
    return RunState(
        run_id=run_id,
        profile=None,
        readiness=None,
        dispatch=[],
        skipped=[],
        candidates=[],
        trace=[],
        pending=[],
        approved=[],
        outcomes=[],
        iteration=0,
        metrics=RunMetrics(),
    )