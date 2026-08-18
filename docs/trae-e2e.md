# TRAE IDE E2E Verification

## Environment

- Platform: Windows
- Agent: TRAE IDE
- Test repository: a separate Windows Git test repository
- Project configuration: `.trae/hooks.json`
- Installation command: `project-guard init-trae .`

## Hook activation

`init-trae` installed the project-level `UserPromptSubmit` Hook. TRAE
recognized the configuration in `Settings > Hooks > Project`, but the project
Hooks were not enabled by default. The tested flow required manually enabling
the configured project Hooks in that settings screen.

Before enablement, submitting a Prompt did not generate Guard artifacts. After
enablement, `UserPromptSubmit` invoked `project-guard trae-hook`, which ran
Project Guard `prepare`.

## Read-only E2E

Prompt:

```text
What does this repository do?
```

Before the test, existing `.project-guard-*` artifacts were removed. After the
Prompt, these five Guard-owned artifacts were generated:

- `.project-guard-agent-prompt.md`
- `.project-guard-contract.json`
- `.project-guard-instructions.md`
- `.project-guard-plan.json`
- `.project-guard-skill.md`

The TRAE response identified `.trae/hooks.json` and the generated Guard files
as Project Guard governance artifacts. No production edit was required.
This is observable evidence that the governance context affected the Agent
workflow; it is not a byte-level raw Prompt preservation guarantee.

## Coding E2E

Prompt:

```text
Add a --limit option that controls how many items are displayed.
Keep the change minimal and add a focused test if appropriate.
```

Observed result:

- `app.py` was modified
- `test_app.py` was modified
- `.project-guard-task-contract.json` was created during the governed coding flow
- no third-party dependency was added
- no unnecessary abstraction or unrelated refactor was added
- focused test `test_limit_returns_first_n_items` was added

The implementation preserved the default behavior when `--limit` was not
provided and used the standard-library `argparse` CLI path.

## Verification

```text
python -m unittest
2 tests passed

python app.py
['a', 'b', 'c', 'd']

python app.py --limit 2
['a', 'b']
```

## Known limitations

- Project Hooks require manual enablement in the observed TRAE environment.
- Only TRAE IDE on Windows was tested.
- TRAE does not provide a byte-level raw Prompt guarantee.
- Task Contract creation remains Agent/model-guided.
- No PreToolUse enforcement was implemented.
- No shell or MCP enforcement was implemented.
- No automatic Review or Stop-based Review was implemented.
- Enterprise deployment was not verified.
