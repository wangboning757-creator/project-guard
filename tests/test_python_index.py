from project_guard.python_index import index_python_file


def test_index_reads_classes_functions_imports(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "import os\n"
        "from .base import LLMProvider\n"
        "\n"
        "class OpenAIProvider(LLMProvider):\n"
        "    pass\n"
        "\n"
        "def create_provider(name):\n"
        "    return name\n",
        encoding="utf-8",
    )
    idx = index_python_file(f, "mod.py")
    assert idx is not None
    assert "OpenAIProvider" in idx.classes
    assert "create_provider" in idx.functions
    assert "os" in idx.imports
    assert "LLMProvider" in idx.imports
    assert "LLMProvider" in idx.bases
    assert idx.top_functions == ["create_provider"]


def test_index_skips_syntax_errors(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text("def broken(:\n", encoding="utf-8")
    assert index_python_file(f, "broken.py") is None
