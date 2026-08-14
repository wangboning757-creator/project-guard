from project_guard.instructions import (
    format_instructions,
    skill_template_text,
)
from project_guard.models import ComplexityBudget, EngineeringContract


def _contract(**overrides) -> EngineeringContract:
    base = dict(
        original_request="Add a CLI option",
        explicit_requirements=["Add a CLI option"],
        inferred_requirements=[
            "Reuse existing capability where available.",
        ],
        assumptions=["Implementation is likely CLI-scoped."],
        unresolved_questions=[],
        repository_facts=["CLI entry point: src/app/cli.py"],
        recommended_scope=["src/app/cli.py"],
        possible_scope=["src/app/workflow.py"],
        avoid_modifying=["src/app/writer.py"],
        existing_capability_files=["src/app/search/tavily.py"],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
        complexity_budget=ComplexityBudget(),
        testing_policy="Run targeted tests for affected behavior first.",
    )
    base.update(overrides)
    return EngineeringContract(**base)


def test_format_instructions_deterministic():
    text = format_instructions(_contract(), ".project-guard-skill.md")
    for fragment in (
        "# Original User Request",
        "Add a CLI option",
        "## Engineering Inferences",
        "## Repository Facts",
        "src/app/cli.py",
        "src/app/workflow.py",
        "src/app/writer.py",
        "## Complexity Budget",
        "## Testing Policy",
        "# Mandatory Coding Skill",
        ".project-guard-skill.md",
    ):
        assert fragment in text


def test_format_instructions_empty_sections():
    text = format_instructions(
        _contract(
            assumptions=[],
            unresolved_questions=[],
            repository_facts=[],
            avoid_modifying=[],
            existing_capability_files=[],
        ),
        ".project-guard-skill.md",
    )
    assert "None identified." in text


def test_format_instructions_unresolved_questions():
    text = format_instructions(
        _contract(
            unresolved_questions=[
                "Should this behavior also apply to the web interface?"
            ]
        ),
        ".project-guard-skill.md",
    )
    assert "web interface" in text


def test_format_instructions_conditional_rules():
    text = format_instructions(_contract(), ".project-guard-skill.md")
    assert "Do not add new dependencies" in text
    assert "Do not introduce a new abstraction." in text
    assert "Do not perform unrelated refactoring." in text

    softer = format_instructions(
        _contract(
            new_dependency="potentially justified",
            new_abstraction="reuse existing abstraction",
            refactor="no strong signal",
        ),
        ".project-guard-skill.md",
    )
    assert "New dependencies are potentially justified" in softer
    assert "Reuse existing structure: reuse existing abstraction." in softer
    assert "not clearly justified" in softer


def test_skill_template_is_generic():
    text = skill_template_text()
    for fragment in (
        "Requirement Fidelity",
        "Smallest Safe Change",
        "Scope Amendment",
        "Reuse Before Build",
    ):
        assert fragment in text
    for forbidden in (
        "tavily",
        "industry_research_agent",
        "domain exclusion",
    ):
        assert forbidden.lower() not in text.lower()
