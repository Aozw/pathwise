"""W3.5 — guards on the eligibility evaluation set.

The eval set is only a testing-slide number if it stays consistent: every case
hand-verified, every grammar construct represented, and 100% agreement between the
labels and `is_eligible`. A drop below 100% means either the parser regressed or a
label is wrong — both are things CI should fail on, not average away.
"""

from __future__ import annotations

import json

from tests.eligibility_eval import EVAL_PATH, run_evaluation

_EXPECTED_GRAMMARS = {"none", "or", "and", "nOf", "wildcard", "graded_leaf", "cohort", "nested"}


def test_eval_set_is_big_enough():
    data = json.loads(EVAL_PATH.read_text())
    assert len(data["students"]) >= 8, "PLAN.md W3.5 asks for eight to ten profiles"
    assert len(data["cases"]) >= 20


def test_every_case_references_a_defined_student_and_module():
    data = json.loads(EVAL_PATH.read_text())
    students = {s["id"] for s in data["students"]}
    modules = {m["code"] for m in data["modules"]}
    for case in data["cases"]:
        assert case["student"] in students, case
        assert case["module"] in modules, case


def test_every_grammar_construct_is_exercised():
    report = run_evaluation()
    assert set(report.by_grammar) == _EXPECTED_GRAMMARS


def test_both_outcomes_are_represented():
    data = json.loads(EVAL_PATH.read_text())
    outcomes = {bool(c["expected_eligible"]) for c in data["cases"]}
    assert outcomes == {True, False}


def test_accuracy_is_perfect_on_the_hand_verified_set():
    report = run_evaluation()
    assert report.accuracy == 1.0, "\n" + "\n".join(
        f"{m.student} x {m.module}: expected {m.expected}, got {m.actual} ({m.reason})"
        for m in report.mismatches
    )


def test_every_grammar_construct_is_fully_correct():
    report = run_evaluation()
    for grammar, (correct, total) in report.by_grammar.items():
        assert correct == total, f"{grammar}: {correct}/{total}"
