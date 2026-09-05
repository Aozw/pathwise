"""Prerequisite eligibility — W2.2.

NUSMods prereqTree grammar (confirmed by fetching a spread of real modules against the
live per-module detail endpoint - CS4243, CS3244, CS2109S, BT4222 and others, see the
PR for the raw trees): a node is one of

  - a leaf string, a module code optionally suffixed "CODE:GRADE"
    (e.g. "CS2100:D" - completed CS2100 at grade D or better; a bare "CS2106" means
    just completed, no grade floor), and optionally ending in "%" - a wildcard over a
    module family (e.g. "ACC1701%:D", satisfied by completing any of
    ACC1701A/B/C/D/XA/XB/XC/XD at grade D or better - live-observed fetching real
    modules at W2.5 integration time, not in the original spread of examples)
  - {"and": [node, ...]}         every child must be satisfied
  - {"or": [node, ...]}          at least one child must be satisfied
  - {"nOf": [n, [node, ...]]}    at least n of the children must be satisfied
  - anything else (e.g. {"cohort": {...}}, an admission-year restriction rather than a
    completed-module requirement - also live-observed at W2.5 integration time) is
    treated as satisfied: there's no reason to assume this grammar list is complete,
    and no StudentProfile field to evaluate a rule outside it against anyway

This is a pure function, no I/O, per the CLAUDE.md hard rule and PLAN.md's own framing
of this task ("one of only two places that can produce a real accuracy number for the
slides"). It does not fetch a module's prereqTree - see src/tools/nusmods.py's module
docstring for why that isn't available in bulk and has to be a separate, later,
per-candidate fetch (W2.5's problem, not this file's).
"""

from __future__ import annotations

from typing import Any

from src.state import CompletedModule

# Grades ordered coarsely enough to compare threshold requirements ("at least D").
# Absolute values don't matter, only relative order.
_GRADE_RANK = {
    "F": 0.0,
    "D": 1.0,
    "D+": 1.5,
    "C": 2.0,
    "C+": 2.5,
    "B-": 3.0,
    "B": 3.5,
    "B+": 4.0,
    "A-": 4.5,
    "A": 5.0,
    "A+": 5.0,
}
# NUS pass/fail modules report S/U (or the older CS/CU) instead of a letter grade.
# A satisfactory result meets any letter-grade floor a prerequisite might ask for;
# unsatisfactory meets none.
_PASS_GRADES = {"S", "CS"}
_FAIL_GRADES = {"U", "CU", "F", "IC", "W"}


def _meets_min_grade(actual_grade: str | None, min_grade: str) -> bool:
    """actual_grade is None when a completed module carries no recorded grade (e.g. an
    exemption or a transcript that only lists pass/completion). Since the module is
    still in the student's completed list, that is treated as meeting the floor rather
    than failing it - there is no evidence it doesn't, and the alternative silently
    drops modules with incomplete grade data out of every prerequisite chain.
    """
    if actual_grade is None:
        return True
    grade = actual_grade.strip().upper()
    if grade in _FAIL_GRADES:
        return False
    if grade in _PASS_GRADES:
        return True
    return _GRADE_RANK.get(grade, 0.0) >= _GRADE_RANK.get(min_grade.strip().upper(), 0.0)


def _leaf_satisfied(leaf: str, completed_by_code: dict[str, str | None]) -> bool:
    """A leaf code ending "%" is a wildcard over a module family (live-observed:
    "ACC1701%:D" is satisfied by completing any of ACC1701A/B/C/D/XA/XB/XC/XD) -
    satisfied if any completed code sharing that prefix meets the grade floor.
    """
    code, _, min_grade = leaf.partition(":")
    if code.endswith("%"):
        prefix = code[:-1]
        matching_codes = [c for c in completed_by_code if c.startswith(prefix)]
        if not matching_codes:
            return False
        if not min_grade:
            return True
        return any(_meets_min_grade(completed_by_code[c], min_grade) for c in matching_codes)
    if code not in completed_by_code:
        return False
    if not min_grade:
        return True
    return _meets_min_grade(completed_by_code[code], min_grade)


def _node_satisfied(node: Any, completed_by_code: dict[str, str | None]) -> bool:
    """Live-fetching real module detail turned up prereqTree node shapes beyond
    and/or/nOf - e.g. {"cohort": {"rule": "MUST_BE_IN", "years": ["S:2017"]}}, an
    admission-year restriction, not a completed-module requirement. There is no
    reason to assume and/or/nOf is the complete grammar, and StudentProfile has no
    field to evaluate a rule like that anyway. Treated the same as a missing tree:
    satisfied, not an error - one module's unusual rule crashing the whole run (this
    used to raise ValueError here) is a worse failure mode than one false-positive
    eligibility answer.
    """
    if node is None:
        return True
    if isinstance(node, str):
        return _leaf_satisfied(node, completed_by_code)
    if isinstance(node, dict):
        if "and" in node:
            return all(_node_satisfied(child, completed_by_code) for child in node["and"])
        if "or" in node:
            return any(_node_satisfied(child, completed_by_code) for child in node["or"])
        if "nOf" in node:
            n, children = node["nOf"]
            met = sum(1 for child in children if _node_satisfied(child, completed_by_code))
            return met >= n
    return True


def is_eligible(module: Any, completed_modules: list[CompletedModule]) -> bool:
    """True if `module` (anything with a `.prereq_tree` attribute - see
    src.tools.nusmods.NUSModsModule) has no prerequisite tree, or its tree is
    satisfied by `completed_modules`.

    A missing tree (module.prereq_tree is None) is treated as eligible, not
    ineligible: that's the normal case for every module read from the live bulk
    catalogue today (see nusmods.py), and refusing to recommend an entire catalogue
    because prerequisite data hasn't been fetched yet would defeat the point of the
    Module Agent. A genuinely prerequisite-gated module without fetched tree data
    is a false positive this design accepts - correcting it means calling the
    per-module detail endpoint (W2.5), which is out of scope for this pure function.
    """
    if module.prereq_tree is None:
        return True
    completed_by_code = {m.code: m.grade for m in completed_modules}
    return _node_satisfied(module.prereq_tree, completed_by_code)
