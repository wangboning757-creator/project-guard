# Codex E2E Verification

## Environment

- Environment: Windows
- Tested surfaces: Codex CLI and Codex Desktop
- Project configuration: `.codex/hooks.json`

## Codex CLI

The project Hook was discovered by plain `codex`. Codex displayed a `Hooks
need review` prompt, and the user explicitly selected trust for the Hook.

The observed sequence was:

1. `UserPromptSubmit` completed.
2. Project Guard prepared the request.
3. The five Guard artifacts were generated.
4. Codex read `.project-guard-skill.md`.
5. Codex created `.project-guard-task-contract.json` before production edits.
6. The implementation changed only the necessary production file.
7. A focused test and CLI smoke test passed.
8. Task Contract JSON validation passed and the coding task completed.

Coding request:

```text
Add a --limit option that controls how many items are displayed.
Keep the change minimal and add a focused test if appropriate.
```

The test used no new dependency or abstraction.

## Codex Desktop

An earlier experiment in the same test repository did not observe the project
Hook firing. A later Desktop task, after the project Hook had been reviewed and
trusted through Codex CLI, did observe the following:

- Guard artifacts were generated automatically
- Desktop read the Guard instructions and Skill
- an explanatory request remained read-only
- the coding request below created the Task Contract before production edits
- `app.py` and its focused test were updated
- unittest and CLI smoke checks passed

```text
Add a --reverse option that reverses the displayed items.
Keep the change minimal and add a focused test if appropriate.
```

This records the observed order only. It does not establish that CLI trust is
required for Desktop, or that trust is shared between CLI and Desktop.

## Interpretation boundary

These are real coding E2E observations for the tested Windows environment.
Codex integration remains Experimental because Hook trust, host behavior, and
version compatibility have not been established as long-term guarantees.
