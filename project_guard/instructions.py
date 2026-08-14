"""Deterministic agent instructions generated from an EngineeringContract."""

from __future__ import annotations

from pathlib import Path

from .models import EngineeringContract

EMPTY_SCOPE_TEXT = "None identified."
SKILL_TEMPLATE = Path(__file__).parent / "templates" / "coding_skill.md"


def skill_template_text() -> str:
    """Return the fixed, generic Coding Skill template."""
    return SKILL_TEMPLATE.read_text(encoding="utf-8")


def _bullet_list(items: list[str]) -> str:
    if not items:
        return EMPTY_SCOPE_TEXT
    return "\n".join(f"- {item}" for item in items)


def _dependency_rule(value: str) -> str:
    if value == "not justified":
        return (
            "Do not add new dependencies unless the goal cannot be completed "
            "safely without one. Stop and explain first."
        )
    return (
        f"New dependencies are {value} by the contract; do not add any "
        "without explaining why they are required."
    )


def _abstraction_rule(value: str) -> str:
    if value == "not justified":
        return "Do not introduce a new abstraction."
    if value.startswith("reuse existing"):
        return f"Reuse existing structure: {value}."
    return (
        f"New abstraction is {value} by the contract; do not create one "
        "without explaining why."
    )


def _refactor_rule(value: str) -> str:
    if value == "not justified":
        return "Do not perform unrelated refactoring."
    if value == "no strong signal":
        return (
            "Refactoring is not clearly justified; do not refactor unrelated "
            "code."
        )
    return (
        f"Refactoring is {value} by the contract; only perform it when "
        "required and explain why."
    )


def format_instructions(
    contract: EngineeringContract,
    skill_path: str | Path = ".project-guard-skill.md",
) -> str:
    """Render a Guard Contract as task-specific agent instructions."""
    budget = contract.complexity_budget
    lines = [
        "# Original User Request",
        "",
        contract.original_request,
        "",
        "# Project Guard Contract",
        "",
        "## Repository Facts",
        "",
        _bullet_list(contract.repository_facts),
        "",
        "## Engineering Guardrails",
        "",
        _bullet_list(contract.inferred_requirements),
        "",
        "## Strongly Related Scope",
        "",
        "Files Project Guard considers strongly related based on "
        "repository evidence. Governance boundary, not a substitute for "
        "engineering judgement.",
        "",
        _bullet_list(contract.recommended_scope),
        "",
        "## Possible Scope",
        "",
        "Files that may be relevant if implementation requires them.",
        "",
        _bullet_list(contract.possible_scope),
        "",
        "## Do Not Modify",
        "",
        "Do not modify these files unless a scope amendment is approved.",
        "",
        _bullet_list(contract.avoid_modifying),
        "",
        "## Existing Capabilities",
        "",
        _bullet_list(contract.existing_capability_files),
        "",
        "## Architecture Constraints",
        "",
        f"- {_dependency_rule(contract.new_dependency)}",
        f"- {_abstraction_rule(contract.new_abstraction)}",
        f"- {_refactor_rule(contract.refactor)}",
        "- Reuse existing project structure before creating new mechanisms.",
        "",
        "## Implementation Signals",
        "",
        f"- preferred new production files: "
        f"{budget.preferred_new_production_files}",
        f"- preferred new abstractions: "
        f"{budget.preferred_new_abstractions}",
        f"- preferred new dependencies: "
        f"{budget.preferred_new_dependencies}",
        f"- preferred max touched production files: "
        f"{budget.preferred_max_touched_production_files}",
        "",
        "## Testing Guidance",
        "",
        contract.testing_policy,
        "",
        "# Mandatory Coding Skill",
        "",
        f"Read and follow: `{skill_path}`",
        "",
        "Before coding, use the original request, this Guard Contract, and "
        "the Coding Skill to form your own Task Contract.",
        "",
        "Project Guard does not determine the final semantic interpretation "
        "of the user's request.",
        "",
        "If materially different interpretations would change user-visible "
        "behavior, ask the user before coding.",
    ]
    return "\n".join(lines) + "\n"
