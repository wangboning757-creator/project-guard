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
    assert paths.index("pkg/base.py") < paths.index("pkg/openai.py")
    assert paths.index("pkg/factory.py") < paths.index("pkg/openai.py")
    assert "provider abstraction" in result.suggestion.lower()


def test_plan_ownership_beats_usage(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "auth.py").write_text(
        "class Auth:\n"
        "    pass\n"
        "\n"
        "class BasicAuth(Auth):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "client.py").write_text(
        "authentication = auth.method()\n" * 60
        + "auth.method()\n" * 40
        + "method = auth.method\n",
        encoding="utf-8",
    )
    result = analyze_plan(
        tmp_path, "Add support for a new authentication method"
    )
    paths = [m.path for m in result.matches]
    assert paths.index("pkg/auth.py") < paths.index("pkg/client.py")


def test_plan_definition_and_ownership_beat_high_frequency_text(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "decoders.py").write_text(
        "class Decoder:\n"
        "    pass\n"
        "\n"
        "class IdentityDecoder(Decoder):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "models.py").write_text(
        "response = 'data'\n" * 100 + "decoder = None\n", encoding="utf-8"
    )
    result = analyze_plan(tmp_path, "Add a new response decoder")
    paths = [m.path for m in result.matches]
    assert paths.index("pkg/decoders.py") < paths.index("pkg/models.py")


def test_plan_cli_entry_point_gets_bonus(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\ndemo = "pkg.main:main"\n', encoding="utf-8"
    )
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "main.py").write_text(
        "def main():\n    timeout = 5\n", encoding="utf-8"
    )
    (pkg / "client.py").write_text(
        "request(timeout=5)\n" * 80, encoding="utf-8"
    )
    (pkg / "config.py").write_text(
        "class TimeoutConfig:\n    pass\n", encoding="utf-8"
    )
    result = analyze_plan(
        tmp_path, "Add a CLI option for request timeout"
    )
    paths = [m.path for m in result.matches]
    assert paths.index("pkg/main.py") < paths.index("pkg/client.py")
    assert paths.index("pkg/main.py") < paths.index("pkg/config.py")
