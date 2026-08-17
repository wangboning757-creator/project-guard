# Project Guard Release Checklist

用于形成一个较完整版本时的发布前检查。小改动可以先在本地累积，不需要每个小修复都立即 push。

1. 确认目标版本内容已经完成，且没有未预期的工作区文件。
2. 同步以下源码版本：
   - `pyproject.toml` 的 `project.version`
   - `project_guard/__init__.py` 的 `__version__`
3. 安装项目和开发依赖：

   ```powershell
   python -m pip install -e ".[dev]"
   ```

   `project_guard.egg-info/` 是生成 artifact，不是版本源码来源；安装过程会刷新它。

4. 执行发布质量门槛：

   ```powershell
   python -m ruff check .
   python -m pytest
   git diff --check
   ```

5. 检查 README 的版本和支持状态，必要时确认真人 dogfood 结果。
6. 再次检查 `git status` 和最终 diff。
7. 在用户明确决定发布后再 commit。
8. push 和 tag 应在最终发布 commit 确认后执行；tag 必须指向该 commit。

Project Guard 不自动执行 commit、push 或 tag。
