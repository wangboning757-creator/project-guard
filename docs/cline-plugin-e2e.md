# Cline CLI Plugin E2E Record

## Date and environment

- Date: 2026-08-18
- Environment: Windows
- Agent: Cline CLI
- Test repository: a separate Windows Git test repository
- Project Plugin: `.cline/plugins/project-guard.js`
- Launch mode: plain `cline`, without `--plugin` or manual loading

## Request

```text
Add a --reverse option that reverses the displayed items.
Keep the change minimal and add a focused test if appropriate.
```

## Observed sequence

The project-local Plugin was automatically discovered. Its `beforeModel`
runtime hook ran before the production edit, invoked Project Guard `prepare`,
and generated:

```text
.project-guard-plan.json
.project-guard-contract.json
.project-guard-instructions.md
.project-guard-skill.md
.project-guard-agent-prompt.md
```

The governance message was added to the current model request. Cline then
read the generated governance files and created the Agent-owned:

```text
.project-guard-task-contract.json
```

The tested implementation changed only `app.py` as the production file and
added focused tests. It added no dependency and no new abstraction. Six
unittest tests passed.

## Interpretation boundary

This record documents observed behavior for the tested Windows Cline CLI
flow. It does not establish a byte-level raw Prompt guarantee, full
enforcement, or support for other Cline hosts. Task Contract adherence remains
model-guided, and Project Guard Review remains an independent audit.

The Plugin does not implement `beforeTool`, shell enforcement, MCP enforcement,
or automatic `TaskComplete` Review. Plugin load/setup failure may be fail-open,
and in-memory Prompt deduplication state is lost when the Plugin process
restarts.
