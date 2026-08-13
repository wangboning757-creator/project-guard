"""Deterministic agent instructions generated from a PlanSnapshot."""

from __future__ import annotations

from .models import PlanSnapshot

EMPTY_SCOPE_TEXT = "None identified."
NO_AVOID_TEXT = "No explicit avoid list."


def _bullet_list(items: list[str], empty_text: str) -> str:
    if not items:
        return empty_text
    return "\n".join(f"- {item}" for item in items)


def _dependency_constraint(value: str) -> str:
    if value == "not justified":
        return (
            "Do not add new dependencies unless the goal cannot be completed "
            "safely without one. Stop and explain first."
        )
    return (
        f"New dependencies are {value} by the plan; do not add any without "
        "explaining why they are required."
    )


def _abstraction_constraint(value: str) -> str:
    if value == "not justified":
        return "Do not introduce a new abstraction."
    if value.startswith("reuse existing"):
        return f"Reuse existing structure: {value}."
    return (
        f"New abstraction is {value} by the plan; do not create one without "
        "explaining why."
    )


def _refactor_constraint(value: str) -> str:
    if value == "not justified":
        return "Do not perform unrelated refactoring."
    if value == "no strong signal":
        return (
            "Refactoring is not clearly justified; do not refactor unrelated "
            "code."
        )
    return (
        f"Refactoring is {value} by the plan; only perform it when required "
        "and explain why."
    )


def format_instructions(snapshot: PlanSnapshot) -> str:
    """Render a PlanSnapshot as a deterministic agent instructions contract."""
    goal = snapshot.goal.strip()
    if goal and not goal.endswith("."):
        goal += "."
    lines = [
        "# Project Guard Agent Instructions",
        "",
        "## Goal",
        "",
        goal,
        "",
        "## Change Boundary",
        "",
        "### Recommended scope",
        "",
        _bullet_list(snapshot.recommended_scope, EMPTY_SCOPE_TEXT),
        "",
        "### Possible scope",
        "",
        _bullet_list(snapshot.possible_scope, EMPTY_SCOPE_TEXT),
        "",
        "### Do not modify",
        "",
        _bullet_list(snapshot.avoid_modifying, NO_AVOID_TEXT),
        "",
        "## Engineering Constraints",
        "",
        f"- {_dependency_constraint(snapshot.new_dependency)}",
        f"- {_abstraction_constraint(snapshot.new_abstraction)}",
        f"- {_refactor_constraint(snapshot.refactor)}",
        "- Reuse existing project structure before creating new mechanisms.",
        "",
        "## Scope Rules",
        "",
        "- Start from the recommended scope.",
        "- Possible scope means \"modify only if necessary\", not \"modify "
        "all of these files\".",
        "- Do not modify files in \"Do not modify\" unless the current goal "
        "cannot be completed safely without them.",
        "- Do not modify unrelated production files.",
        "",
        "If a production file outside the allowed scope is genuinely "
        "required:",
        "",
        "1. Stop before modifying it.",
        "2. Explain which file is required.",
        "3. Explain why it is required.",
        "4. Explain why the current Project Guard plan underestimated the "
        "scope.",
        "5. Explain whether a correct and maintainable implementation exists "
        "within the current scope.",
        "",
        "## Implementation Rule",
        "",
        "Use the Smallest Safe Change that fully satisfies the goal.",
        "",
        "Do not sacrifice correctness only to reduce the number of changed "
        "files.",
        "",
        "Prefer reusing existing behavior over duplicating functionality.",
        "",
        "## Testing Rule",
        "",
        "Run targeted tests for the behavior directly affected by the change.",
        "",
        "Expand test scope only when the actual implementation affects shared "
        "interfaces, shared execution paths, or multiple core modules.",
        "",
        "## Completion Rule",
        "",
        "Do not commit automatically.",
        "",
        "When finished, report:",
        "",
        "1. What was implemented",
        "2. Production files changed",
        "3. Recommended-scope files changed",
        "4. Possible-scope files changed",
        "5. Whether any avoided files were modified",
        "6. Whether Project Guard underestimated the required scope",
        "7. New dependencies",
        "8. New abstractions",
        "9. Tests run",
        "10. Whether the full test suite was run and why",
        "11. Known limitations",
    ]
    return "\n".join(lines) + "\n"
