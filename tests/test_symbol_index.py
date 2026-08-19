import subprocess
from pathlib import Path

from project_guard.models import PlanSnapshot
from project_guard.planner import analyze_plan
from project_guard.reviewer import analyze_diff, check_plan_compliance
from project_guard.scanner import scan_project
from project_guard.symbol_index import index_source_file


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_java_index_extracts_symbols_imports_and_methods(tmp_path):
    path = _write(
        tmp_path / "SearchService.java",
        """package example;
import com.example.data.UserRepository;
interface SearchProvider {}
class SearchService implements SearchProvider {
    public User findUser(String id) { return null; }
}
""",
    )
    index = index_source_file(path, "SearchService.java")
    assert index is not None
    assert index.language == "java"
    assert index.package == "example"
    assert "SearchService" in index.classes
    assert "SearchProvider" in index.bases
    assert "findUser" in index.functions
    assert "com.example.data.UserRepository" in index.imports
    assert "UserRepository" in index.imports


def test_java_index_ignores_comment_and_string_declarations():
    from project_guard.language_index import index_language_source

    index = index_language_source(
        """
        // class FakeProvider implements SearchProvider
        class RealProvider implements SearchProvider {}
        String example = "class DemoProvider implements SearchProvider";
        """,
        "RealProvider.java",
        "java",
    )

    assert index.classes == ["RealProvider"]
    assert index.bases == ["SearchProvider"]


def test_typescript_index_extracts_symbols_imports_and_exports(tmp_path):
    path = _write(
        tmp_path / "UserService.ts",
        """import { Repository } from "./repository";
export class UserService {
    async getUser(id: string) {}
}
""",
    )
    index = index_source_file(path, "UserService.ts")
    assert index is not None
    assert index.language == "typescript"
    assert "UserService" in index.classes
    assert "getUser" in index.functions
    assert "./repository" in index.imports
    assert "Repository" in index.imports
    assert "UserService" in index.exports
    assert "id" in index.identifiers


def test_typescript_index_ignores_comment_and_string_declarations():
    from project_guard.language_index import index_language_source

    index = index_language_source(
        """
        // interface FakeProvider { get(): string }
        export interface RealProvider { get(): string }
        const example = "import { FakeProvider } from './fake'";
        """,
        "provider.ts",
        "typescript",
    )

    assert index.classes == ["RealProvider"]
    assert index.abstract_symbols == ["RealProvider"]
    assert index.imports == []


def test_go_and_rust_indexes_extract_types_methods_and_imports(tmp_path):
    go_path = _write(
        tmp_path / "main.go",
        """package main
import "example/service"
type UserService struct{}
func (s *UserService) GetUser(id string) {}
func main() {}
""",
    )
    rust_path = _write(
        tmp_path / "src" / "main.rs",
        """use crate::repo::Repository;
pub struct UserService {}
impl UserService {
    pub fn get_user(&self, id: &str) {}
}
fn main() {}
""",
    )
    go_index = index_source_file(go_path, "main.go")
    rust_index = index_source_file(rust_path, "src/main.rs")
    assert go_index is not None
    assert "UserService" in go_index.classes
    assert "GetUser" in go_index.functions
    assert "example/service" in go_index.imports
    assert go_index.entry_points == ["main"]
    assert rust_index is not None
    assert "UserService" in rust_index.classes
    assert "get_user" in rust_index.functions
    assert "crate::repo::Repository" in rust_index.imports
    assert rust_index.entry_points == ["main"]


def test_html_index_extracts_resource_references(tmp_path):
    path = _write(
        tmp_path / "login.html",
        """<script src="app.js"></script>
<link href="styles.css">
<form action="/api/users"><input id="login" class="form"></form>
""",
    )
    index = index_source_file(path, "login.html")
    assert index is not None
    assert {"app.js", "styles.css", "/api/users"} <= set(index.references)
    assert "login" in index.references
    assert "form" in index.references


def test_language_indexer_failure_and_large_file_are_safe(tmp_path):
    malformed = _write(tmp_path / "broken.java", "class {\n")
    assert index_source_file(malformed, "broken.java") is not None
    large = _write(tmp_path / "large.ts", "x\n" * 600_000)
    assert index_source_file(large, "large.ts") is None


def test_java_planner_detects_provider_abstraction_and_wiring(tmp_path):
    src = tmp_path / "src" / "main" / "java" / "example"
    _write(src / "SearchProvider.java", "interface SearchProvider {}\n")
    _write(
        src / "GoogleSearchProvider.java",
        "class GoogleSearchProvider implements SearchProvider {}\n",
    )
    _write(
        src / "BingSearchProvider.java",
        "class BingSearchProvider implements SearchProvider {}\n",
    )
    _write(
        src / "ProviderFactory.java",
        "import example.SearchProvider;\nclass ProviderFactory { SearchProvider create() { return null; } }\n",
    )
    result = analyze_plan(tmp_path, "Add another search provider")
    assert result.snapshot is not None
    assert "src/main/java/example/SearchProvider.java" in result.snapshot.recommended_scope
    assert "provider abstraction" in result.suggestion.lower()
    assert any(
        "SearchProvider.java" in fact for fact in result.contract.repository_facts
    )


def test_typescript_planner_detects_provider_abstraction(tmp_path):
    src = tmp_path / "src" / "storage"
    _write(src / "StorageProvider.ts", "export interface StorageProvider {}\n")
    _write(
        src / "LocalStorageProvider.ts",
        "export class LocalStorageProvider implements StorageProvider {}\n",
    )
    _write(
        src / "S3StorageProvider.ts",
        "export class S3StorageProvider implements StorageProvider {}\n",
    )
    _write(
        src / "createStorage.ts",
        "import { StorageProvider } from './StorageProvider';\nexport function createStorage(): StorageProvider { return null; }\n",
    )
    result = analyze_plan(tmp_path, "Add another storage provider")
    assert result.snapshot is not None
    assert "src/storage/StorageProvider.ts" in result.snapshot.recommended_scope
    assert result.duplication_risk


def test_mixed_java_typescript_repository_keeps_both_sides_visible(tmp_path):
    _write(
        tmp_path / "backend" / "src" / "main" / "java" / "example" / "UserService.java",
        "class UserService { User findUser(String id) { return null; } }\n",
    )
    _write(
        tmp_path / "frontend" / "src" / "UserService.ts",
        "export class UserService { getUser(id: string) {} }\n",
    )
    result = analyze_plan(tmp_path, "Add timeout support to UserService")
    paths = {match.path for match in result.matches}
    assert "backend/src/main/java/example/UserService.java" in paths
    assert "frontend/src/UserService.ts" in paths


def test_go_cli_request_surfaces_main_entry_point(tmp_path):
    _write(
        tmp_path / "cmd" / "app" / "main.go",
        "package main\nimport \"example/service\"\nfunc main() {}\n",
    )
    _write(
        tmp_path / "internal" / "service" / "user.go",
        "package service\ntype UserService struct {}\n",
    )
    result = analyze_plan(tmp_path, "Add a CLI option for selecting the backend")
    assert result.snapshot is not None
    assert result.snapshot.recommended_scope == ["cmd/app/main.go"]


def test_reviewer_treats_non_python_production_file_as_scope(tmp_path):
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    java = _write(tmp_path / "src" / "UserService.java", "class UserService {}\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True,
                   capture_output=True, text=True)
    java.write_text("class UserService { void getUser() {} }\n", encoding="utf-8")
    result = analyze_diff(tmp_path)
    assert "src/UserService.java" in result.changed_paths
    assert "src/UserService.java" in result.changed_source_files
    snapshot = PlanSnapshot(
        goal="Add a user service method",
        recommended_scope=["src/UserService.java"],
        possible_scope=[],
        avoid_modifying=[],
        new_dependency="not justified",
        new_abstraction="not justified",
        refactor="not justified",
    )
    compliance = check_plan_compliance(snapshot, result)
    assert compliance.status == "PASS"


def test_scanner_detects_non_python_dependency_manifests(tmp_path):
    _write(
        tmp_path / "pom.xml",
        """<project><dependencies><dependency><groupId>org.example</groupId><artifactId>search</artifactId></dependency></dependencies></project>""",
    )
    _write(
        tmp_path / "build.gradle",
        "implementation('org.example:logging:1.0')\ntestImplementation \"org.example:test:1.0\"\n",
    )
    _write(tmp_path / "go.mod", "module example\n\nrequire example/service v1.0.0\n")
    _write(
        tmp_path / "Cargo.toml",
        "[dependencies]\nserde = \"1\"\n[dev-dependencies]\ninsta = \"1\"\n",
    )
    scan = scan_project(tmp_path)
    sources = {item.source: item.names for item in scan.dependencies}
    assert sources["pom.xml"] == ["org.example:search"]
    assert sources["build.gradle"] == ["org.example:logging:1.0", "org.example:test:1.0"]
    assert sources["go.mod"] == ["example/service"]
    assert set(sources["Cargo.toml"]) == {"serde", "insta"}
