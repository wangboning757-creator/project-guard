"""project-guard CLI entry point."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import typer

from . import (
    claude_integration,
    codex_integration,
    instructions,
    planner,
    reviewer,
    scanner,
    scoring,
)
from . import context as context_mod

app = typer.Typer(
    help="Small local-first AI coding governance CLI.",
    no_args_is_help=True,
)


def _write_artifact(path: Path, content: str, label: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        typer.echo(f"Error: cannot write {label}: {exc}", err=True)
        raise typer.Exit(1) from exc


def _prepare_task(root: Path, request: str) -> dict[str, Path]:
    """Generate the standard guard artifacts for a request (shared by
    prepare and run)."""
    result = planner.analyze_plan(root, request)
    snapshot = result.snapshot
    contract = result.contract
    if snapshot is None or contract is None:
        typer.echo("Error: no plan/contract available", err=True)
        raise typer.Exit(1)
    artifacts = {
        "plan": root / ".project-guard-plan.json",
        "contract": root / ".project-guard-contract.json",
        "instructions": root / ".project-guard-instructions.md",
        "skill": root / ".project-guard-skill.md",
        "agent_prompt": root / ".project-guard-agent-prompt.md",
    }
    _write_artifact(
        artifacts["plan"],
        snapshot.model_dump_json(indent=2) + "\n",
        "plan snapshot",
    )
    _write_artifact(
        artifacts["contract"],
        contract.model_dump_json(indent=2) + "\n",
        "engineering contract",
    )
    _write_artifact(
        artifacts["instructions"],
        instructions.format_instructions(
            contract, ".project-guard-skill.md"
        ),
        "agent instructions",
    )
    _write_artifact(
        artifacts["skill"],
        instructions.skill_template_text(),
        "coding skill",
    )
    _write_artifact(
        artifacts["agent_prompt"],
        instructions.format_agent_prompt(),
        "agent prompt",
    )
    return artifacts


def _resolve_claude_executable() -> str | None:
    """Locate the Claude Code CLI via the standard-library lookup."""
    return shutil.which("claude")


def _claude_command(executable: str, prompt_text: str) -> list[str]:
    """Build the Claude Code CLI invocation for the resolved executable.

    Verified against `claude --help`: `claude [prompt]` starts an
    interactive session by default with the prompt as the initial task;
    `-p/--print` is non-interactive and is intentionally not used.
    The resolved executable path is passed directly. On Windows this is
    the npm `claude.CMD` shim, which Python subprocess executes directly
    (verified in the target environment).
    """
    return [executable, prompt_text]


def _run_claude(cmd: list[str], cwd: Path) -> int:
    """Launch Claude Code with inherited terminal stdio (interactive)."""
    return subprocess.run(cmd, cwd=str(cwd), check=False).returncode


@app.command()
def inspect(path: Path = typer.Argument(".", help="Project directory")):
    """Analyze a project and print a health report."""
    typer.echo(scanner.format_inspect(scanner.scan_project(path)))


@app.command()
def context(path: Path = typer.Argument(".", help="Project directory")):
    """Generate a compact Markdown context for coding agents."""
    typer.echo(context_mod.build_context(path, scanner.scan_project(path)))


@app.command()
def plan(
    path: Path = typer.Argument(".", help="Project directory"),
    request: str = typer.Argument(
        ..., help="Feature request to check before implementation"
    ),
    output_plan: Path | None = typer.Option(
        None,
        "--output-plan",
        help="Write a plan snapshot JSON to this file (no auto-persist)",
    ),
    output_instructions: Path | None = typer.Option(
        None,
        "--output-instructions",
        help="Write agent instructions Markdown to this file (no auto-persist)",
    ),
    output_contract: Path | None = typer.Option(
        None,
        "--output-contract",
        help="Write the Engineering Contract JSON to this file "
        "(no auto-persist)",
    ),
    output_skill: Path | None = typer.Option(
        None,
        "--output-skill",
        help="Copy the fixed Coding Skill template to this file",
    ),
):
    """Check a feature request before implementation."""
    result = planner.analyze_plan(path, request)
    if output_plan is not None:
        snapshot = result.snapshot
        if snapshot is None:
            typer.echo("Error: no plan snapshot available", err=True)
            raise typer.Exit(1)
        _write_artifact(
            output_plan,
            snapshot.model_dump_json(indent=2) + "\n",
            "plan snapshot",
        )
        typer.echo(f"Plan snapshot written to {output_plan}")
    if output_contract is not None:
        contract = result.contract
        if contract is None:
            typer.echo("Error: no engineering contract available", err=True)
            raise typer.Exit(1)
        _write_artifact(
            output_contract,
            contract.model_dump_json(indent=2) + "\n",
            "engineering contract",
        )
        typer.echo(f"Engineering contract written to {output_contract}")
    if output_skill is not None:
        _write_artifact(
            output_skill,
            instructions.skill_template_text(),
            "coding skill",
        )
        typer.echo(f"Coding skill written to {output_skill}")
    if output_instructions is not None:
        contract = result.contract
        if contract is None:
            typer.echo("Error: no engineering contract available", err=True)
            raise typer.Exit(1)
        skill_path = output_skill or Path(".project-guard-skill.md")
        _write_artifact(
            output_instructions,
            instructions.format_instructions(contract, skill_path),
            "agent instructions",
        )
        typer.echo(f"Agent instructions written to {output_instructions}")
    typer.echo(planner.format_plan(result))


@app.command()
def prepare(
    path: Path = typer.Argument(".", help="Project directory"),
    request: str = typer.Argument(
        ..., help="Feature request to prepare for a Coding Agent"
    ),
):
    """Prepare guard artifacts and an agent-ready handoff for a request."""
    root = Path(path)
    _prepare_task(root, request)

    task_contract_path = root / ".project-guard-task-contract.json"
    if task_contract_path.is_file():
        typer.echo("Existing Task Contract detected.")
        typer.echo("It is agent-owned and was left unchanged.")
        typer.echo(
            "Ensure the Coding Agent updates it for the new request "
            "before coding."
        )
        typer.echo("")

    typer.echo("Project Guard task prepared.")
    typer.echo("")
    typer.echo("Request:")
    typer.echo(request)
    typer.echo("")
    typer.echo("Generated:")
    for name in (
        ".project-guard-plan.json",
        ".project-guard-contract.json",
        ".project-guard-instructions.md",
        ".project-guard-skill.md",
        ".project-guard-agent-prompt.md",
    ):
        typer.echo(f"- {name}")
    typer.echo("")
    typer.echo("Agent handoff:")
    typer.echo(".project-guard-agent-prompt.md")


@app.command("init-claude")
def init_claude(
    path: Path = typer.Argument(".", help="Git project directory"),
):
    """Install project-scoped Claude Code transparent activation."""
    try:
        result = claude_integration.install_claude_integration(path)
    except claude_integration.ClaudeIntegrationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo("Project Guard Claude integration installed.")
    typer.echo("")
    typer.echo(f"Repository: {result.root}")
    typer.echo("")
    typer.echo("Installed/updated:")
    settings_status = "updated" if result.settings_changed else "already present"
    claude_md_status = "updated" if result.claude_md_changed else "already present"
    typer.echo(f"- {result.settings_path.relative_to(result.root)} ({settings_status})")
    typer.echo(f"- {result.claude_md_path.relative_to(result.root)} ({claude_md_status})")
    typer.echo("")
    typer.echo("Normal use:")
    typer.echo("claude")


@app.command("init-codex")
def init_codex(
    path: Path = typer.Argument(".", help="Git project directory"),
):
    """Install project-scoped Codex CLI transparent activation."""
    try:
        result = codex_integration.install_codex_integration(path)
    except codex_integration.CodexIntegrationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo("Project Guard Codex CLI integration installed.")
    typer.echo("")
    typer.echo(f"Repository: {result.root}")
    typer.echo("")
    typer.echo("Installed/updated:")
    hooks_status = "updated" if result.hooks_changed else "already present"
    typer.echo(
        f"- {result.hooks_path.relative_to(result.root)} ({hooks_status})"
    )
    typer.echo("")
    typer.echo(
        "First use: Codex may ask you to review and trust the project Hook."
    )
    typer.echo("")
    typer.echo("Normal use:")
    typer.echo("codex")


@app.command("claude-hook", hidden=True)
def claude_hook():
    """Internal Claude Code UserPromptSubmit hook entry point."""
    raise typer.Exit(claude_integration.run_user_prompt_hook())


@app.command("codex-hook", hidden=True)
def codex_hook():
    """Internal Codex CLI UserPromptSubmit hook entry point."""
    raise typer.Exit(codex_integration.run_user_prompt_hook())


@app.command()
def run(
    path: Path = typer.Argument(".", help="Project directory"),
    request: str = typer.Argument(
        ..., help="Feature request to implement with Claude Code"
    ),
):
    """Prepare a governed coding task, run it with local Claude Code,
    then review the resulting changes."""
    root = Path(path)
    typer.echo("Project Guard: preparing task...")
    artifacts = _prepare_task(root, request)
    task_contract_path = root / ".project-guard-task-contract.json"
    typer.echo("")
    typer.echo("Project Guard: starting Claude Code...")
    prompt_text = artifacts["agent_prompt"].read_text(encoding="utf-8")
    executable = _resolve_claude_executable()
    if executable is None:
        typer.echo("Claude Code executable was not found.", err=True)
        typer.echo(
            "Install/configure Claude Code and ensure `claude` "
            "is available on PATH.",
            err=True,
        )
        raise typer.Exit(1)
    cmd = _claude_command(executable, prompt_text)
    try:
        exit_code = _run_claude(cmd, root)
    except OSError:
        typer.echo("Claude Code executable was not found.", err=True)
        typer.echo(
            "Install/configure Claude Code and ensure `claude` "
            "is available on PATH.",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo("")
    typer.echo("Project Guard: Claude Code finished.")
    if exit_code != 0:
        typer.echo(
            f"Claude Code exited with status {exit_code}.", err=True
        )
        typer.echo("Project Guard run was not completed.", err=True)
        raise typer.Exit(exit_code)
    if not task_contract_path.is_file():
        typer.echo("Claude Code finished without producing", err=True)
        typer.echo(".project-guard-task-contract.json.", err=True)
        typer.echo("Project Guard review was not run.", err=True)
        raise typer.Exit(1)
    try:
        task_contract_obj = reviewer.load_task_contract(task_contract_path)
    except reviewer.TaskContractError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if task_contract_obj.original_request != request:
        typer.echo(
            "Claude Code did not update the Agent-owned Task Contract",
            err=True,
        )
        typer.echo("for the current request.", err=True)
        typer.echo("Project Guard review was not run.", err=True)
        raise typer.Exit(1)
    typer.echo("")
    typer.echo("Project Guard: reviewing changes...")
    _review_contract_mode(
        root,
        artifacts["contract"],
        task_contract_path,
        artifacts["instructions"],
        artifacts["skill"],
    )


def _review_contract_mode(
    root: Path,
    contract_path: Path,
    task_contract_path: Path | None,
    instructions_path: Path | None,
    skill_path: Path | None,
) -> None:
    """Shared contract-mode review used by `review --contract` and `run`."""
    try:
        engineering_contract = reviewer.load_engineering_contract(
            contract_path
        )
    except reviewer.ContractError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    snapshot = reviewer.contract_to_snapshot(engineering_contract)
    task_contract_obj = None
    if task_contract_path is not None:
        try:
            task_contract_obj = reviewer.load_task_contract(
                task_contract_path
            )
        except reviewer.TaskContractError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        if (
            task_contract_obj.original_request
            != engineering_contract.original_request
        ):
            typer.echo("Task Contract mismatch:", err=True)
            typer.echo(
                "original_request does not match Guard Contract.",
                err=True,
            )
            raise typer.Exit(1)
    exclude_paths: set[Path] = {contract_path}
    if task_contract_path is not None:
        exclude_paths.add(task_contract_path)
    for artifact in (instructions_path, skill_path):
        if artifact is not None:
            if not artifact.is_file():
                typer.echo(
                    f"Error: file not found: {artifact}",
                    err=True,
                )
                raise typer.Exit(1)
            exclude_paths.add(artifact)
    result = reviewer.analyze_diff(
        root,
        exclude_paths=exclude_paths or None,
    )
    amendments = (
        task_contract_obj.scope_amendments
        if task_contract_obj is not None
        else None
    )
    compliance = reviewer.check_plan_compliance(
        snapshot, result, amendments=amendments
    )
    reuse_warnings = reviewer.check_reuse_warnings(
        root, snapshot, result
    )
    if reuse_warnings:
        compliance.reuse_warnings = reuse_warnings
        compliance.risk = reviewer.merge_risk(compliance.risk, "MEDIUM")
    final_risk = reviewer.merge_risk(result.risk, compliance.risk)
    complexity = reviewer.check_complexity(root, engineering_contract, result)
    if complexity.level == "MEDIUM":
        final_risk = reviewer.merge_risk(final_risk, "MEDIUM")
    fidelity = reviewer.check_requirement_fidelity(
        engineering_contract, result
    )
    constraints = reviewer.build_remediation_constraints(
        compliance, reuse_warnings
    )
    extra_reasons: list[str] = []
    if reuse_warnings:
        extra_reasons.extend(reuse_warnings)
    if complexity.level == "MEDIUM":
        extra_reasons.append("complexity signal: MEDIUM")
    if compliance.risk in ("MEDIUM", "HIGH") and compliance.violations:
        extra_reasons.extend(compliance.violations)
    typer.echo(
        reviewer.format_review(
            result,
            risk=final_risk,
            extra_reasons=extra_reasons,
        )
    )
    typer.echo("")
    typer.echo(reviewer.format_plan_compliance(compliance))
    typer.echo("")
    typer.echo(f"Requirement Fidelity: {fidelity}")
    if fidelity == "STRUCTURAL CHECK ONLY":
        typer.echo("No obvious structural conflict found.")
    typer.echo(
        "Semantic correctness is not determined by Project Guard."
    )
    typer.echo("")
    typer.echo(reviewer.format_complexity(complexity, engineering_contract))
    typer.echo("")
    typer.echo(reviewer.format_quality_signals(root, result))
    typer.echo("")
    typer.echo(reviewer.format_remediation_constraints(constraints))


@app.command()
def review(
    path: Path = typer.Argument(".", help="Git project directory"),
    plan: Path | None = typer.Option(
        None,
        "--plan",
        help="Plan snapshot JSON to check diff compliance against",
    ),
    instructions: Path | None = typer.Option(
        None,
        "--instructions",
        help="Agent instructions file to exclude from review diff.",
    ),
    contract: Path | None = typer.Option(
        None,
        "--contract",
        help="Engineering Contract JSON to check the diff against",
    ),
    skill: Path | None = typer.Option(
        None,
        "--skill",
        help="Coding Skill file to exclude from review diff.",
    ),
    task_contract: Path | None = typer.Option(
        None,
        "--task-contract",
        help="Agent-maintained Task Contract JSON with approved scope "
        "amendments",
    ),
):
    """Analyze the current git diff for risk signals."""
    if contract is not None:
        _review_contract_mode(
            path, contract, task_contract, instructions, skill
        )
        return
    snapshot = None
    if plan is not None:
        try:
            snapshot = reviewer.load_plan_snapshot(plan)
        except reviewer.PlanSnapshotError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
    if task_contract is not None:
        typer.echo("Error: --task-contract requires --contract", err=True)
        raise typer.Exit(1)
    exclude_paths: set[Path] = set()
    if plan is not None:
        exclude_paths.add(plan)
    for artifact in (instructions, skill):
        if artifact is not None:
            if not artifact.is_file():
                typer.echo(
                    f"Error: file not found: {artifact}",
                    err=True,
                )
                raise typer.Exit(1)
            exclude_paths.add(artifact)
    try:
        result = reviewer.analyze_diff(
            path,
            exclude_paths=exclude_paths or None,
        )
    except reviewer.NotAGitRepoError as exc:
        typer.echo(f"Error: not a git repository ({exc})", err=True)
        raise typer.Exit(1) from exc
    if snapshot is not None:
        compliance = reviewer.check_plan_compliance(snapshot, result)
        reuse_warnings = reviewer.check_reuse_warnings(
            path, snapshot, result
        )
        if reuse_warnings:
            compliance.reuse_warnings = reuse_warnings
            compliance.risk = reviewer.merge_risk(compliance.risk, "MEDIUM")
        final_risk = reviewer.merge_risk(result.risk, compliance.risk)
        extra_reasons: list[str] = []
        if reuse_warnings:
            extra_reasons.extend(reuse_warnings)
        if compliance.risk in ("MEDIUM", "HIGH") and compliance.violations:
            extra_reasons.extend(compliance.violations)
        typer.echo(
            reviewer.format_review(
                result,
                risk=final_risk,
                extra_reasons=extra_reasons,
            )
        )
        typer.echo("")
        typer.echo(reviewer.format_plan_compliance(compliance))
    else:
        typer.echo(reviewer.format_review(result))


@app.command()
def score(path: Path = typer.Argument(".", help="Project directory")):
    """Print an AI coding readiness score."""
    scan = scanner.scan_project(path)
    diff = None
    try:
        diff = reviewer.analyze_diff(path)
    except (reviewer.NotAGitRepoError, RuntimeError):
        diff = None
    typer.echo(scoring.format_score(scoring.compute_score(scan, diff)))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
