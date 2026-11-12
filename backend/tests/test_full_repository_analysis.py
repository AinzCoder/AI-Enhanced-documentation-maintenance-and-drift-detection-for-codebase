import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyzer.repository_analyzer import analyze_full_repository
from app.main import app
from repository.repository_scanner import scan_repository


@pytest.fixture
def client():
    return TestClient(app)


def write_file(root, relative_path, content):
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_analyze_one_java_file(tmp_path):
    write_file(
        tmp_path,
        "src/Example.java",
        "class Example { int value() { return 1; } }\n"
    )

    result = analyze_full_repository(str(tmp_path))

    assert result["summary"]["java_file_count"] == 1
    assert result["summary"]["files_analyzed"] == 1
    assert result["summary"]["class_count"] == 1
    assert result["summary"]["method_count"] == 1
    assert result["files"][0]["file"] == str(Path("src") / "Example.java")
    assert result["files"][0]["classes"][0]["methods"][0]["name"] == "value"


def test_analyze_multiple_java_files(tmp_path):
    write_file(tmp_path, "src/One.java", "class One {}\n")
    write_file(tmp_path, "src/Two.java", "class Two {}\n")

    result = analyze_full_repository(str(tmp_path))

    assert [file["file"] for file in result["files"]] == [
        str(Path("src") / "One.java"),
        str(Path("src") / "Two.java")
    ]
    assert result["summary"]["java_file_count"] == 2
    assert result["summary"]["class_count"] == 2


def test_nested_packages_are_discovered_and_reported(tmp_path):
    write_file(
        tmp_path,
        "src/main/java/com/example/deep/Service.java",
        "package com.example.deep;\nclass Service {}\n"
    )

    result = analyze_full_repository(str(tmp_path))

    assert result["files"][0]["file"] == str(
        Path("src") / "main" / "java" / "com" / "example" / "deep"
        / "Service.java"
    )
    assert result["files"][0]["package"] == "com.example.deep"


def test_multiple_classes_are_aggregated(tmp_path):
    write_file(
        tmp_path,
        "Many.java",
        "class First { void one() {} }\nclass Second { void two() {} }\n"
    )

    result = analyze_full_repository(str(tmp_path))

    assert [item["name"] for item in result["files"][0]["classes"]] == [
        "First",
        "Second"
    ]
    assert result["files"][0]["class_count"] == 2
    assert result["files"][0]["method_count"] == 2


def test_method_line_positions_are_included(tmp_path):
    write_file(
        tmp_path,
        "Positions.java",
        "class Positions {\n\n    int value() {\n        return 1;\n    }\n}\n"
    )

    result = analyze_full_repository(str(tmp_path))
    method = result["files"][0]["classes"][0]["methods"][0]

    assert method["start_line"] == 3
    assert method["end_line"] == 5


def test_overloaded_methods_have_distinct_signatures_and_no_full_body(tmp_path):
    write_file(
        tmp_path,
        "Overloads.java",
        (
            "class Overloads {\n"
            "    int value(int input) { return input; }\n"
            "    int value(String input) { return 1; }\n"
            "}\n"
        )
    )

    result = analyze_full_repository(str(tmp_path))
    methods = result["files"][0]["classes"][0]["methods"]

    assert sorted(method["signature"] for method in methods) == [
        "value(String)",
        "value(int)"
    ]
    assert all(method["body_available"] for method in methods)
    assert all("body" not in method for method in methods)
    assert all(method["body_preview"].startswith("{") for method in methods)


def test_empty_readme_is_discovered_without_content_filtering(tmp_path):
    write_file(tmp_path, "src/A.java", "class A {}\n")
    readme = write_file(tmp_path, "README.md", "")

    result = analyze_full_repository(str(tmp_path))

    assert str(Path("README.md")) in result["documentation_files"]
    assert readme.read_text(encoding="utf-8") == ""


def test_no_documentation_files_returns_empty_list(tmp_path):
    write_file(tmp_path, "A.java", "class A {}\n")

    result = analyze_full_repository(str(tmp_path))

    assert result["documentation_files"] == []


def test_no_java_files_has_zero_java_counts(tmp_path):
    write_file(tmp_path, "README.md", "Project\n")
    write_file(tmp_path, "notes.txt", "Notes\n")

    result = analyze_full_repository(str(tmp_path))

    assert result["files"] == []
    assert result["summary"]["java_file_count"] == 0
    assert result["summary"]["class_count"] == 0
    assert result["summary"]["method_count"] == 0
    assert result["summary"]["total_java_source_lines"] == 0


def test_scanning_does_not_require_git(tmp_path):
    write_file(tmp_path, "src/Plain.java", "class Plain {}\n")

    result = analyze_full_repository(str(tmp_path))

    assert result["summary"]["files_analyzed"] == 1
    assert result["errors"] == []


def test_excluded_directories_are_pruned(tmp_path):
    write_file(tmp_path, "src/Kept.java", "class Kept {}\n")
    excluded = (
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "target",
        "build",
        "dist",
        ".next",
        "__pycache__",
        ".pytest_cache"
    )
    for directory in excluded:
        write_file(
            tmp_path,
            str(Path(directory) / "Nested.java"),
            "class Ignored {}\n"
        )

    scan = scan_repository(str(tmp_path))
    result = analyze_full_repository(str(tmp_path))

    assert scan.source_files == [str(Path("src") / "Kept.java")]
    assert [file["file"] for file in result["files"]] == [
        str(Path("src") / "Kept.java")
    ]


def test_invalid_repository_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        analyze_full_repository(str(tmp_path / "missing"))

    file_path = tmp_path / "not-a-directory"
    file_path.write_text("file", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        analyze_full_repository(str(file_path))


def test_malformed_java_is_reported_as_per_file_error(tmp_path):
    write_file(tmp_path, "Broken.java", "class Broken { void f( { }\n")

    result = analyze_full_repository(str(tmp_path))

    assert result["summary"]["java_file_count"] == 1
    assert result["summary"]["files_analyzed"] == 0
    assert result["summary"]["files_with_errors"] == 1
    assert result["files"][0]["line_count"] == 1
    assert result["errors"][0]["file"] == "Broken.java"
    assert result["errors"][0]["stage"] == "java_analysis"


def test_malformed_file_does_not_abort_valid_java_files(tmp_path):
    write_file(tmp_path, "A_Broken.java", "class Broken { void f( { }\n")
    write_file(tmp_path, "B_Good.java", "class Good { void valid() {} }\n")

    result = analyze_full_repository(str(tmp_path))

    assert result["summary"]["java_file_count"] == 2
    assert result["summary"]["files_analyzed"] == 1
    assert result["summary"]["files_with_errors"] == 1
    assert result["files"][0]["classes"] == []
    assert result["files"][1]["classes"][0]["name"] == "Good"


def test_summary_counts_include_lines_from_malformed_files(tmp_path):
    write_file(tmp_path, "Good.java", "class Good {}\n\n")
    write_file(tmp_path, "Bad.java", "class Bad { void broken( { }\n\n")

    result = analyze_full_repository(str(tmp_path))

    assert result["summary"]["java_file_count"] == 2
    assert result["summary"]["files_analyzed"] == 1
    assert result["summary"]["files_with_errors"] == 1
    assert result["summary"]["class_count"] == 1
    assert result["summary"]["total_java_source_lines"] == 4


def test_full_endpoint_response_and_no_documentation_writes(client, tmp_path):
    write_file(tmp_path, "src/Example.java", "class Example { void run() {} }\n")
    readme = write_file(tmp_path, "README.md", "")
    original = readme.read_bytes()

    response = client.post(
        "/analyze/full",
        json={"repository_path": str(tmp_path.resolve())}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "repository",
        "analysis_mode",
        "summary",
        "files",
        "documentation_files",
        "documentation_analysis",
        "errors"
    }
    assert body["repository"] == tmp_path.name
    assert body["analysis_mode"] == "full"
    assert body["files"][0]["file"] == str(
        Path("src") / "Example.java"
    )
    assert all(
        str(tmp_path.resolve()) not in str(value)
        for value in body.values()
    )
    assert readme.read_bytes() == original
    assert not (tmp_path / "docs" / "API.md").exists()


def test_full_endpoint_validates_absolute_existing_directory(client, tmp_path):
    relative_response = client.post(
        "/analyze/full",
        json={"repository_path": "relative/repository"}
    )
    missing_response = client.post(
        "/analyze/full",
        json={"repository_path": str(tmp_path / "missing")}
    )
    file_path = write_file(tmp_path, "plain-file", "not a directory")
    not_directory_response = client.post(
        "/analyze/full",
        json={"repository_path": str(file_path.resolve())}
    )

    assert relative_response.status_code == 400
    assert missing_response.status_code == 404
    assert not_directory_response.status_code == 400
    assert str(tmp_path.resolve()) not in missing_response.text


def test_existing_analyze_endpoint_remains_registered():
    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }

    assert ("POST", "/analyze") in routes
    assert ("POST", "/analyze/full") in routes


def test_large_repository_analysis(tmp_path):
    java_file_count = 100
    expected_lines_per_file = 52
    for file_index in range(java_file_count):
        source_lines = [
            f"package generated.pkg{file_index % 10};",
            f"class Generated{file_index} {{",
            "    int value() {",
            "        return 1;",
            "    }"
        ]
        source_lines.extend(
            f"    // synthetic line {line_index}"
            for line_index in range(expected_lines_per_file - 6)
        )
        source_lines.append("}")
        assert len(source_lines) == expected_lines_per_file
        write_file(
            tmp_path,
            str(
                Path("src")
                / f"pkg{file_index % 10}"
                / f"Generated{file_index}.java"
            ),
            "\n".join(source_lines) + "\n"
        )

    started_at = time.perf_counter()
    result = analyze_full_repository(str(tmp_path))
    elapsed_seconds = time.perf_counter() - started_at

    assert result["summary"]["java_file_count"] == 100
    assert result["summary"]["files_analyzed"] == 100
    assert result["summary"]["files_with_errors"] == 0
    assert result["summary"]["class_count"] == 100
    assert result["summary"]["method_count"] == 100
    assert result["summary"]["total_java_source_lines"] == (
        java_file_count * expected_lines_per_file
    )
    assert elapsed_seconds < 30
