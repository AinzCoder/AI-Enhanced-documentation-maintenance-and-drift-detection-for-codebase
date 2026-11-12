import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzer.repository_analyzer import analyze_full_repository
from app.main import app
from documentation_analysis.documentation_coverage import (
    analyze_documentation_coverage
)
from drift_analysis.drift_detector import detect_documentation_drift


@pytest.fixture
def client():
    return TestClient(app)


def write_file(root, relative_path, content):
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def analyze_coverage(root, changes=None):
    full_analysis = analyze_full_repository(str(root))
    result = analyze_documentation_coverage(
        str(root),
        full_analysis,
        git_changes=changes
    )
    return full_analysis, result


def finding(result, finding_type, method=None, class_name=None):
    matches = [
        item for item in result["findings"]
        if item["finding_type"] == finding_type
        and (method is None or item.get("method") == method)
        and (class_name is None or item.get("class") == class_name)
    ]
    assert matches, result["findings"]
    return matches[0]


def drift(root, change, docs=None):
    return detect_documentation_drift(
        str(root),
        docs or ["API.md"],
        [change]
    )


def test_fully_documented_class_and_method(tmp_path):
    write_file(
        tmp_path,
        "src/OrderService.java",
        "class OrderService {\n    int getOrder(int id) { return id; }\n}\n"
    )
    write_file(
        tmp_path,
        "API.md",
        "## OrderService\n\n### getOrder(int id)\nReturns an order.\n"
    )

    _, result = analyze_coverage(tmp_path)

    assert result["summary"]["documented_class_count"] == 1
    assert result["summary"]["documented_method_count"] == 1
    assert result["covered_classes"][0]["documentation_file"] == "API.md"
    assert result["covered_methods"][0]["signature"] == "getOrder(int)"


def test_missing_class_documentation(tmp_path):
    write_file(tmp_path, "A.java", "class A {}\n")
    write_file(tmp_path, "API.md", "# API\n")

    _, result = analyze_coverage(tmp_path)

    assert finding(result, "missing_class_documentation", class_name="A")
    assert "docs/API.md" in result["proposed_documentation_targets"]


def test_missing_method_documentation(tmp_path):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "API.md", "## A\n")

    _, result = analyze_coverage(tmp_path)

    assert finding(result, "missing_method_documentation", method="run")


@pytest.mark.parametrize("documentation_path", ["README.md", "docs/API.md"])
def test_empty_markdown_is_detected_independent_of_filename(
    tmp_path,
    documentation_path
):
    write_file(tmp_path, "A.java", "class A {}\n")
    write_file(tmp_path, documentation_path, "")

    _, result = analyze_coverage(tmp_path)

    empty = finding(result, "empty_documentation")
    assert empty["documentation_target"] == str(Path(documentation_path))


def test_no_documentation_files_proposes_default_target(tmp_path):
    write_file(tmp_path, "A.java", "class A {}\n")

    _, result = analyze_coverage(tmp_path)

    missing = finding(result, "missing_documentation_file")
    assert missing["documentation_target"] == "docs/API.md"


def test_identically_named_methods_are_scoped_to_their_class(tmp_path):
    write_file(
        tmp_path,
        "A.java",
        "class A { int value() { return 1; } }\n"
    )
    write_file(
        tmp_path,
        "B.java",
        "class B { int value() { return 2; } }\n"
    )
    write_file(
        tmp_path,
        "API.md",
        "## A\n### value()\n\n## B\n### value()\n"
    )

    _, result = analyze_coverage(tmp_path)

    assert result["summary"]["documented_method_count"] == 2
    assert not result["missing_documentation_findings"]


def test_overloaded_methods_require_matching_signatures(tmp_path):
    write_file(
        tmp_path,
        "A.java",
        "class A {\n"
        "    int find(int id) { return id; }\n"
        "    int find(String name) { return 1; }\n"
        "}\n"
    )
    write_file(
        tmp_path,
        "API.md",
        "## A\n### find(int id)\n\n### find(String name)\n"
    )

    _, result = analyze_coverage(tmp_path)

    assert result["summary"]["documented_method_count"] == 2
    assert result["summary"]["ambiguous_method_count"] == 0


def test_duplicate_overload_heading_is_ambiguous(tmp_path):
    write_file(
        tmp_path,
        "A.java",
        "class A { int find(int id) { return id; } }\n"
    )
    write_file(
        tmp_path,
        "API.md",
        "## A\n### find(int id)\n\n### find(int id)\n"
    )

    _, result = analyze_coverage(tmp_path)

    assert result["summary"]["ambiguous_method_count"] == 1
    finding(result, "ambiguous_documentation_mapping", method="find")


def test_added_method_without_documentation_is_reported(tmp_path):
    write_file(tmp_path, "API.md", "## A\n")
    change = {
        "type": "method_added",
        "class": "A",
        "method": "start",
        "parameter_types": [],
        "source_file": "A.java",
        "start_line": 4,
        "end_line": 6
    }

    findings = drift(tmp_path, change)

    assert findings[0]["finding_type"] == "missing_method_documentation"
    assert findings[0]["source_line_range"] == {
        "start_line": 4,
        "end_line": 6
    }
    assert findings[0]["documentation_target"] == "API.md"


def test_removed_method_with_retained_documentation_is_obsolete(tmp_path):
    write_file(tmp_path, "API.md", "## A\n### start(int id)\n")
    change = {
        "type": "method_removed",
        "class": "A",
        "method": "start",
        "parameter_types": ["int"],
        "source_file": "A.java",
        "old_start_line": 3,
        "old_end_line": 5
    }

    findings = drift(tmp_path, change)

    assert findings[0]["finding_type"] == "obsolete_method_documentation"
    assert findings[0]["source_line_range"] == {
        "start_line": 3,
        "end_line": 5
    }


@pytest.mark.parametrize(
    "change_type",
    [
        "method_body_changed",
        "parameter_name_changed",
        "return_type_changed",
        "parameters_changed",
        "parameter_type_changed"
    ]
)
def test_method_changes_are_review_candidates_not_confirmed_drift(
    tmp_path,
    change_type
):
    write_file(tmp_path, "API.md", "## A\n### start(int id)\n")
    change = {
        "type": change_type,
        "class": "A",
        "method": "start",
        "parameter_types": ["int"],
        "source_file": "src/A.java",
        "start_line": 8,
        "end_line": 10
    }

    findings = drift(tmp_path, change)

    assert findings[0]["finding_type"] == "documentation_review_required"
    assert findings[0]["review_classification"] == "review_required"
    assert findings[0]["source_file"] == "src/A.java"


def test_class_addition_is_reported_as_missing_documentation(tmp_path):
    write_file(tmp_path, "API.md", "# API\n")
    findings = drift(
        tmp_path,
        {"type": "class_added", "class": "AddedService", "source_file": "AddedService.java"}
    )

    assert findings[0]["finding_type"] == "missing_class_documentation"


def test_class_removal_only_marks_existing_documentation_obsolete(tmp_path):
    write_file(tmp_path, "API.md", "## RemovedService\n")
    findings = drift(
        tmp_path,
        {
            "type": "class_removed",
            "class": "RemovedService",
            "source_file": "RemovedService.java"
        }
    )

    assert findings[0]["finding_type"] == "obsolete_class_documentation"


def test_multiple_documentation_files_map_only_matching_class(tmp_path):
    write_file(tmp_path, "src/A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "src/B.java", "class B { void stop() {} }\n")
    write_file(tmp_path, "README.md", "## A\n### run()\n")
    write_file(tmp_path, "docs/API.md", "## B\n### stop()\n")

    _, result = analyze_coverage(tmp_path)

    methods = {
        item["class"]: item["documentation_file"]
        for item in result["covered_methods"]
    }
    assert methods == {
        "A": "README.md",
        "B": str(Path("docs") / "API.md")
    }


def test_method_heading_under_wrong_class_does_not_count(tmp_path):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "API.md", "## Other\n### run()\n")

    _, result = analyze_coverage(tmp_path)

    assert result["summary"]["missing_class_count"] == 1
    assert result["summary"]["missing_method_count"] == 1


def test_nested_class_section_is_not_counted_for_outer_class(tmp_path):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "B.java", "class B { void run() {} }\n")
    write_file(
        tmp_path,
        "API.md",
        "## A\n### B\n#### run()\n"
    )

    _, result = analyze_coverage(tmp_path)

    coverage_by_class = {
        item["class"]: item
        for item in result["classes"]
    }
    assert coverage_by_class["A"]["methods"][0]["coverage"] == "missing"
    assert coverage_by_class["B"]["methods"][0]["coverage"] == "documented"


def test_coverage_preserves_source_file_and_method_line_range(tmp_path):
    write_file(
        tmp_path,
        "src/main/java/A.java",
        "class A {\n\n    void run() {\n        return;\n    }\n}\n"
    )
    write_file(tmp_path, "API.md", "## A\n")

    _, result = analyze_coverage(tmp_path)

    missing = finding(result, "missing_method_documentation", method="run")
    assert missing["source_file"] == str(Path("src") / "main" / "java" / "A.java")
    assert missing["source_line_range"] == {
        "start_line": 3,
        "end_line": 5
    }


def test_unreadable_documentation_is_reported_without_aborting(
    tmp_path,
    monkeypatch
):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "broken.md", "## A\n")
    original_read_text = Path.read_text

    def failing_read_text(path, *args, **kwargs):
        if path.name == "broken.md":
            raise OSError("permission denied for test")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", failing_read_text)
    _, result = analyze_coverage(tmp_path)

    assert any(error["file"] == "broken.md" for error in result["errors"])
    assert result["summary"]["unsupported_method_count"] == 1


def test_full_endpoint_adds_documentation_analysis_without_writing_docs(
    client,
    tmp_path
):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "README.md", "")
    before = (tmp_path / "README.md").read_bytes()

    response = client.post(
        "/analyze/full",
        json={"repository_path": str(tmp_path)}
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["analysis_mode"] == "full"
    assert "documentation_analysis" in payload
    assert payload["documentation_analysis"]["empty_documentation_findings"]
    assert payload["errors"] == []
    assert (tmp_path / "README.md").read_bytes() == before


def test_large_repository_coverage_handles_one_hundred_java_files(tmp_path):
    for index in range(100):
        class_name = f"Service{index:03d}"
        write_file(
            tmp_path,
            f"src/pkg{index % 10}/{class_name}.java",
            f"class {class_name} {{\n"
            "    int value() {\n"
            "        return 1;\n"
            "    }\n"
            "}\n"
        )
    write_file(tmp_path, "docs/API.md", "# API\n")

    _, result = analyze_coverage(tmp_path)

    assert result["summary"]["class_count"] == 100
    assert result["summary"]["method_count"] == 100
    assert result["summary"]["missing_class_count"] == 100
    assert result["summary"]["missing_method_count"] == 100


def test_incremental_drift_preserves_legacy_fields_and_line_metadata(tmp_path):
    write_file(tmp_path, "API.md", "## A\n### run()\n")
    findings = drift(
        tmp_path,
        {
            "type": "method_body_changed",
            "class": "A",
            "method": "run",
            "source_file": "src/A.java",
            "start_line": 7,
            "end_line": 9
        }
    )

    assert findings[0]["type"] == "documentation_drift"
    assert findings[0]["change_type"] == "method_body_changed"
    assert findings[0]["class"] == "A"
    assert findings[0]["method"] == "run"
    assert findings[0]["source_line_range"] == {
        "start_line": 7,
        "end_line": 9
    }
