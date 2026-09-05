"""W3.5 — prerequisite eligibility evaluation.

Runs `src.tools.eligibility.is_eligible` over the hand-verified cases in
`data/fixtures/eligibility_eval.json` and reports accuracy, broken down by the
prereqTree grammar construct each case exercises. This is the "prerequisite
accuracy" number the testing slide needs.

The other two numbers PLAN.md's W3.5 asks for — schema validation pass rate and
tool-call success rate — come from `RunMetrics` accumulated over real runs (W3.4),
not from a static fixture, so they are not produced here. When W3.4 lands, its
metrics reader can print alongside this report.

Importable (`from tests.eligibility_eval import run_evaluation`) and runnable
(`python -m tests.eligibility_eval`) so W5 can pull the figure for the deck without
re-deriving it.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from src.state import CompletedModule
from src.tools.eligibility import is_eligible
from src.tools.nusmods import NUSModsModule

EVAL_PATH = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "eligibility_eval.json"


@dataclass
class CaseResult:
    student: str
    module: str
    grammar: str
    expected: bool
    actual: bool
    reason: str

    @property
    def correct(self) -> bool:
        return self.expected == self.actual


@dataclass
class EvalReport:
    results: list[CaseResult]
    by_grammar: dict[str, tuple[int, int]] = field(default_factory=dict)  # grammar -> (correct, total)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def correct(self) -> int:
        return sum(1 for r in self.results if r.correct)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.results else 0.0

    @property
    def mismatches(self) -> list[CaseResult]:
        return [r for r in self.results if not r.correct]


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _modules(data: dict) -> dict[str, NUSModsModule]:
    return {
        m["code"]: NUSModsModule(
            code=m["code"], title=m["title"], prereq_tree=m.get("prereq_tree")
        )
        for m in data["modules"]
    }


def _students(data: dict) -> dict[str, list[CompletedModule]]:
    return {
        s["id"]: [
            CompletedModule(code=code, title=code, units=4.0, grade=grade)
            for code, grade in s["completed"]
        ]
        for s in data["students"]
    }


def run_evaluation(path: Path = EVAL_PATH) -> EvalReport:
    data = _load(path)
    modules = _modules(data)
    students = _students(data)

    results: list[CaseResult] = []
    for case in data["cases"]:
        module = modules[case["module"]]
        completed = students[case["student"]]
        actual = is_eligible(module, completed)
        results.append(
            CaseResult(
                student=case["student"],
                module=case["module"],
                grammar=case["grammar"],
                expected=bool(case["expected_eligible"]),
                actual=actual,
                reason=case["reason"],
            )
        )

    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in results:
        tally[r.grammar][1] += 1
        if r.correct:
            tally[r.grammar][0] += 1

    report = EvalReport(results=results)
    report.by_grammar = {g: (c, t) for g, (c, t) in sorted(tally.items())}
    return report


def format_report(report: EvalReport) -> str:
    lines = [
        "Prerequisite eligibility evaluation (W3.5)",
        f"  cases:    {report.total}",
        f"  correct:  {report.correct}",
        f"  accuracy: {report.accuracy:.1%}",
        "",
        "  by grammar construct:",
    ]
    for grammar, (correct, total) in report.by_grammar.items():
        lines.append(f"    {grammar:<12} {correct}/{total}")
    if report.mismatches:
        lines.append("")
        lines.append("  MISMATCHES:")
        for r in report.mismatches:
            lines.append(
                f"    {r.student} x {r.module}: expected {r.expected}, got {r.actual} "
                f"— {r.reason}"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_report(run_evaluation()))
