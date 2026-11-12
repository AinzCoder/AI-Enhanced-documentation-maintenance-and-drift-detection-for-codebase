import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from git import Repo

from analyzer.java_analyzer import source_line_range, source_line_starts
from rag import embedding_generator


def test_byte_offsets_preserve_line_ranges_without_tree_sitter_points():
    source = "é\r\nvoid x() {\r\n}\r\n".encode("utf-8")
    starts = source_line_starts(source)
    node = SimpleNamespace(start_byte=4, end_byte=len(source))
    assert source_line_range(node, starts) == (2, 3)


def test_embedding_model_loaded_once_for_concurrent_requests(monkeypatch):
    calls = []

    class FakeModel:
        def encode(self, text, normalize_embeddings):
            assert normalize_embeddings
            return SimpleNamespace(tolist=lambda: [len(text)])

    def create_model():
        calls.append(True)
        return FakeModel()

    monkeypatch.setattr(embedding_generator, "model", None)
    monkeypatch.setattr(embedding_generator, "_create_model", create_model)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(embedding_generator.generate_embedding, ["a", "bb", "ccc", "dddd"]))
    assert results == [[1], [2], [3], [4]]
    assert len(calls) == 1


def test_repeated_analysis_in_subprocess_needs_no_llm_or_rag(tmp_path):
    repo = Repo.init(tmp_path)
    with repo.config_writer() as config:
        config.set_value("user", "name", "DocGuard Test")
        config.set_value("user", "email", "docguard@example.test")
    source = tmp_path / "Example.java"
    methods = [
        f"    public int method{i}(int value) {{\n"
        f"        // method {i}\n"
        f"        return value + {i};\n"
        "    }\n"
        for i in range(75)
    ]
    source.write_text("class Example {\n" + "".join(methods) + "}\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")
    repo.git.add(A=True)
    repo.index.commit("initial")
    source.write_text(source.read_text(encoding="utf-8").replace("return value + 1;", "return value + 101;"), encoding="utf-8")

    script = """
import sys
import requests
from fastapi.testclient import TestClient
from app import main
from rag import embedding_generator

def unexpected(*args, **kwargs):
    raise AssertionError("ordinary analysis invoked an external service or RAG")

requests.post = unexpected
main.index_repository_documentation = unexpected
main.generate_update_for_change = unexpected
main.list_audit_records = unexpected
embedding_generator.generate_embedding = unexpected
assert embedding_generator.model is None
assert "sentence_transformers" not in sys.modules
client = TestClient(main.app)
path = sys.argv[1]
for _ in range(5):
    full = client.post("/analyze/full", json={"repository_path": path})
    assert full.status_code == 200, full.text
    data = full.json()
    assert data["summary"]["method_count"] == 75
    assert data["documentation_analysis"]["summary"]["method_count"] == 75
    methods = data["files"][0]["classes"][0]["methods"]
    last_method = next(method for method in methods if method["name"] == "method74")
    assert (last_method["start_line"], last_method["end_line"]) == (298, 301)
    assert not data["errors"]
    git = client.post("/analyze", json={"repository_path": path})
    assert git.status_code == 200, git.text
    assert len(git.json()["results"]) == 1
    assert not git.json()["results"][0].get("errors")
assert embedding_generator.model is None
assert "sentence_transformers" not in sys.modules
"""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=120,
        env=environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
