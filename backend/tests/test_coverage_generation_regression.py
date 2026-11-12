import pytest
from fastapi.testclient import TestClient

from analyzer.repository_analyzer import analyze_full_repository
from app import main as app_module
from approval.generation_markdown import merge_generated_documentation
from documentation_analysis.documentation_coverage import analyze_documentation_coverage
from documentation_generation import full_documentation_generator as generator


def write(root, path, text):
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def coverage(root):
    analysis = analyze_full_repository(str(root))
    return analyze_documentation_coverage(str(root), analysis)


def test_approved_overview_class_heading_is_recognized(tmp_path):
    write(tmp_path, "src/Order.java",
          "package demo; class Order { int getId() { return 1; } }\n")
    record = {
        "repository_overview": "### Order Management\n\n#### demo.Order\nOverview.",
        "generated_classes": [{
            "class": "Order", "package": "demo", "source_file": "src/Order.java",
            "identity": "demo.Order — src/Order.java", "description": "Order.",
        }],
        "generated_methods": [{
            "class": "Order", "package": "demo", "source_file": "src/Order.java",
            "signature": "getId()", "documentation": "Returns the identifier.",
        }],
    }
    merged = merge_generated_documentation("# API\n", record)
    write(tmp_path, "docs/API.md", merged)

    assert "##### getId()" in merged
    assert coverage(tmp_path)["summary"]["documented_method_count"] == 1


def test_qualified_method_heading_requires_correct_class(tmp_path):
    write(tmp_path, "src/A.java", "class A { int find(String id) { return 1; } }\n")
    write(tmp_path, "API.md", "## A\n### A.find(String id)\n")
    assert coverage(tmp_path)["summary"]["documented_method_count"] == 1
    write(tmp_path, "API.md", "## A\n### Other.find(String id)\n")
    assert coverage(tmp_path)["summary"]["documented_method_count"] == 0


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("find(String id)", "documented"),
        ("A.find(String id)", "documented"),
        ("find(String)", "documented"),
        ("find(id)", "missing"),
        ("Other.find(String id)", "missing"),
    ],
)
def test_overloads_require_the_correct_parameter_types(tmp_path, heading, expected):
    write(tmp_path, "A.java", (
        "class A { void find(String id) {} void find(int id) {} }\n"
    ))
    write(tmp_path, "API.md", f"## A\n### {heading}\n")
    methods = coverage(tmp_path)["classes"][0]["methods"]
    by_signature = {method["signature"]: method["coverage"] for method in methods}
    assert by_signature["find(String)"] == expected
    assert by_signature["find(int)"] == "missing"


def test_bare_overloaded_method_and_duplicate_headings_are_ambiguous(tmp_path):
    write(tmp_path, "A.java", "class A { void find(int id) {} void find(String id) {} }")
    write(tmp_path, "API.md", "## A\n### find\n")
    assert coverage(tmp_path)["summary"]["ambiguous_method_count"] == 2
    write(tmp_path, "API.md", "## A\n### find(int)\n### find(int id)\n")
    assert coverage(tmp_path)["summary"]["ambiguous_method_count"] == 1


def test_type_normalization_and_identifiers_with_underscores(tmp_path):
    write(tmp_path, "A.java", (
        "class A { void find_items(java.util.List<String> values, String... names) {} }"
    ))
    write(tmp_path, "API.md", (
        "## A\n### `find_items(java.util.List< String > values, String[] names)`\n"
    ))
    assert coverage(tmp_path)["summary"]["documented_method_count"] == 1


def test_prose_unknown_nested_class_and_distinct_files_do_not_count(tmp_path):
    write(tmp_path, "src/A.java", "class A { void run() {} }")
    write(tmp_path, "src/nested/B.java", "class B { void run() {} }")
    write(tmp_path, "API.md", (
        "## A\nThe run method is useful.\n### Other\n#### run()\n"
        "## B\n### run()\n"
    ))
    result = coverage(tmp_path)
    assert [(item["class"], item["methods"][0]["coverage"])
            for item in result["classes"]] == [("A", "missing"), ("B", "documented")]


def test_duplicate_qualified_class_names_require_file_identity(tmp_path):
    write(tmp_path, "one/A.java", "package demo; class A { void run() {} }")
    write(tmp_path, "two/A.java", "package demo; class A { void run() {} }")
    write(tmp_path, "API.md", "## demo.A\n### run()\n")
    result = coverage(tmp_path)
    assert result["summary"]["ambiguous_method_count"] == 2
    assert result["summary"]["documented_method_count"] == 0


def test_method_only_approval_reuses_qualified_class_and_not_nested_other(tmp_path):
    write(tmp_path, "A.java", "package demo; class A { void run() {} }")
    record = {
        "generated_classes": [],
        "generated_methods": [{
            "class": "A", "package": "demo", "source_file": "A.java",
            "signature": "run()", "documentation": "Runs."
        }]
    }
    original = "## demo.A\n### Other\n#### run()\nUnrelated.\n"
    merged = merge_generated_documentation(original, record)
    write(tmp_path, "API.md", merged)
    assert merged.count("## demo.A") == 1
    assert "### run()" in merged
    assert "#### run()\nUnrelated." in merged
    assert coverage(tmp_path)["summary"]["documented_method_count"] == 1


def test_generation_approval_and_reanalysis_keep_unrelated_coverage(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    write(root, "src/OrderService.java", (
        "package demo;\nclass OrderService {"
        " int findOrder(String id) { return 1; }"
        " int getOrder() { return 1; }"
        " void placeOrder() {} }\n"
    ))
    write(root, "src/nested/UserService.java", (
        "package demo;\nclass UserService {"
        " void addUser() {} void removeUser() {} void findUser() {} }\n"
    ))
    write(root, "docs/API.md", (
        "# API Documentation\n## OrderService\n### getOrder()\nExisting.\n"
        "## UserService\n"
    ))
    write(root, "README.md", "# Project\n")
    monkeypatch.setattr(app_module, "GENERATION_STORE_PATH", tmp_path / "store.sqlite3")
    monkeypatch.setattr(generator, "index_repository_documentation", lambda _: {
        "indexed_files": [], "skipped_files": [], "deleted_files": [],
        "indexed_chunks": 0, "errors": []
    })
    monkeypatch.setattr(generator, "retrieve_repository_context", lambda *args, **kwargs: {
        "documents": [], "metadatas": [], "distances": [],
        "available": True, "error": None
    })

    def model(prompt):
        if "repository overview" in prompt:
            return "# Overview\n## demo.OrderService\nA source-backed service."
        return (
            "**Purpose and behavior**\nReturns a value.\n\n"
            "**Parameters**\n- id: identifier.\n\n**Returns**\n- An integer.\n\n"
            "**Behavior**\nReturns the value."
        )

    monkeypatch.setattr(generator, "generate_response", model)
    with TestClient(app_module.app) as client:
        before = client.post("/analyze/full", json={"repository_path": str(root)}).json()
        assert before["summary"]["java_file_count"] == 2
        assert before["summary"]["method_count"] == 6
        before_coverage = before["documentation_analysis"]
        assert before_coverage["summary"]["documented_method_count"] == 1
        target_before = (root / "docs" / "API.md").read_bytes()
        sources_before = {
            path: path.read_bytes() for path in root.rglob("*")
            if path.is_file() and path.name != "API.md"
        }

        response = client.post("/documentation/generate/full", json={
            "repository_path": str(root), "target_documentation_file": "docs/API.md",
            "max_methods": 1, "include_repository_overview": True
        })
        assert response.status_code == 200, response.text
        preview = response.json()
        assert preview["generation_status"] == "partial"
        assert [m["signature"] for m in preview["generated_methods"]] == [
            "findOrder(String)"
        ]
        assert "#### findOrder(String)" in preview["generated_markdown"]
        assert "#### demo.OrderService" not in preview["generated_markdown"]
        assert (root / "docs" / "API.md").read_bytes() == target_before
        generation_id = preview["generation_id"]
        assert client.get(f"/documentation/generation/{generation_id}").json()["status"] == "pending"
        approved = client.post(
            f"/documentation/generation/{generation_id}/approve",
            json={"decision": "approve"}
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert "### findOrder(String)" in (root / "docs" / "API.md").read_text(encoding="utf-8")
        after = client.post("/analyze/full", json={"repository_path": str(root)}).json()
        after_coverage = after["documentation_analysis"]
        assert after_coverage["summary"]["documented_method_count"] == 2
        def states(result):
            return {(c["class"], m["signature"]): m["coverage"]
                    for c in result["classes"] for m in c["methods"]}
        expected = states(before_coverage)
        expected[("OrderService", "findOrder(String)")] = "documented"
        assert states(after_coverage) == expected
        assert all(path.read_bytes() == content for path, content in sources_before.items())
