"""W4.4 — src/entrypoint.py's onboard/run/approve routing.

The graph itself calls Bedrock; these tests never touch it. They monkeypatch
src.entrypoint.graph (get_state/invoke) and
src.entrypoint.{load_snapshot,save_snapshot,write_run_metrics} so the routing/
serialization logic in entrypoint.py is verified in isolation, per the CLAUDE.md
rule against calling Bedrock or any external API from a test - write_run_metrics
also needs patching even though it never touches the network, since its default
runs_dir is the repo's real data/runs/, and a test suite should not have side
effects on the filesystem outside tmp_path.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langgraph.types import Command, Interrupt

import src.entrypoint as ep
from src.state import (
    Candidate,
    CandidateKind,
    Dimension,
    DimensionScore,
    Gap,
    Readiness,
    ScoreComponents,
    SourceName,
    StudentProfile,
    TraceEvent,
    TraceKind,
    new_run_state,
)


def _profile() -> StudentProfile:
    return StudentProfile(name="Tan Wei Ling", year=2, major="Computer Science",
                           target_role="backend_infrastructure")


def _readiness() -> Readiness:
    return Readiness(
        dimensions=[DimensionScore(dimension=d, score=0.5, rationale="x") for d in Dimension],
        gaps=[Gap(dimension=Dimension.SYSTEMS, label="Systems depth", priority=1,
                  current=0.3, target=0.8)],
    )


def _candidate(scored: bool = True) -> Candidate:
    scores = (
        ScoreComponents(gap_coverage=0.8, role_fit=0.9, time_cost=0.5,
                         redundancy_penalty=0.1, total=0.75, rationale="fits well")
        if scored else None
    )
    return Candidate(id="nusmods:CS3230", kind=CandidateKind.MODULE, source=SourceName.NUSMODS,
                      title="CS3230", description="Algorithms", closes_gaps=["Systems depth"],
                      scores=scores)


class _FakeGraph:
    """Stands in for src.graph.graph: records what invoke() was called with and
    returns a canned result, and get_state() returns whatever values were configured."""

    def __init__(self, state_values: dict, invoke_result: dict):
        self._values = state_values
        self._invoke_result = invoke_result
        self.invoke_calls: list[tuple] = []

    def get_state(self, config):
        return SimpleNamespace(values=self._values)

    def invoke(self, graph_input, config):
        self.invoke_calls.append((graph_input, config))
        return self._invoke_result


def _patch_graph(monkeypatch, state_values, invoke_result):
    fake = _FakeGraph(state_values, invoke_result)
    monkeypatch.setattr(ep, "graph", fake)
    return fake


def _patch_snapshot(monkeypatch, load_return=(None, None), save_return=None):
    monkeypatch.setattr(ep, "load_snapshot", lambda run_id: load_return)
    monkeypatch.setattr(ep, "save_snapshot", lambda state: save_return)
    monkeypatch.setattr(ep, "write_run_metrics", lambda state: None)


# --- _build_run_input --------------------------------------------------------


def test_approve_resumes_with_command_and_never_touches_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(ep, "load_snapshot", lambda run_id: calls.append(run_id) or (None, None))
    graph_input, fallback = ep._build_run_input(
        "approve", "r1", {"approved": ["a1", "a2"]}, {"configurable": {"thread_id": "r1"}}
    )
    assert isinstance(graph_input, Command)
    assert graph_input.resume == {"approved": ["a1", "a2"]}
    assert fallback == []
    assert calls == []  # load_snapshot never called for approve


def test_onboard_on_a_fresh_thread_starts_a_new_run_state(monkeypatch):
    _patch_graph(monkeypatch, state_values={}, invoke_result={})
    _patch_snapshot(monkeypatch, load_return=(None, None))
    graph_input, fallback = ep._build_run_input(
        "onboard", "r1", {}, {"configurable": {"thread_id": "r1"}}
    )
    assert graph_input["run_id"] == "r1"
    assert graph_input["candidates"] == []
    assert graph_input["trace"] == []
    assert fallback == []


def test_onboard_on_a_warm_thread_sends_no_input(monkeypatch):
    """Nothing new to add - the checkpoint already has everything. An empty dict
    input on a continuing thread just re-runs from START without re-seeding any
    reducer field (see the reducer-duplication note in _recover_after_restart)."""
    _patch_graph(monkeypatch, state_values={"candidates": [1, 2, 3]}, invoke_result={})
    graph_input, fallback = ep._build_run_input(
        "onboard", "r1", {}, {"configurable": {"thread_id": "r1"}}
    )
    assert graph_input == {}
    assert fallback == []


def test_run_on_a_warm_thread_only_carries_the_new_outcome(monkeypatch):
    """The critical reducer-safety property: candidates/trace must NOT be echoed
    back as input on a continuing thread, or graph.invoke's operator.add reducer
    would double-count everything the checkpoint already holds."""
    _patch_graph(
        monkeypatch,
        state_values={"candidates": [1, 2, 3], "trace": [1, 2], "outcomes": ["prior"]},
        invoke_result={},
    )
    graph_input, fallback = ep._build_run_input(
        "run", "r1",
        {"outcome": {"candidate_id": "nusmods:CS3230", "result": "not_shortlisted"}},
        {"configurable": {"thread_id": "r1"}},
    )
    assert "candidates" not in graph_input
    assert "trace" not in graph_input
    assert graph_input["outcomes"][0] == "prior"
    new_outcome = graph_input["outcomes"][1]
    assert (new_outcome.candidate_id, new_outcome.result) == ("nusmods:CS3230", "not_shortlisted")
    assert fallback == []


def test_run_on_a_cold_thread_recovers_profile_from_snapshot_but_not_candidates(monkeypatch):
    _patch_graph(monkeypatch, state_values={}, invoke_result={})
    snapshot_state = new_run_state("r1")
    snapshot_state["profile"] = _profile()
    snapshot_state["candidates"] = [_candidate()]  # must NOT survive into graph_input
    snapshot_state["outcomes"] = ["prior"]
    fallback_event = TraceEvent(kind=TraceKind.OBSERVED, agent="Career Agent", message="recovered")
    _patch_snapshot(monkeypatch, load_return=(snapshot_state, fallback_event))

    graph_input, fallback = ep._build_run_input(
        "run", "r1", {"outcome": {"candidate_id": "x", "result": "accepted"}},
        {"configurable": {"thread_id": "r1"}},
    )
    assert graph_input["profile"] == _profile()
    assert graph_input["candidates"] == []  # reset, not replayed from the snapshot
    assert graph_input["trace"] == []
    assert graph_input["outcomes"][0] == "prior"
    new_outcome = graph_input["outcomes"][1]
    assert (new_outcome.candidate_id, new_outcome.result) == ("x", "accepted")
    assert fallback == [fallback_event]


# --- _serialize ---------------------------------------------------------------


def test_serialize_completed_run_has_no_pending_and_reports_ranked_candidates():
    result = {
        "profile": _profile(), "readiness": _readiness(), "ranked": [_candidate()],
        "approved": ["action:nusmods:CS3230"],
        "trace": [TraceEvent(kind=TraceKind.DECIDED, agent="Career Agent", message="done")],
    }
    out = ep._serialize(result, "r1")
    assert out["status"] == "ok"
    assert out["run_id"] == "r1"
    assert out["awaiting_approval"] is False
    assert out["profile"]["name"] == "Tan Wei Ling"
    assert out["readiness"]["dimensions"][0]["weight"] == pytest.approx(0.25)
    assert out["ranked"][0]["id"] == "nusmods:CS3230"
    assert out["ranked"][0]["score"] == pytest.approx(0.75)
    assert out["pending"] == []
    assert out["approved"] == ["action:nusmods:CS3230"]
    assert len(out["trace"]) == 1


def test_serialize_interrupted_run_surfaces_pending_actions_from_the_interrupt():
    actions = [{"id": "action:nusmods:CS3230", "action_type": "add_to_roadmap",
                "label": "Add 'CS3230' to the roadmap", "candidate_id": "nusmods:CS3230",
                "auto_approvable": True}]
    result = {
        "profile": _profile(), "readiness": _readiness(), "ranked": [_candidate()],
        "trace": [], "__interrupt__": (Interrupt(value={"kind": "approve_actions", "actions": actions}),),
    }
    out = ep._serialize(result, "r1")
    assert out["awaiting_approval"] is True
    assert out["pending"] == actions


def test_serialize_handles_missing_profile_and_readiness():
    out = ep._serialize({}, "r1")
    assert out["profile"] is None
    assert out["readiness"] is None
    assert out["ranked"] == []
    assert out["pending"] == []
    assert out["trace"] == []


# --- invoke: end-to-end routing -----------------------------------------------


def test_invoke_rejects_unknown_action():
    out = ep.invoke({"action": "bogus"})
    assert out["status"] == "error"
    assert "bogus" in out["message"]


def test_invoke_reports_graph_failure_without_crashing(monkeypatch):
    class _Boom:
        def get_state(self, config):
            return SimpleNamespace(values={})

        def invoke(self, graph_input, config):
            raise RuntimeError("bedrock exploded")

    monkeypatch.setattr(ep, "graph", _Boom())
    _patch_snapshot(monkeypatch)
    out = ep.invoke({"action": "onboard"})
    assert out["status"] == "error"
    assert "bedrock exploded" in out["message"]


def test_invoke_onboard_generates_a_run_id_and_serializes_the_result(monkeypatch):
    invoke_result = {"profile": _profile(), "readiness": _readiness(), "ranked": [],
                      "trace": [TraceEvent(kind=TraceKind.OBSERVED, agent="Profile Agent",
                                            message="parsed")]}
    fake = _patch_graph(monkeypatch, state_values={}, invoke_result=invoke_result)
    _patch_snapshot(monkeypatch)

    out = ep.invoke({"action": "onboard"})

    assert out["status"] == "ok"
    assert out["run_id"]  # a uuid was generated
    assert len(fake.invoke_calls) == 1
    graph_input, config = fake.invoke_calls[0]
    assert config == {"configurable": {"thread_id": out["run_id"]}}
    assert graph_input["run_id"] == out["run_id"]


def test_invoke_echoes_back_a_supplied_run_id(monkeypatch):
    fake = _patch_graph(monkeypatch, state_values={"outcomes": []}, invoke_result={"trace": []})
    _patch_snapshot(monkeypatch)

    out = ep.invoke({"action": "run", "run_id": "existing-run",
                      "outcome": {"candidate_id": "x", "result": "withdrew"}})

    assert out["run_id"] == "existing-run"
    _graph_input, config = fake.invoke_calls[0]
    assert config == {"configurable": {"thread_id": "existing-run"}}


def test_invoke_strips_interrupt_key_before_snapshotting(monkeypatch):
    """A dunder key holding langgraph Interrupt objects must never reach
    save_snapshot - it isn't one of state.py's registered types."""
    saved = {}

    def fake_save(state):
        saved.update(state)
        return None

    invoke_result = {
        "profile": _profile(), "trace": [],
        "__interrupt__": (Interrupt(value={"kind": "approve_actions", "actions": []}),),
    }
    _patch_graph(monkeypatch, state_values={}, invoke_result=invoke_result)
    monkeypatch.setattr(ep, "load_snapshot", lambda run_id: (None, None))
    monkeypatch.setattr(ep, "save_snapshot", fake_save)
    monkeypatch.setattr(ep, "write_run_metrics", lambda state: None)

    ep.invoke({"action": "onboard"})

    assert "__interrupt__" not in saved
    assert saved["profile"] == _profile()


def test_invoke_appends_a_save_snapshot_failure_to_the_trace(monkeypatch):
    invoke_result = {"profile": _profile(), "trace": []}
    _patch_graph(monkeypatch, state_values={}, invoke_result=invoke_result)
    fallback_event = TraceEvent(kind=TraceKind.OBSERVED, agent="Career Agent",
                                 message="S3 snapshot write failed")
    monkeypatch.setattr(ep, "load_snapshot", lambda run_id: (None, None))
    monkeypatch.setattr(ep, "save_snapshot", lambda state: fallback_event)
    monkeypatch.setattr(ep, "write_run_metrics", lambda state: None)

    out = ep.invoke({"action": "onboard"})

    assert any(t["message"] == "S3 snapshot write failed" for t in out["trace"])


def test_invoke_writes_run_metrics_alongside_the_snapshot(monkeypatch):
    """W3.4's write_run_metrics must actually run on the real invoke() path, not
    just exist as unit-tested-in-isolation dead code."""
    written = {}

    def fake_write(state):
        written.update(state)
        return None

    invoke_result = {"profile": _profile(), "trace": [], "run_id": "r1"}
    _patch_graph(monkeypatch, state_values={}, invoke_result=invoke_result)
    monkeypatch.setattr(ep, "load_snapshot", lambda run_id: (None, None))
    monkeypatch.setattr(ep, "save_snapshot", lambda state: None)
    monkeypatch.setattr(ep, "write_run_metrics", fake_write)

    ep.invoke({"action": "onboard", "run_id": "r1"})

    assert written["run_id"] == "r1"
