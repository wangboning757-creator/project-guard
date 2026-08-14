# Requirement Fidelity

The user's intent is the highest-priority constraint.

Do not replace an ambiguous user requirement with your own product decision.

If materially different interpretations would change user-visible behavior,
ask the user before coding.

Distinguish:
- Explicit user requirements
- Engineering inferences
- Assumptions

# Smallest Safe Change

Choose the smallest change that safely satisfies the goal and preserves
future local changeability.

Do not optimize only for fewest lines or fewest files.

# Reuse Before Build

Search for existing capabilities before introducing a parallel mechanism.

# Scope Discipline

Treat recommended scope as the primary area.
Treat possible scope as allowed only when necessary.

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

# Scope Amendment

If implementation requires a production file outside the contract:
stop before modifying it.

Report:
- requested file
- exact reason
- why current allowed scope is insufficient
- whether a safe in-scope alternative exists

Wait for user approval.

# Completion

Report:
- behavior implemented
- production files changed
- why the implementation is the Smallest Safe Change
- existing capability reused
- dependencies/abstractions added
- tests run
- unresolved limitations
