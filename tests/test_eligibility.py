"""Unit tests for W2.2 — src/tools/eligibility.py.

Pure function, no I/O, no fixtures needed beyond what's constructed inline. Several
trees below are copied verbatim from live `modules/{code}.json` responses (fetched
manually while building this parser) rather than invented, so the and/or/nOf grammar
is tested against real NUSMods data shapes, not a simplified guess at them.
"""

from __future__ import annotations

from src.state import CompletedModule
from src.tools.eligibility import is_eligible
from src.tools.nusmods import NUSModsModule


def _module(prereq_tree) -> NUSModsModule:
    return NUSModsModule(code="TEST1234", title="Test Module", prereq_tree=prereq_tree)


def _completed(*codes_and_grades: tuple[str, str | None]) -> list[CompletedModule]:
    return [
        CompletedModule(code=code, title=code, units=4.0, grade=grade)
        for code, grade in codes_and_grades
    ]


def test_no_prereq_tree_is_eligible():
    assert is_eligible(_module(None), []) is True


def test_bare_leaf_needs_completion_only():
    module = _module("CS2106")
    assert is_eligible(module, _completed(("CS2106", None))) is True
    assert is_eligible(module, []) is False


def test_graded_leaf_checks_grade_floor():
    module = _module("CS2100:D")
    assert is_eligible(module, _completed(("CS2100", "B"))) is True
    assert is_eligible(module, _completed(("CS2100", "D"))) is True
    assert is_eligible(module, _completed(("CS2100", "F"))) is False


def test_graded_leaf_missing_grade_is_treated_as_meeting_floor():
    # In the completed list but with no recorded grade (e.g. an exemption).
    module = _module("CS2100:D")
    assert is_eligible(module, _completed(("CS2100", None))) is True


def test_pass_fail_grades():
    module = _module("CS2100:D")
    assert is_eligible(module, _completed(("CS2100", "S"))) is True
    assert is_eligible(module, _completed(("CS2100", "U"))) is False


def test_and_requires_every_child():
    module = _module({"and": ["CS2106", "CS2100"]})
    assert is_eligible(module, _completed(("CS2106", "B"), ("CS2100", "B"))) is True
    assert is_eligible(module, _completed(("CS2106", "B"))) is False


def test_or_requires_one_child():
    module = _module({"or": ["CS2100", "CS2106"]})
    assert is_eligible(module, _completed(("CS2106", "B"))) is True
    assert is_eligible(module, []) is False


def test_n_of_requires_n_children():
    module = _module({"nOf": [2, ["MA1511:D", "MA1512:D", "MA1521:D"]]})
    assert is_eligible(module, _completed(("MA1511", "B"), ("MA1512", "B"))) is True
    assert is_eligible(module, _completed(("MA1511", "B"))) is False
    assert is_eligible(module, _completed(("MA1521", "B"), ("MA1511", "B"))) is True


def test_nested_and_or_combination():
    # CS4225's real tree.
    module = _module({"or": ["CS2102:D", "IT2002:D"]})
    assert is_eligible(module, _completed(("IT2002", "C"))) is True
    assert is_eligible(module, []) is False


def test_wildcard_leaf_satisfied_by_any_matching_family_member():
    # Live-observed real tree: ACC2727 requires ACC1701% (any of ACC1701A/B/C/D/
    # XA/XB/XC/XD) or EC2204, at grade D.
    module = _module({"or": ["ACC1701%:D", "EC2204:D"]})
    assert is_eligible(module, _completed(("ACC1701C", "B"))) is True
    assert is_eligible(module, _completed(("EC2204", "B"))) is True
    assert is_eligible(module, _completed(("ACC1702", "B"))) is False  # not a match
    assert is_eligible(module, []) is False


def test_wildcard_leaf_checks_grade_floor_across_matches():
    module = _module("ACC1701%:D")
    assert is_eligible(module, _completed(("ACC1701A", "F"), ("ACC1701B", "B"))) is True
    assert is_eligible(module, _completed(("ACC1701A", "F"))) is False


def test_unrecognised_node_shape_defaults_to_satisfied_not_an_error():
    # Live-observed: a cohort/admission-year restriction, not a completed-module
    # requirement - StudentProfile has no field to evaluate it against.
    module = _module({"cohort": {"rule": "MUST_BE_IN", "years": ["S:2017"]}})
    assert is_eligible(module, []) is True


def test_unrecognised_node_nested_inside_and_defaults_to_satisfied():
    module = _module({"and": ["CS2106", {"cohort": {"rule": "MUST_BE_IN", "years": ["S:2017"]}}]})
    assert is_eligible(module, _completed(("CS2106", "B"))) is True


def test_deeply_nested_real_tree_cs4243():
    # Copied verbatim from a live GET of modules/CS4243.json.
    tree = {
        "and": [
            {"or": ["YSC2232:D", "MA2001:D", "MA1101R:D", "MA1311:D", "MA1508E:D", "MA1513:D", "MA1522:D"]},
            {
                "or": [
                    "ST1131:D",
                    "ST1131A:D",
                    "ST1232:D",
                    "ST2131:D",
                    "MA2116:D",
                    "MA2116T:D",
                    "MA2216:D",
                    "EE2012A:D",
                    "EE2012:D",
                    "ST2334:D",
                    "YSC2243:D",
                ]
            },
            {"or": ["CS2030:D", "CS2030S:D", "CS2030DE:D", "CS2113:D", "CS2113T:D"]},
            {"or": ["YSC2229:D", "CS2040:D", "CS2040S:D", "CS2040DE:D", "CS2040C:D", "CS2040HS:D"]},
            {
                "or": [
                    "MA1102R:D",
                    "MA2002:D",
                    "YSC1216:D",
                    "MA1505:D",
                    "MA1521:D",
                    "MA1507:D",
                    {"nOf": [2, ["MA1512:D", "MA1511:D"]]},
                ]
            },
        ]
    }
    module = _module(tree)

    # A student who cleared every "or" branch via its first listed option, plus
    # both halves of the trailing nOf branch, should be eligible.
    completed = _completed(
        ("MA2001", "B"),
        ("ST1131", "B"),
        ("CS2030", "B"),
        ("CS2040", "B"),
        ("MA1511", "B"),
        ("MA1512", "B"),
    )
    assert is_eligible(module, completed) is True

    # Missing just the CS2040-equivalent branch should fail the whole "and".
    incomplete = _completed(
        ("MA2001", "B"),
        ("ST1131", "B"),
        ("CS2030", "B"),
        ("MA1511", "B"),
        ("MA1512", "B"),
    )
    assert is_eligible(module, incomplete) is False


def test_bt4222_real_tree_or_of_and_and_nof():
    # Copied verbatim from a live GET of modules/BT4222.json.
    tree = {
        "or": [
            {
                "and": [
                    {
                        "or": [
                            "CS1010:D",
                            "CS1010E:D",
                            "CS1101S:D",
                            "CS1010J:D",
                            "CS1010S:D",
                            "CS1010X:D",
                            "CS1010A:D",
                            "CS1010HS:D",
                            "UTC2851:D",
                        ]
                    },
                    {"nOf": [2, ["BT2101:D", "BT2102:D"]]},
                ]
            },
            {"nOf": [3, ["DAO2702:D", "DBA3803:D", "IT3010:D"]]},
        ]
    }
    module = _module(tree)

    via_first_branch = _completed(
        ("CS1101S", "B"), ("BT2101", "B"), ("BT2102", "B")
    )
    assert is_eligible(module, via_first_branch) is True

    via_second_branch = _completed(
        ("DAO2702", "B"), ("DBA3803", "B"), ("IT3010", "B")
    )
    assert is_eligible(module, via_second_branch) is True

    neither_branch = _completed(("CS1101S", "B"), ("BT2101", "B"))
    assert is_eligible(module, neither_branch) is False
