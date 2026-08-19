from project_guard.artifacts import (
    PROJECT_GUARD_OWNED_PATHS,
    is_project_guard_artifact,
)


def test_owned_artifact_matching_is_exact_and_separator_independent():
    assert is_project_guard_artifact(".cline/plugins/project-guard.js")
    assert is_project_guard_artifact(".cline\\plugins\\project-guard.js")
    assert is_project_guard_artifact("./.project-guard-plan.json")
    assert not is_project_guard_artifact(".cline/rules/custom.md")
    assert not is_project_guard_artifact(".project-guard-notes.md")


def test_owned_paths_include_only_confirmed_project_guard_outputs():
    assert ".cline/plugins/project-guard.js" in PROJECT_GUARD_OWNED_PATHS
    assert ".claude/settings.json" not in PROJECT_GUARD_OWNED_PATHS
    assert ".codex/hooks.json" not in PROJECT_GUARD_OWNED_PATHS
    assert ".github/hooks/project-guard.json" not in PROJECT_GUARD_OWNED_PATHS
    assert ".trae/hooks.json" not in PROJECT_GUARD_OWNED_PATHS
