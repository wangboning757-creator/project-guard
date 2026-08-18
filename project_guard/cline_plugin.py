"""Cline CLI project-local Plugin runtime integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cline_integration import ClineIntegrationError, resolve_git_root

PLUGIN_PATH = Path(".cline/plugins/project-guard.js")
PLUGIN_MARKER = "// project-guard-cline-plugin:v1"

# This is intentionally a single-file JavaScript Plugin. It uses only Node's
# standard library so installation does not create an npm project or add a
# second dependency tree to the target repository.
PLUGIN_TEMPLATE = r'''// Project Guard Cline CLI Plugin
// project-guard-cline-plugin:v1
import { execFile } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const PREPARE_TIMEOUT_MS = 30_000;
const GIT_TIMEOUT_MS = 10_000;
const SMOKE_MARKER = ".project-guard-cline-plugin-loaded";
const GOVERNANCE_MESSAGE = `Project Guard prepared the current request.

Before modifying production code:
- read .project-guard-instructions.md
- follow .project-guard-skill.md
- create or update .project-guard-task-contract.json
- request a Scope Amendment before modifying production files outside approved scope
- prefer the Smallest Safe Change and reuse existing capability`;

function latestUserMessage(messages) {
  if (!Array.isArray(messages)) {
    throw new Error("beforeModel request is missing messages");
  }
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!message || message.role !== "user") {
      continue;
    }
    if (!Array.isArray(message.content) || message.content.length !== 1) {
      throw new Error("latest user message is not a single text part");
    }
    const part = message.content[0];
    if (!part || part.type !== "text" || typeof part.text !== "string") {
      throw new Error("latest user message is not a single text part");
    }
    return part.text;
  }
  throw new Error("beforeModel request has no user message");
}

function governanceMessage() {
  return GOVERNANCE_MESSAGE;
}

function shouldPrepare(state, sessionId, prompt) {
  if (state.get(sessionId) === prompt) {
    return false;
  }
  return true;
}

function rememberPrepared(state, sessionId, prompt) {
  state.set(sessionId, prompt);
}

function failureReason(error) {
  const detail = error instanceof Error ? error.message : String(error);
  return `Project Guard preparation failed: ${detail.slice(0, 400)}`;
}

async function resolveGitRoot(workspaceRoot) {
  if (typeof workspaceRoot !== "string" || workspaceRoot.length === 0) {
    throw new Error("Cline workspace root is missing");
  }
  const result = await execFileAsync(
    "git",
    ["-C", workspaceRoot, "rev-parse", "--show-toplevel"],
    {
      cwd: workspaceRoot,
      shell: false,
      timeout: GIT_TIMEOUT_MS,
      maxBuffer: 1024 * 1024,
    },
  );
  const root = result.stdout.trim();
  if (!root) {
    throw new Error("Git did not return a repository root");
  }
  return root;
}

function projectGuardExecutable() {
  const pathValue = process.env.Path ?? process.env.PATH ?? "";
  const names = process.platform === "win32"
    ? ["project-guard.exe", "project-guard"]
    : ["project-guard"];
  for (const directory of pathValue.split(requirePathSeparator())) {
    for (const name of names) {
      const candidate = join(directory, name);
      if (existsSync(candidate)) {
        return candidate;
      }
    }
  }
  return names[0];
}

function requirePathSeparator() {
  return process.platform === "win32" ? ";" : ":";
}

async function prepare(root, prompt) {
  const executable = projectGuardExecutable();
  await execFileAsync(
    executable,
    ["prepare", root, prompt],
    {
      cwd: root,
      shell: false,
      timeout: PREPARE_TIMEOUT_MS,
      maxBuffer: 2 * 1024 * 1024,
    },
  );
}

function writeSmokeMarker(root, sessionId) {
  if (process.env.PROJECT_GUARD_CLINE_PLUGIN_SMOKE !== "1") {
    return;
  }
  writeFileSync(
    join(root, SMOKE_MARKER),
    `Project Guard Cline Plugin loaded for ${sessionId}\n`,
    "utf8",
  );
}

const preparedPrompts = new Map();
let sessionId;
let workspaceRoot;

const plugin = {
  name: "project-guard",
  manifest: {
    capabilities: ["hooks"],
  },
  setup(api, ctx) {
    void api;
    sessionId = ctx?.session?.sessionId;
    workspaceRoot = ctx?.workspaceInfo?.rootPath;
    if (typeof sessionId !== "string" || sessionId.length === 0) {
      throw new Error("Cline sessionId is missing");
    }
    if (typeof workspaceRoot !== "string" || workspaceRoot.length === 0) {
      throw new Error("Cline workspace root is missing");
    }
    writeSmokeMarker(workspaceRoot, sessionId);
  },
  hooks: {
    async beforeModel({ request }) {
      try {
        if (!sessionId || !workspaceRoot) {
          throw new Error("Project Guard Plugin is not initialized");
        }
        const prompt = latestUserMessage(request?.messages);
        const root = await resolveGitRoot(workspaceRoot);
        if (shouldPrepare(preparedPrompts, sessionId, prompt)) {
          await prepare(root, prompt);
          rememberPrepared(preparedPrompts, sessionId, prompt);
        }
        return {
          messages: [
            ...request.messages,
            {
              id: `project_guard_governance_${Date.now()}`,
              role: "user",
              createdAt: Date.now(),
              metadata: { source: "project-guard" },
              content: [{ type: "text", text: governanceMessage() }],
            },
          ],
        };
      } catch (error) {
        return { stop: true, reason: failureReason(error) };
      }
    },
  },
};

export {
  governanceMessage,
  latestUserMessage,
  plugin,
  shouldPrepare,
};
export default plugin;
'''


class ClinePluginIntegrationError(RuntimeError):
    """Raised when the Cline Plugin installation is unsafe."""


@dataclass(frozen=True)
class ClinePluginInstallResult:
    root: Path
    plugin_path: Path
    plugin_changed: bool


def _read_text(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except OSError as exc:
        raise ClinePluginIntegrationError(
            f"cannot read existing Cline Plugin: {path}: {exc}"
        ) from exc


def install_cline_plugin(path: Path) -> ClinePluginInstallResult:
    """Install the dedicated project-local Cline runtime Plugin."""
    try:
        root = resolve_git_root(path)
    except ClineIntegrationError as exc:
        raise ClinePluginIntegrationError(str(exc)) from exc

    plugin_path = root / PLUGIN_PATH
    if plugin_path.exists():
        if _read_text(plugin_path) != PLUGIN_TEMPLATE:
            raise ClinePluginIntegrationError(
                "cannot safely update existing Project Guard Cline Plugin: "
                f"{plugin_path}"
            )
        return ClinePluginInstallResult(root, plugin_path, False)

    try:
        plugin_path.parent.mkdir(parents=True, exist_ok=True)
        plugin_path.write_text(PLUGIN_TEMPLATE, encoding="utf-8", newline="")
    except OSError as exc:
        raise ClinePluginIntegrationError(
            f"cannot write Project Guard Cline Plugin: {plugin_path}: {exc}"
        ) from exc
    return ClinePluginInstallResult(root, plugin_path, True)
