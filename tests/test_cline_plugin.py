import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from project_guard.cli import app
from project_guard.cline_plugin import PLUGIN_MARKER, PLUGIN_PATH

runner = CliRunner()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "main.py").write_text("print(1)\n", encoding="utf-8")
    return repo


def test_init_cline_plugin_installs_project_local_plugin(tmp_path):
    repo = _repo(tmp_path)

    result = runner.invoke(app, ["init-cline-plugin", str(repo)])

    plugin = repo / PLUGIN_PATH
    assert result.exit_code == 0
    assert plugin.is_file()
    content = plugin.read_text(encoding="utf-8")
    assert PLUGIN_MARKER in content
    assert 'name: "project-guard"' in content
    assert 'capabilities: ["hooks"]' in content
    assert "beforeModel" in content
    assert "stop: true" in content
    assert "ctx?.workspaceInfo?.rootPath" in content
    assert "ctx?.session?.sessionId" in content


def test_init_cline_plugin_is_idempotent(tmp_path):
    repo = _repo(tmp_path)

    first = runner.invoke(app, ["init-cline-plugin", str(repo)])
    plugin = repo / PLUGIN_PATH
    original = plugin.read_text(encoding="utf-8")
    second = runner.invoke(app, ["init-cline-plugin", str(repo)])

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert plugin.read_text(encoding="utf-8") == original
    assert "already present" in second.output


def test_init_cline_plugin_preserves_existing_file_hook(tmp_path):
    repo = _repo(tmp_path)
    hook = repo / ".cline" / "hooks" / "UserPromptSubmit.ps1"
    hook.parent.mkdir(parents=True)
    original = "Write-Output 'existing hook'\n"
    hook.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-cline-plugin", str(repo)])

    assert result.exit_code == 0
    assert hook.read_text(encoding="utf-8") == original


def test_init_cline_plugin_rejects_unknown_existing_plugin(tmp_path):
    repo = _repo(tmp_path)
    plugin = repo / PLUGIN_PATH
    plugin.parent.mkdir(parents=True)
    original = "export default { name: 'user-plugin' };\n"
    plugin.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-cline-plugin", str(repo)])

    assert result.exit_code == 1
    assert "cannot safely update existing Project Guard Cline Plugin" in result.output
    assert plugin.read_text(encoding="utf-8") == original


def test_init_cline_plugin_rejects_malformed_owned_path_without_overwrite(
    tmp_path,
):
    repo = _repo(tmp_path)
    plugin = repo / PLUGIN_PATH
    plugin.parent.mkdir(parents=True)
    original = "// project-guard-cline-plugin:v1\nnot valid JavaScript\n"
    plugin.write_text(original, encoding="utf-8")

    result = runner.invoke(app, ["init-cline-plugin", str(repo)])

    assert result.exit_code == 1
    assert plugin.read_text(encoding="utf-8") == original


def test_cline_plugin_helpers_preserve_latest_text_and_dedupe(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("Node.js is not installed")
    repo = _repo(tmp_path)
    result = runner.invoke(app, ["init-cline-plugin", str(repo)])
    assert result.exit_code == 0
    plugin = repo / PLUGIN_PATH
    script = r'''
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
const pluginPath = process.argv[1];
const { latestUserMessage, governanceMessage, shouldPrepare } =
  await import(pathToFileURL(pluginPath));
const prompt = "  Keep exact whitespace & symbols.  ";
assert.equal(
  latestUserMessage([
    { role: "user", content: [{ type: "text", text: "old" }] },
    { role: "assistant", content: [{ type: "text", text: "answer" }] },
    { role: "user", content: [{ type: "text", text: prompt }] },
  ]),
  prompt,
);
assert.throws(() => latestUserMessage([
  { role: "user", content: [{ type: "text", text: "a" }, { type: "text", text: "b" }] },
]));
const state = new Map([["session-1", prompt]]);
assert.equal(shouldPrepare(state, "session-1", prompt), false);
assert.equal(shouldPrepare(state, "session-1", "new"), true);
const context = governanceMessage();
assert.match(context, /\.project-guard-instructions\.md/);
assert.match(context, /\.project-guard-skill\.md/);
assert.match(context, /\.project-guard-task-contract\.json/);
assert.ok(!context.includes("Requirement Fidelity"));
console.log(JSON.stringify({ ok: true }));
'''
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(plugin)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"ok": True}


def test_cline_plugin_node_syntax_check(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("Node.js is not installed")
    repo = _repo(tmp_path)
    result = runner.invoke(app, ["init-cline-plugin", str(repo)])
    assert result.exit_code == 0
    completed = subprocess.run(
        ["node", "--check", str(repo / PLUGIN_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
