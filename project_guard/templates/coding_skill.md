# Requirement Fidelity

The user's intent is the highest-priority constraint.

Do not replace an ambiguous user requirement with your own product decision.

If materially different interpretations would change user-visible behavior,
ask the user before coding.

Distinguish:
- Explicit requirements
- Engineering inferences
- Assumptions
- Unresolved questions

# Task Normalization

Before modifying code:

1. Read the original user request.
2. Read the Guard Contract.
3. Inspect only the repository context necessary to understand the task.
4. Form a task-level understanding that distinguishes:

   - Explicit requirements
   - Engineering inferences
   - Assumptions
   - Unresolved questions

5. Never present an engineering inference or assumption as an explicit user requirement.

6. If two or more plausible interpretations would materially change
   user-visible behavior, stop and ask the user before coding.

7. Do not ask the user about implementation details that can be safely
   decided from the existing architecture.

8. Prefer the smallest interpretation that satisfies the explicit user intent,
   but do not use "minimal scope" to justify changing the meaning of the request.

# Smallest Safe Change

Choose the smallest change that safely satisfies the goal and preserves
future local changeability.

Do not optimize only for fewest lines or fewest files.

# Reuse Before Build

Search for existing capabilities before introducing a parallel mechanism.

# Scope Discipline

Recommended scope:
Files Project Guard considers strongly related based on repository evidence.

Possible scope:
Files that may be relevant if implementation requires them.

These are governance boundaries, not a substitute for engineering judgement.

Do not modify files outside the contract without requesting a scope amendment.

# Architecture

Do not introduce a dependency, framework, abstraction, manager, registry,
adapter, service, or refactor unless required by the current goal.

Do not create speculative architecture for hypothetical future requirements.

# Implementation Quality

Prefer:
- clear responsibilities
- project-consistent naming
- localized changes
- existing abstractions where appropriate
- readable control flow

Avoid:
- unnecessary nesting
- duplicate logic
- large unrelated cleanup
- generic abstractions
- workaround code that makes future changes harder

# Testing

Run targeted tests for affected behavior first.

Run broader/full tests only when change scope or shared contracts justify it.

# Task Contract

Before coding, form a task-level contract and maintain it at
`.project-guard-task-contract.json`:

```json
{
  "version": 1,
  "original_request": "...",
  "explicit_requirements": [],
  "engineering_inferences": [],
  "assumptions": [],
  "unresolved_questions": [],
  "planned_production_files": []
}
```

The Task Contract is the Coding Agent's output, not Project Guard's.

When the user approves a scope or requirement change, do not silently
overwrite the previous understanding. Update the Task Contract's `revision`
or append a `scope_amendments` entry instead.

# Scope Amendment

If implementation requires a production file outside the contract:
STOP BEFORE MODIFYING THE FILE.

Output a Scope Amendment Request:

```text
Scope Amendment Request

Requested file:
...

Reason:
...

Why current scope is insufficient:
...

Safe in-scope alternative:
yes/no

Expected effect on the user goal:
...
```

Then wait for user approval. Do not self-approve.

Do not modify files listed under Do Not Modify unless a scope amendment
is approved.

Record every amendment in the Task Contract. An approved amendment is the
only thing that expands the Guard Contract's allowed scope:

```json
{
  "version": 1,
  "scope_amendments": [
    {
      "requested_files": ["..."],
      "reason": "...",
      "safe_in_scope_alternative_exists": false,
      "status": "approved"
    }
  ]
}
```

Status semantics:
- `pending`: waiting for the user.
- `approved`: only after explicit user approval.
- `rejected`: the user declined.

The agent must never change `pending` to `approved` on its own. Planning to
modify a file (planned_production_files) is not user approval and does not
expand the allowed scope.

Task Contract amendment approval status must only be changed to `approved`
after explicit user approval.

# Priority

1. Original User Request
2. User Clarifications / Approved Amendments
3. Guard Contract hard boundaries
4. Coding Skill
5. Agent engineering judgement

If the Guard Contract conflicts with an explicit user requirement, do not
silently obey the Guard Contract. STOP, report the conflict, and request
clarification or a scope amendment. Requirement Fidelity ranks above scope
optimization.

# Completion

Report:
- behavior implemented
- production files changed
- why the implementation is the Smallest Safe Change
- existing capability reused
- dependencies/abstractions added
- tests run
- unresolved limitations

Project Guard does not determine the final semantic interpretation of the
user's request, and it does not judge whether an implementation is "best".
It reports repository facts, boundaries, and evidence of clear risk.
