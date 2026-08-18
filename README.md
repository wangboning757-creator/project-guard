# Project Guard

Project Guard is a local-first governance layer for coding agents. It turns
a natural-language request into repository facts, governed boundaries,
structured contracts, and an independent diff review - so a Coding Agent
(such as Claude Code) can implement the user's actual requirement as the
Smallest Safe Change.

*Experimental v0.4.0*

## Why Project Guard

Coding Agents can complete a request while still:

- changing too much
- duplicating an existing capability
- creating unnecessary abstractions or dependencies
- modifying unrelated files
- solving a slightly different problem than the user asked
- introducing a brittle workaround

Project Guard adds an independent governance layer around the coding
process. It does not replace the Coding Agent - it gives the Agent
repository facts, clear boundaries, and an independent review of the
resulting diff.

## Quick Start

Requires Python 3.12+. Install from a local checkout:

```bash
pip install -e .
```

For the experimental Codex CLI integration, set up the repository once:

```bash
project-guard init-codex .
codex
```

Then submit a normal natural-language coding request in Codex CLI, for
example:

```text
Add a CLI option to limit the maximum number of search queries used in an ask run.
```

This installs the project-scoped Codex `UserPromptSubmit` Hook. The first use
may show `Hooks need review`; review and trust is a Codex security mechanism.
Real coding E2E has been verified for the tested Codex CLI environment. All
prompts are expected to trigger preparation, including ordinary questions;
there is no coding-intent classifier in this experimental integration.

For transparent Claude Code activation, set up the repository once:

```bash
project-guard init-claude .
claude
```

Then submit a normal natural-language coding request in Claude Code, for
example:

```text
Add a CLI option to limit the maximum number of search queries used in an ask run.
```

After the one-time setup, Project Guard activates automatically through the
project-scoped Claude Code hook. For the explicit, fully governed runner,
which remains the reliable fallback for both integrations, use:

```bash
project-guard run . "Add a CLI option to limit the maximum number of search queries used in an ask run."
```

Internally, `run` prepares the governance artifacts, launches Claude Code
with a generated agent prompt, waits while you interact with Claude, and
then validates the Agent's Task Contract and reviews the resulting git diff
automatically. You do not need to know the internal artifacts to start.

## How It Works

```text
User natural-language request
        ↓
Project Guard prepare
        ↓
Engineering Contract + fixed Coding Skill
        ↓
Coding Agent
        ↓
Agent Task Contract
        ↓
clarification / Scope Amendment if required
        ↓
implementation + targeted tests
        ↓
Project Guard diff review
```

Responsibilities are deliberately separated:

- The user defines what they want.
- Project Guard provides repository facts, governance boundaries, and
  structured contracts.
- The Coding Agent performs semantic interpretation and implementation.
- Project Guard review audits the actual changes independently.

Project Guard does not prove semantic correctness, and it does not claim to
choose the "best" implementation.

`prepare` may be triggered automatically by the verified project-scoped
Claude Code `UserPromptSubmit` hook, the tested Codex project Hook, or the
Cline CLI Plugin. The Coding Agent still decides how to interpret the request
and follow the generated governance artifacts.

## Core Principles

- **P0 Requirement Fidelity** - the implementation must satisfy the user's
  actual request.
- **P1 Avoid Unnecessary Expansion** - avoid unnecessary architecture,
  dependencies, frameworks, and abstractions.
- **P2 Future-change Safety** - do not achieve a tiny current diff through a
  brittle workaround that makes the project harder to safely change later.
- **P3 Reuse Before Build** - prefer wiring an existing capability over
  implementing a parallel mechanism.
- **P4 Scope Discipline** - keep production changes inside the governed scope;
  genuinely necessary out-of-contract production changes require a Scope
  Amendment.
- **Smallest Safe Change** - the smallest change that is safe, correct for
  the requirement, local, and does not damage future changeability. This is
  not simply fewest lines or fewest files.
- **Targeted Testing** - run targeted tests for the affected behavior first;
  broaden to the full suite only when the affected scope justifies it.

## Commands

Primary workflow:

```text
project-guard run PATH "REQUEST"
    Prepare → run local Claude Code → validate Task Contract → review

project-guard prepare PATH "REQUEST"
    Generate the governance handoff without launching an Agent

project-guard init-claude PATH
    Install experimental project-scoped Claude Code activation

project-guard init-codex PATH
    Install Experimental Codex CLI integration

project-guard init-copilot PATH
    Install Experimental GitHub Copilot repository Hook integration

project-guard init-cline-plugin PATH
    Install the recommended Experimental Cline CLI Plugin integration

project-guard init-cline PATH
    Install the legacy Experimental Cline file-hook integration

project-guard review PATH
    Review the git diff against Guard / Task contracts
    (--contract, --task-contract, --plan, --instructions, --skill)
```

Secondary and debugging commands:

```text
project-guard plan PATH "REQUEST"
    Pre-implementation check
    (--output-plan, --output-contract, --output-instructions, --output-skill)

project-guard inspect PATH   Project health report
project-guard context PATH   Compact Markdown project context
project-guard score PATH     AI coding readiness score
```

## Claude Code Integration

`project-guard run` supports the locally installed Claude Code CLI:

- resolves the `claude` executable from PATH (including the npm
  `claude.CMD` shim on Windows)
- generates the Guard artifacts
- launches Claude Code with the prepared Agent prompt
- inherits stdin/stdout/stderr, so Claude remains interactive
- Claude creates or updates the Agent-owned Task Contract
- when Claude exits successfully, Project Guard validates the Task Contract
  and runs the final review automatically

v0.4.0 includes transparent project-scoped activation for Claude Code through a
one-time project setup:

```bash
project-guard init-claude .
```

After setup, use Claude Code normally:

```text
claude
> Add a CLI option to ...
```

The project-scoped `UserPromptSubmit` hook receives the exact submitted prompt,
resolves the Git repository root, runs the existing `prepare` workflow, and
adds short governance context for Claude. All prompts in an opted-in
repository currently trigger preparation, including ordinary questions. There
is intentionally no coding-intent classifier in v0.4.0. Claude following the
generated instructions and maintaining the Task Contract remains model-guided;
Project Guard review remains the independent final audit.

The setup only modifies the target repository's `.claude/` configuration. It
does not modify `~/.claude/`. `project-guard run` remains the reliable explicit
fallback for environments without this hook integration.

Known UX limitation: when using `project-guard run`, Claude Code currently
stays in its interactive session after completing a task. The user must exit
the session (for example with `/exit`) before Project Guard resumes and runs
the final review. Project Guard does not detect Claude's completion
automatically.

## Codex CLI Integration

v0.4.0 includes an experimental project-scoped Codex CLI integration:

```bash
project-guard init-codex .
```

The setup writes only the target repository's `.codex/hooks.json`; it does not
modify `~/.codex/`. The Hook receives the submitted prompt, resolves the Git
repository root, runs the existing `prepare` workflow, and returns short
governance context. Real coding E2E has been verified for the tested Codex CLI
flow: the Hook was reviewed and trusted, artifacts were generated, Codex read
the Coding Skill, created the Task Contract before production edits, added a
focused test, and completed the task.

All prompts in an opted-in repository are expected to trigger preparation,
including ordinary questions. No coding-intent classifier is used. Codex
adherence to the generated instructions and Task Contract remains
model-guided, while Project Guard Review remains the independent diff-based
audit. `project-guard run` remains the explicit reliable fallback.

Codex Hook trust and compatibility across different environments and versions
have not been established as a long-term guarantee.

### Codex Desktop

Codex Desktop is also marked **Experimental — real coding E2E verified** for
the tested Windows environment. An earlier experiment did not observe the
project Hook firing. A later Desktop task in the same repository, after the
project Hook had been reviewed and trusted through Codex CLI, generated the
Guard artifacts, read the instructions and Skill, created the Task Contract
before editing `app.py`, added focused tests, and completed the coding task.

This records the observed sequence only. It does not prove that CLI trust is
required for Desktop, or that trust is shared across CLI and Desktop.

## GitHub Copilot Integration

v0.4.0 includes a limited experimental project-scoped GitHub Copilot integration:

```bash
project-guard init-copilot .
```

This installs the repository-level `.github/hooks/project-guard.json` using
GitHub's official `version: 1` Hook format and the `userPromptSubmitted` event.
The Hook receives the exact submitted prompt and `cwd`, resolves the Git
repository root, and runs the existing `prepare` workflow. It does not modify
user-level Copilot configuration.

For command-configured `userPromptSubmitted` Hooks, GitHub currently drops the
Hook's model-facing output; `additionalContext` is not an available injection
field for this configuration. Project Guard therefore emits only an official
display-only progress message after prepare. This PoC does not claim automatic
governance context injection into the Copilot model.

There is no `preToolUse` enforcement in this integration. Coding Agent
adherence to the generated instructions and Task Contract remains
model-guided, while Project Guard Review remains the independent final
Git Diff audit. Real GitHub Copilot full governance-loop dogfood has not been
performed. This integration is limited to the deterministic prepare path; it
is not full governance support.

Although Copilot `preToolUse` can deny tool calls in supported environments,
using it for full Project Guard scope enforcement would require session/task
association, tool schema handling, shell-bypass handling, and additional
state. That work is intentionally outside this release.

## Cline CLI Integration

### Recommended: Cline CLI Plugin runtime

v0.4.0 includes an experimental project-scoped Cline CLI Plugin integration:

```bash
project-guard init-cline-plugin .
```

This installs `.cline/plugins/project-guard.js` and does not modify global
Cline configuration. The Plugin uses Cline's `beforeModel` runtime hook to
resolve `ctx.workspaceInfo.rootPath`, run the existing `prepare` workflow, and
append a short governance message to the current model request.

Real CLI E2E was observed and verified for the tested Windows Cline CLI flow:

- plain `cline` automatically discovered the project Plugin
- `beforeModel` executed before coding
- the five Guard artifacts were generated
- the governance message reached the model request
- Cline read the generated governance artifacts
- Cline created `.project-guard-task-contract.json` before the coding workflow
  proceeded

The E2E record is documented in
[`docs/cline-plugin-e2e.md`](docs/cline-plugin-e2e.md).

Current limitations:

- only the Cline CLI runtime has been verified; VS Code and JetBrains are not
  in the current validation scope
- the latest user message is extracted from `beforeModel`'s
  `request.messages`; Cline does not provide a byte-level raw Prompt guarantee
- Plugin load or setup failure may be fail-open
- Task Contract creation remains model-guided and Agent-owned
- there is no `beforeTool`, shell, or MCP enforcement
- there is no automatic `TaskComplete` Review
- same-Prompt deduplication uses in-memory session state; it is lost on process
  restart
- Prompt arguments currently pass through the CLI command line and may be
  subject to Windows command-length limits

### Legacy: Cline file-hook experiment

The older file-hook experiment remains available for historical and testing
purposes:

```bash
project-guard init-cline .
```

It installs `.cline/hooks/` files and has deterministic tests, but automatic
discovery was not observed in the real Cline CLI test. It is not recommended
for new setups.

### Integration support summary

| Platform | Integration | Status |
| --- | --- | --- |
| Claude Code | project-level `UserPromptSubmit` | Verified — real coding E2E |
| Codex CLI | project `.codex` Hook | Experimental — real coding E2E verified |
| Codex Desktop | project `.codex` Hook | Experimental — real coding E2E verified |
| Cline CLI | project-local Plugin / `beforeModel` | Experimental — real coding E2E verified |
| GitHub Copilot | `userPromptSubmitted` prepare | Experimental — limited integration |
| Cline CLI | file Hook experiment | Legacy experimental |

## Contracts and Governance

Guard-owned artifacts (written by `prepare` / `run`):

```text
.project-guard-plan.json
.project-guard-contract.json
.project-guard-instructions.md
.project-guard-skill.md
.project-guard-agent-prompt.md
```

Agent-owned:

```text
.project-guard-task-contract.json
```

The separation exists because the Guard records repository facts and
boundaries, while the Agent records its semantic interpretation, assumptions,
planned files, and any scope amendments. Only user-approved amendments
(`status: "approved"`) expand the effective allowed scope; an Agent's plan
alone does not.

Review independently compares the Engineering Contract, Agent-owned Task
Contract, approved Scope Amendments, and the actual Git Diff. It is an audit
of structural and governance signals, not a proof of semantic correctness.

## Local-First Design

- local CLI, works against a git repository
- no vector database
- no web dashboard
- no SaaS backend
- no database required for Project Guard governance state
- no LLM inside the Guard Core for business-semantic judgment
- no dependency-heavy Agent framework

## Current Scope / Non-goals

For the v0.4.0 state:

- the project-scoped Claude Code transparent integration is verified by a real
  Claude Code E2E run
- the Experimental Codex CLI integration has verified real coding E2E evidence
- the Experimental Codex Desktop integration has verified real coding E2E
  evidence in the tested environment
- the Experimental Cline CLI Plugin integration is implemented and verified by
  a real Cline CLI E2E run
- the legacy Cline file-hook experiment remains unverified for automatic
  discovery
- an earlier Codex Desktop experiment did not observe the Hook; a later task
  in the same trusted project did
- no TRAE integration yet
- no MCP server
- no multi-Agent provider framework
- no IDE plugin
- no GitHub App
- no SaaS / cloud control plane
- no automatic semantic correctness judge
- no automatic Claude completion detection

## Status

Project Guard is experimental v0.4.0. This release records verified real coding
E2E evidence for Claude Code, Codex CLI, Codex Desktop, and the Cline CLI
Plugin, while preserving the local-first governance model and the explicit
`project-guard run` fallback.
