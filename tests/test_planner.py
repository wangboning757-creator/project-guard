from project_guard.planner import analyze_plan


def test_plan_finds_existing_feature(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "csv_exporter.py").write_text(
        "def export_csv(data):\n    return data\n" * 3, encoding="utf-8"
    )
    result = analyze_plan(tmp_path, "Add CSV export")
    assert "csv" in result.keywords
    assert any(
        m.path.endswith("csv_exporter.py") for m in result.matches
    )
    assert result.duplication_risk
    assert "csv_exporter.py" in result.suggestion


def test_plan_no_match_suggests_new_module(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    result = analyze_plan(tmp_path, "Add PDF export")
    assert result.matches == []
    assert not result.duplication_risk
    assert "new module" in result.suggestion


def test_plan_test_mentions_are_not_treated_as_feature(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text(
        "Add PDF export\n", encoding="utf-8"
    )
    result = analyze_plan(tmp_path, "Add PDF export")
    assert result.matches
    assert not result.duplication_risk
    assert "tests/docs" in result.suggestion


def _make_provider_repo(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from .base import LLMProvider\n", encoding="utf-8"
    )
    (pkg / "base.py").write_text(
        "class LLMProvider:\n"
        "    def generate(self):\n"
        "        raise NotImplementedError\n",
        encoding="utf-8",
    )
    (pkg / "openai.py").write_text(
        "from .base import LLMProvider\n\n"
        "class OpenAIProvider(LLMProvider):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "deepseek.py").write_text(
        "from .base import LLMProvider\n\n"
        "class DeepSeekProvider(LLMProvider):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "factory.py").write_text(
        "def create_llm_provider(name):\n"
        "    return name\n",
        encoding="utf-8",
    )
    return tmp_path


def test_plan_prefers_provider_abstraction_over_smallest_file(tmp_path):
    result = analyze_plan(
        _make_provider_repo(tmp_path), "Add another LLM vendor"
    )
    paths = [m.path for m in result.matches]
    assert paths.index("pkg/base.py") < paths.index("pkg/__init__.py")
    assert paths.index("pkg/factory.py") < paths.index("pkg/__init__.py")
    assert "provider abstraction" in result.suggestion.lower()
