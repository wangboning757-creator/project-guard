# Project Guard

Project Guard is a local-first governance layer for coding agents. It turns
a natural-language request into repository facts, governed boundaries,
structured contracts, and an independent diff review - so a Coding Agent
(such as Claude Code) can implement the user's actual requirement as the
Smallest Safe Change.

*Experimental v0.1.0*

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

Then run a governed coding task with local Claude Code:

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

## Core Principles

- **Requirement Fidelity** - the implementation must satisfy the user's
  actual request.
- **Smallest Safe Change** - the smallest change that is safe, correct for
  the requirement, local, and does not damage future changeability. This is
  not simply fewest lines or fewest files.
- **Reuse Before Build** - prefer wiring an existing capability over
  implementing a parallel mechanism.
- **Scope Discipline** - keep production changes inside the governed scope;
  genuinely necessary out-of-contract production changes require a Scope
  Amendment.
- **Future-change Safety** - do not achieve a tiny current diff through a
  brittle workaround that makes the project harder to safely change later.
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

Experimental transparent activation is available for Claude Code through a
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
repository currently trigger preparation, including ordinary questions. Claude
following the generated instructions and maintaining the Task Contract remains
model-guided; Project Guard review remains the independent final audit.

The setup only modifies the target repository's `.claude/` configuration. It
does not modify `~/.claude/`. `project-guard run` remains the reliable explicit
fallback for environments without this hook integration.

Known UX limitation: Claude Code currently stays in its interactive session
after completing a task. The user exits the session (for example with
`/exit`) before Project Guard resumes and runs the final review. Project
Guard does not detect Claude's completion automatically.

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

## Local-First Design

- local CLI, works against a git repository
- no vector database
- no web dashboard
- no SaaS backend
- no database required for Project Guard governance state
- no LLM inside the Guard Core for business-semantic judgment
- no dependency-heavy Agent framework

## Current Scope / Non-goals

For the v0.1.0 state:

- only the local Claude Code runner is integrated
- no Codex integration yet
- no TRAE integration yet
- no MCP server
- no multi-Agent provider framework
- no IDE plugin
- no GitHub App
- no SaaS / cloud control plane
- no automatic semantic correctness judge
- no automatic Claude completion detection

## Status

Project Guard is experimental v0.1.0. This release is intended to validate a
small, local-first governance layer around real Coding Agent workflows.
