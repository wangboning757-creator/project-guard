# project-guard

AI Coding Project Guard - a small, local-first CLI that helps coding agents
(Codex, Claude Code, ...) keep long-running projects from ballooning: giant
files, duplicate implementations, dependency creep, uncontrolled change scope,
and unrequested features.

## Install

Requires Python 3.12+.

```bash
pip install -e .
```

## Usage

```bash
project-guard inspect .                 # project health report
project-guard context .                 # compact agent context (Markdown)
project-guard plan . "Add PDF export"   # pre-implementation check
project-guard review .                  # git diff risk analysis
project-guard score .                   # AI coding readiness score
```

## Design rules

- Minimal implementation only; no speculative features.
- Static analysis only - no LLM, no vector DB, no background agent, no
  automatic code modification.
- Transparent, human-readable rules (thresholds live in
  `project_guard/config.py`).
- Local-first: everything runs on your machine against your git repo.

## Non-goals (current version)

No web dashboard, IDE/VS Code plugin, GitHub app, SaaS, auth/RBAC, cloud
deployment, vector search, long-term memory, autonomous coding, or auto-fix.
Those are recorded as future ideas, not implemented.
