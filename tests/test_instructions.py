from project_guard.instructions import format_instructions
from project_guard.models import PlanSnapshot


def _snapshot(**overrides) -> PlanSnapshot:
    base = dict(
        version=1,
        goal="Add a CLI option",
        recommended_scope=["src/app/cli.py"],
        possible_scope=["src/app/workflow.py"],
        avoid_modifying=["src/app/writer.py"],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    base.update(overrides)
    return PlanSnapshot(**base)


def test_format_instructions_deterministic():
    text = format_instructions(_snapshot())
    for fragment in (
        "## Goal",
        "src/app/cli.py",
        "src/app/workflow.py",
        "src/app/writer.py",
        "Smallest Safe Change",
        "Possible scope means",
        "Stop before modifying",
        "Do not commit automatically",
    ):
        assert fragment in text


def test_format_instructions_empty_scopes():
    text = format_instructions(
        _snapshot(possible_scope=[], avoid_modifying=[])
    )
    assert "None identified." in text
    assert "No explicit avoid list." in text


def test_format_instructions_conditional_constraints():
    text = format_instructions(_snapshot())
    assert "Do not add new dependencies" in text
    assert "Do not introduce a new abstraction." in text
    assert "Do not perform unrelated refactoring." in text

    softer = format_instructions(
        _snapshot(
            new_dependency="potentially justified",
            new_abstraction="reuse existing abstraction",
            refactor="no strong signal",
        )
    )
    assert "New dependencies are potentially justified by the plan" in softer
    assert "Reuse existing structure: reuse existing abstraction." in softer
    assert "not clearly justified" in softer
