"""Graph wiring — W1.2, the skeleton.

Every node here is either a stub (agents/*.py) or a temporary placeholder defined
inline below. Nothing is real yet; the point of this module is that the edges, the
conditional fan-out and the refine loop with its hard cap all exist and run end to
end, so Aaron has something deployable while W1.3-W1.6 and W2.1-W2.5 fill the nodes
in on separate branches.

Flow:
    START -> profile -> planner -> (fan out on dispatch) -> module / event / project
           -> score -> refine_gate -> planner (loop, capped) or END

Two nodes below are temporary and live in this file rather than their eventual home:

  * profile: src/agents/profile.py is Stevson's (W3.1-W3.3) and is empty right now.
    This file cannot depend on it without breaking the graph, and W2 ownership does not
    extend to writing Stevson's node. Replace `_profile_stub` with an import of
    `profile_node` from src.agents.profile once W3.1 lands.
  * score: src/scoring.py is W1.4, not yet built. `_score_stub` is a pure pass-through
    that does not write `state["ranked"]` at all yet. The real score node will populate
    `ranked` (plain last-write-wins) rather than rewriting `candidates` (operator.add) -
    see the RunState docstring in state.py for why the two fields are split.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.agents.event import event_node
from src.agents.module import module_node
from src.agents.planner import planner_node
from src.agents.project import project_node
from src.config import DEFAULT_ROLE, MAX_REFINE_ITERATIONS
from src.state import (
    Dimension,
    DimensionScore,
    Gap,
    Readiness,
    RunState,
    StudentProfile,
    TraceEvent,
    TraceKind,
)

# Maps the display names the planner writes into `dispatch` (config.AGENT_NAMES) onto
# the graph node keys those agents actually run as.
NODE_BY_AGENT_NAME = {
    "Module Agent": "module",
    "Event Agent": "event",
    "Project Agent": "project",
}


def _profile_stub(state: RunState) -> dict:
    """Temporary placeholder — see module docstring. Do not edit profile.py to replace this."""
    profile = StudentProfile(
        name="Tan Wei Ling",  # matches data/fixtures/transcript.txt and resume.txt
        year=2,
        major="Computer Science",
        target_role=DEFAULT_ROLE,
        units_completed=72,
    )
    readiness = Readiness(
        dimensions=[
            DimensionScore(dimension=dimension, score=0.5, rationale="stub, not assessed")
            for dimension in Dimension
        ],
        gaps=[
            Gap(
                dimension=Dimension.SYSTEMS,
                label="Distributed systems",
                priority=1,
                current=0.3,
                target=0.8,
            )
        ],
    )
    return {
        "profile": profile,
        "readiness": readiness,
        "trace": [
            TraceEvent(
                kind=TraceKind.OBSERVED,
                agent="Profile Agent",
                message="Loaded stub profile and readiness",
                detail="Placeholder in graph.py. Real transcript/resume parsing and "
                "readiness assessment are W3.1-W3.3.",
            )
        ],
    }


def _fan_out(state: RunState) -> list[str]:
    dispatch = state.get("dispatch", [])
    nodes = [NODE_BY_AGENT_NAME[name] for name in dispatch if name in NODE_BY_AGENT_NAME]
    return nodes or ["score"]  # nothing dispatched: skip straight to scoring


def _score_stub(state: RunState) -> dict:
    """Temporary placeholder — see module docstring."""
    count = len(state.get("candidates", []))
    return {
        "trace": [
            TraceEvent(
                kind=TraceKind.DECIDED,
                agent="Career Agent",
                message=f"Scoring stub: {count} candidates passed through unscored",
                detail="Real scoring composition (gap coverage + role fit from the model, "
                "time cost + redundancy penalty + weighted sum in Python) is W1.4.",
            )
        ]
    }


def _refine_gate(state: RunState) -> dict:
    """Increments the refine-loop counter every time it is reached, cap or no cap."""
    iteration = state.get("iteration", 0) + 1
    return {
        "iteration": iteration,
        "trace": [
            TraceEvent(
                kind=TraceKind.DECIDED,
                agent="Career Agent",
                message=f"Refine check: iteration {iteration}/{MAX_REFINE_ITERATIONS}",
            )
        ],
    }


def _should_refine(state: RunState) -> str:
    """Loops back to the planner only when a logged outcome asked for a re-plan and the
    hard cap from config has not been reached. The cap is checked unconditionally — it
    ignores whatever a model might otherwise decide, per the hard rule in CLAUDE.md.
    """
    has_new_outcome = bool(state.get("outcomes"))
    under_cap = state.get("iteration", 0) < MAX_REFINE_ITERATIONS
    return "planner" if (has_new_outcome and under_cap) else END


def build_graph():
    builder = StateGraph(RunState)

    builder.add_node("profile", _profile_stub)
    builder.add_node("planner", planner_node)
    builder.add_node("module", module_node)
    builder.add_node("event", event_node)
    builder.add_node("project", project_node)
    builder.add_node("score", _score_stub)
    builder.add_node("refine_gate", _refine_gate)

    builder.add_edge(START, "profile")
    builder.add_edge("profile", "planner")

    builder.add_conditional_edges(
        "planner", _fan_out, ["module", "event", "project", "score"]
    )

    # Fan-in: whichever of module/event/project actually ran, all converge on score.
    builder.add_edge("module", "score")
    builder.add_edge("event", "score")
    builder.add_edge("project", "score")

    builder.add_edge("score", "refine_gate")
    builder.add_conditional_edges("refine_gate", _should_refine, ["planner", END])

    return builder.compile()


graph = build_graph()
