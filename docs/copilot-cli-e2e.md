# GitHub Copilot CLI E2E Verification

## Environment

- Environment: Windows
- Tested product: GitHub Copilot CLI
- Project configuration: `.github/hooks/project-guard.json`
- Installation: `project-guard init-copilot .`

The Copilot CLI was installed and run through WinGet. This record covers the
Copilot CLI only; it does not extend the result to Copilot IDE or Cloud Agent.

## Integration

The tested Project Guard path was:

```text
userPromptTransformed
-> project-guard copilot-hook
-> Project Guard prepare
-> modifiedTransformedPrompt
-> Copilot CLI Agent
```

The Project Guard-owned Hook used the repository-level `version: 1` schema:

```json
{
  "version": 1,
  "hooks": {
    "userPromptTransformed": [
      {
        "type": "command",
        "bash": "project-guard copilot-hook",
        "powershell": "project-guard copilot-hook",
        "timeoutSec": 30
      }
    ]
  }
}
```

Project Guard does not register its own `userPromptSubmitted` Hook as the
transparent prepare path because command-hook output from that event does not
enter the model context.

## Read-only E2E

Prompt:

```text
What does this repository do?
```

Observed behavior:

- Copilot CLI searched for `.project-guard*` files.
- The five Guard artifacts were generated.
- Copilot CLI actively read `.project-guard-instructions.md`.
- Copilot CLI actively read `.project-guard-skill.md`.
- Copilot CLI read `.project-guard-contract.json`.
- Copilot CLI read `.project-guard-plan.json`.
- Copilot CLI read `.project-guard-agent-prompt.md`.
- Copilot CLI then inspected `app.py` and `test_app.py`.
- The final response was a read-only repository explanation.
- No production file was modified.

This is evidence that the dynamic governance context produced an observable
effect in the real Copilot CLI Agent flow. It is not evidence of deterministic
model behavior, fail-closed enforcement, or byte-level raw Prompt preservation.

## Coding E2E

Prompt:

```text
Add a --limit option that controls how many items are displayed.
Keep the change minimal and add a focused test if appropriate.
```

Observed behavior:

1. Copilot CLI searched for the relevant implementation.
2. Copilot CLI read `app.py` and `test_app.py`.
3. The Agent described a minimal change, a `limit` parameter, CLI parsing, a
   focused test, and the need for a Task Contract.
4. `app.py` was modified.
5. `test_app.py` was modified.
6. `.project-guard-task-contract.json` was created during the governed coding
   flow.
7. The Agent ran:

   ```text
   python -m unittest -v test_app.py
   ```

8. The focused test passed.

The observed result included the `--limit` behavior, a focused test, no new
third-party dependency, no unnecessary abstraction, and no unrelated
refactoring.

## Task Contract ordering

The observed log order was:

```text
read app.py / test_app.py
-> Agent stated that it would create the Task Contract
-> edit app.py
-> edit test_app.py
-> create .project-guard-task-contract.json
-> tests
```

Therefore this E2E record must not claim that the Task Contract was created
before production edits. The accurate statement is:

> The Agent recognized the Task Contract requirement, but in this E2E run the
> Task Contract file was created after the production edits.

The transformed Prompt can guide the Agent toward the Task Contract workflow,
but it does not enforce the creation order. Task Contract compliance remains
model-guided rather than an enforced invariant.

## Known limitations

- Only GitHub Copilot CLI has been verified by real coding E2E.
- Copilot IDE remains a separate limited integration; its full transparent
  governance flow was not verified by this test.
- Byte-level raw Prompt preservation is not claimed.
- Task Contract ordering remains model-guided.
- No `preToolUse` enforcement was implemented.
- No shell enforcement was implemented.
- No MCP enforcement was implemented.
- No automatic Review was implemented.
- Hook failure semantics remain dependent on Copilot host behavior.
