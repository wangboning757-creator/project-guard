import re

from project_guard.models import PlanSnapshot
from project_guard.planner import analyze_plan


def _section(text: str, header: str) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == header:
            out = []
            for ln in lines[i + 1:]:
                if re.match(r"^[A-Z][A-Za-z ]*:$", ln.strip()):
                    break
                out.append(ln)
            return "\n".join(out).strip()
    return ""


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
    assert not result.duplication_risk
    assert "csv_exporter.py" in result.suggestion


def test_plan_no_match_suggests_new_module(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    result = analyze_plan(tmp_path, "Add PDF export")
    assert result.matches == []
    assert not result.duplication_risk
    assert "new module" in result.suggestion


def test_plan_ignores_project_guard_artifacts(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "SearchProvider.java").write_text(
        "interface SearchProvider {}\n", encoding="utf-8"
    )
    (src / "GoogleSearchProvider.java").write_text(
        "class GoogleSearchProvider implements SearchProvider {}\n",
        encoding="utf-8",
    )
    (src / "ProviderFactory.java").write_text(
        "class ProviderFactory { SearchProvider create() { return null; } }\n",
        encoding="utf-8",
    )
    for name in (
        ".project-guard-plan.json",
        ".project-guard-contract.json",
        ".project-guard-instructions.md",
        ".project-guard-skill.md",
        ".project-guard-agent-prompt.md",
        ".project-guard-task-contract.json",
    ):
        (tmp_path / name).write_text(
            "SearchProvider GoogleSearchProvider ProviderFactory\n",
            encoding="utf-8",
        )
    plugin = tmp_path / ".cline" / "plugins"
    plugin.mkdir(parents=True)
    (plugin / "project-guard.js").write_text(
        "SearchProvider GoogleSearchProvider ProviderFactory\n",
        encoding="utf-8",
    )

    result = analyze_plan(tmp_path, "Add another search provider")
    paths = [match.path for match in result.matches]
    guardrail = result.guardrail

    assert {"src/SearchProvider.java", "src/GoogleSearchProvider.java"} <= set(
        paths
    )
    assert "src/ProviderFactory.java" in paths or "ProviderFactory" in guardrail
    assert not any(path.startswith(".project-guard-") for path in paths)
    assert ".cline/plugins/project-guard.js" not in paths
    assert ".project-guard-" not in guardrail
    assert ".cline/plugins/project-guard.js" not in guardrail


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


def test_plan_guardrail_prefers_local_change(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "writer.py").write_text(
        "class ReportWriter:\n"
        "    def write_report(self):\n"
        "        return 'md'\n",
        encoding="utf-8",
    )
    (pkg / "storage.py").write_text(
        "report = store(rows)\n" * 40, encoding="utf-8"
    )
    (pkg / "workflow.py").write_text(
        "report = process(steps)\n" * 40, encoding="utf-8"
    )
    result = analyze_plan(tmp_path, "Add CSV report export")
    g = result.guardrail
    scope = _section(g, "Recommended change scope:")
    assert "pkg/writer.py" in scope
    assert "pkg/storage.py" not in scope
    assert "pkg/workflow.py" not in scope
    assert _section(g, "New dependency:") == "not justified"
    assert _section(g, "New abstraction:") == "not justified"
    assert _section(g, "Refactor:") == "not justified"


def test_plan_guardrail_reuses_provider_abstraction(tmp_path):
    result = analyze_plan(
        _make_provider_repo(tmp_path), "Add another LLM vendor"
    )
    g = result.guardrail
    scope = _section(g, "Recommended change scope:")
    assert "pkg/base.py" in scope
    assert "pkg/factory.py" in scope
    assert "pkg/openai.py" not in scope
    assert "pkg/deepseek.py" not in scope
    assert "new provider module" in scope
    reuse = _section(g, "Existing capability to reuse:")
    assert "abstraction" in reuse
    assert "pkg/base.py" in reuse
    assert _section(g, "New abstraction:") == "reuse existing abstraction"


def test_plan_guardrail_ownership_over_usage(tmp_path):
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
        "response = decode(raw)\n" * 60, encoding="utf-8"
    )
    (pkg / "transport.py").write_text(
        "response = transport.decode(data)\n" * 60, encoding="utf-8"
    )
    result = analyze_plan(tmp_path, "Add a new response decoder")
    g = result.guardrail
    scope = _section(g, "Recommended change scope:")
    assert "pkg/decoders.py" in scope
    assert "pkg/transport.py" not in scope
    assert "pkg/models.py" not in scope
    avoid = _section(g, "Avoid modifying:")
    assert "pkg/transport.py" in avoid
    assert _section(g, "New dependency:") == "not justified"
    assert _section(g, "Refactor:") == "not justified"


def test_plan_guardrail_multi_role_writer_has_no_strong_signal(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "writer.py").write_text(
        "# markdown report export helpers\n"
        "def render_markdown(text):\n"
        "    return 'md'\n"
        "\n"
        "def send_email(to, body):\n"
        "    return True\n"
        "\n"
        "def save_database(row):\n"
        "    return True\n"
        "\n"
        "def upload_s3(blob):\n"
        "    return True\n",
        encoding="utf-8",
    )
    result = analyze_plan(tmp_path, "Add PDF report export")
    g = result.guardrail
    assert _section(g, "Refactor:") == "no strong signal"
    assert _section(g, "New dependency:") == "not justified"


def test_plan_snapshot_round_trip(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "decoders.py").write_text(
        "class Decoder:\n    pass\n", encoding="utf-8"
    )
    (pkg / "client.py").write_text(
        "from .decoders import Decoder\n\n" + "decoder = Decoder()\n" * 30,
        encoding="utf-8",
    )
    (pkg / "storage.py").write_text(
        "response = store(decoder)\n" * 30, encoding="utf-8"
    )
    result = analyze_plan(tmp_path, "Add a new response decoder")
    snap = result.snapshot
    assert snap is not None
    assert snap.goal == "Add a new response decoder"
    assert snap.recommended_scope == ["pkg/decoders.py"]
    assert "pkg/client.py" in snap.possible_scope
    assert "pkg/storage.py" in snap.avoid_modifying
    assert snap.new_dependency == "not justified"
    loaded = PlanSnapshot.model_validate_json(snap.model_dump_json())
    assert loaded == snap


def test_plan_guardrail_includes_execution_integration_points(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "writer.py").write_text(
        "def render_report(topic):\n    return 'md'\n", encoding="utf-8"
    )
    (pkg / "workflow.py").write_text(
        "from .writer import render_report\n\n"
        "def run():\n    return render_report('x')\n",
        encoding="utf-8",
    )
    (pkg / "cli.py").write_text(
        "from .writer import render_report\n\n"
        "def resume():\n    return render_report('y')\n",
        encoding="utf-8",
    )
    (pkg / "storage.py").write_text(
        "report = store_metadata()\n" * 30, encoding="utf-8"
    )
    result = analyze_plan(tmp_path, "Add optional plain-text report export")
    snap = result.snapshot
    assert snap is not None
    assert snap.recommended_scope == ["pkg/writer.py"]
    assert "pkg/workflow.py" in snap.possible_scope
    assert "pkg/cli.py" in snap.possible_scope
    assert "pkg/storage.py" not in snap.possible_scope
    assert "pkg/storage.py" not in snap.recommended_scope


def _make_search_provider_repo(tmp_path):
    search = tmp_path / "pkg" / "search"
    search.mkdir(parents=True)
    (search / "base.py").write_text(
        "class SearchProvider:\n"
        '    """Fetches sources for research."""\n'
        "    def search(self, query):\n"
        "        return []\n",
        encoding="utf-8",
    )
    (search / "google.py").write_text(
        "from .base import SearchProvider\n\n"
        "class GoogleProvider(SearchProvider):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (search / "bing.py").write_text(
        "from .base import SearchProvider\n\n"
        "class BingProvider(SearchProvider):\n"
        "    pass\n",
        encoding="utf-8",
    )
    pkg = tmp_path / "pkg"
    (pkg / "cli.py").write_text(
        "import typer\n\n"
        "def main():\n"
        "    typer.run(research)\n\n"
        "def research(sources):\n"
        "    return sources\n",
        encoding="utf-8",
    )
    (pkg / "workflow.py").write_text(
        "def run_research(sources):\n"
        "    return sources\n",
        encoding="utf-8",
    )
    (pkg / "settings.py").write_text(
        "class Settings:\n"
        "    max_sources: int = 10\n",
        encoding="utf-8",
    )
    return tmp_path


def test_plan_parameter_change_does_not_trigger_provider(tmp_path):
    result = analyze_plan(
        _make_search_provider_repo(tmp_path),
        "Add a CLI option to limit the maximum number of sources used in "
        "a research run",
    )
    snap = result.snapshot
    assert snap is not None
    assert snap.recommended_scope == ["pkg/cli.py"]
    assert "pkg/workflow.py" in snap.possible_scope
    assert "pkg/search/base.py" not in snap.recommended_scope
    assert "pkg/search/base.py" not in snap.possible_scope
    scope_text = _section(result.guardrail, "Recommended change scope:")
    assert "new provider module" not in scope_text
    assert "provider abstraction" not in result.suggestion.lower()
    assert "pkg/workflow.py" not in snap.avoid_modifying
    assert not result.duplication_risk


def test_plan_provider_expansion_still_works(tmp_path):
    result = analyze_plan(
        _make_search_provider_repo(tmp_path),
        "Add support for another search provider",
    )
    snap = result.snapshot
    assert snap is not None
    assert "pkg/search/base.py" in snap.recommended_scope
    assert "new provider module" in _section(
        result.guardrail, "Recommended change scope:"
    )
    assert "provider abstraction" in result.suggestion.lower()
    assert "abstraction" in _section(result.guardrail, "Existing capability to reuse:")
    assert _section(result.guardrail, "New abstraction:") == "reuse existing abstraction"


def test_plan_cli_parameter_change_prefers_cli(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "cli.py").write_text(
        "import typer\n\n"
        "def main():\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "workflow.py").write_text(
        "def run(request, timeout):\n"
        "    return request\n",
        encoding="utf-8",
    )
    (pkg / "config.py").write_text(
        "class TimeoutConfig:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "models.py").write_text(
        "request = make_request()\n" * 40, encoding="utf-8"
    )
    result = analyze_plan(tmp_path, "Add a CLI option for request timeout")
    snap = result.snapshot
    assert snap is not None
    assert snap.recommended_scope == ["pkg/cli.py"]
    assert "pkg/config.py" in snap.possible_scope
    assert "pkg/models.py" not in snap.recommended_scope
    assert "pkg/models.py" not in snap.possible_scope
    assert "provider abstraction" not in result.suggestion.lower()


def test_plan_generic_limit_ignores_provider_pattern(tmp_path):
    pkg = tmp_path / "pkg"
    search = pkg / "search"
    search.mkdir(parents=True)
    (search / "base.py").write_text(
        "class SearchProvider:\n"
        '    """Search provider that gathers sources."""\n'
        "    def search(self):\n"
        "        return []\n",
        encoding="utf-8",
    )
    (search / "foo.py").write_text(
        "from .base import SearchProvider\n\n"
        "class FooProvider(SearchProvider):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (search / "bar.py").write_text(
        "from .base import SearchProvider\n\n"
        "class BarProvider(SearchProvider):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (pkg / "workflow.py").write_text(
        "def run_research(sources):\n"
        "    return sources\n",
        encoding="utf-8",
    )
    (pkg / "settings.py").write_text(
        "def max_sources():\n"
        "    return 10\n",
        encoding="utf-8",
    )
    result = analyze_plan(
        tmp_path,
        "Limit the maximum number of sources per research run",
    )
    snap = result.snapshot
    assert snap is not None
    assert "pkg/search/base.py" not in snap.recommended_scope
    assert "new provider module" not in _section(
        result.guardrail, "Recommended change scope:"
    )
    assert "provider abstraction" not in result.suggestion.lower()
    paths = [m.path for m in result.matches]
    assert paths.index("pkg/workflow.py") < paths.index("pkg/search/base.py")
    assert paths.index("pkg/settings.py") < paths.index("pkg/search/base.py")


def test_plan_avoid_excludes_direct_capability_file(tmp_path):
    pkg = tmp_path / "pkg"
    search = pkg / "search"
    search.mkdir(parents=True)
    (search / "tavily.py").write_text(
        "class TavilySearchProvider:\n"
        "    def __init__(self, include_domains=(), exclude_domains=()):\n"
        "        self.include_domains = include_domains\n"
        "        self.exclude_domains = exclude_domains\n"
        "    def search(self, query):\n"
        "        payload = {}\n"
        "        if self.exclude_domains:\n"
        "            payload['exclude_domains'] = list(self.exclude_domains)\n"
        "        return payload\n",
        encoding="utf-8",
    )
    (search / "base.py").write_text(
        "class SearchProvider:\n"
        "    def search(self):\n"
        "        return {}\n",
        encoding="utf-8",
    )
    (pkg / "cli.py").write_text(
        "import typer\n\n"
        "def main():\n"
        "    typer.run(research)\n\n"
        "def research(domains):\n"
        "    return domains\n",
        encoding="utf-8",
    )
    (pkg / "workflow.py").write_text(
        "def run_research(domains):\n"
        "    return domains\n",
        encoding="utf-8",
    )
    result = analyze_plan(
        tmp_path,
        "Add an option to exclude one or more domains from research "
        "search results",
    )
    snap = result.snapshot
    assert snap is not None
    assert snap.recommended_scope == ["pkg/cli.py"]
    assert "pkg/search/tavily.py" not in snap.avoid_modifying
    assert "pkg/search/tavily.py" in snap.existing_capability_files
    assert "provider abstraction" not in result.suggestion.lower()


def _make_reuse_repo(tmp_path):
    src = tmp_path / "src" / "sample_app"
    search = src / "search"
    search.mkdir(parents=True)
    (search / "tavily.py").write_text(
        "class TavilySearchProvider:\n"
        "    def __init__(self, exclude_domains=()):\n"
        "        self.exclude_domains = exclude_domains\n"
        "    def search(self, query):\n"
        "        payload = {}\n"
        "        if self.exclude_domains:\n"
        "            payload['exclude_domains'] = list(self.exclude_domains)\n"
        "        return payload\n",
        encoding="utf-8",
    )
    (src / "factory.py").write_text(
        "from .search.tavily import TavilySearchProvider\n\n"
        "def create_search_provider(exclude_domains=()):\n"
        "    return TavilySearchProvider(exclude_domains=exclude_domains)\n",
        encoding="utf-8",
    )
    (src / "settings.py").write_text(
        "class Settings:\n"
        "    def domain_config(self):\n"
        "        return {}\n",
        encoding="utf-8",
    )
    (src / "cli.py").write_text(
        "import typer\n\n"
        "def main():\n"
        "    typer.run(research)\n\n"
        "def research(domains):\n"
        "    return domains\n",
        encoding="utf-8",
    )
    return tmp_path


REUSE_TAVILY_GOAL = (
    "Reuse the existing Tavily exclude_domains capability for the CLI "
    "domain-exclusion option instead of client-side filtering"
)


def test_plan_reuse_finds_wiring_point(tmp_path):
    result = analyze_plan(
        _make_reuse_repo(tmp_path),
        REUSE_TAVILY_GOAL,
    )
    snap = result.snapshot
    assert snap is not None
    assert snap.recommended_scope == ["src/sample_app/cli.py"]
    assert "src/sample_app/factory.py" in snap.possible_scope
    assert "src/sample_app/search/tavily.py" not in snap.avoid_modifying
    assert "src/sample_app/settings.py" not in snap.possible_scope
    assert "src/sample_app/search/tavily.py" in snap.existing_capability_files
    assert (
        "Existing capability in src/sample_app/search/tavily.py"
        in result.guardrail
    )


def test_engineering_contract_builder(tmp_path):
    result = analyze_plan(_make_reuse_repo(tmp_path), REUSE_TAVILY_GOAL)
    contract = result.contract
    assert contract is not None
    assert contract.original_request == REUSE_TAVILY_GOAL
    assert contract.explicit_requirements == [REUSE_TAVILY_GOAL]
    assert contract.inferred_requirements
    assert set(contract.explicit_requirements).isdisjoint(
        contract.inferred_requirements
    )
    assert contract.recommended_scope == ["src/sample_app/cli.py"]
    assert "src/sample_app/factory.py" in contract.possible_scope
    assert (
        "src/sample_app/search/tavily.py"
        in contract.existing_capability_files
    )
    assert (
        contract.complexity_budget.preferred_max_touched_production_files
        == 3
    )
    assert any("CLI entry point" in f for f in contract.repository_facts)
    assert any(
        "Existing capability detected" in f
        for f in contract.repository_facts
    )
    assert any(
        "Provider construction detected" in f
        for f in contract.repository_facts
    )
    assert contract.assumptions == []
    assert contract.unresolved_questions == []
    assert contract.testing_policy
