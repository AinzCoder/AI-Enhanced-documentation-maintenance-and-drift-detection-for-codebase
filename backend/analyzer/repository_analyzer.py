import re
from pathlib import Path

from analyzer.java_analyzer import analyze_java_file
from repository.repository_scanner import scan_repository
from timing import timed


PACKAGE_PATTERN = re.compile(
    rb"(?m)^\s*package\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*;"
)
BODY_PREVIEW_LIMIT = 240


def _extract_package(source_code: bytes) -> str | None:
    match = PACKAGE_PATTERN.search(source_code)
    if match is None:
        return None
    return match.group(1).decode("utf-8")


def _method_signature(method) -> str:
    parameter_types = ", ".join(
        parameter.type or "?"
        for parameter in method.parameters
    )
    return f"{method.name}({parameter_types})"


def _body_preview(body: str | None) -> str | None:
    if body is None:
        return None

    preview = " ".join(body.split())
    if len(preview) > BODY_PREVIEW_LIMIT:
        return preview[:BODY_PREVIEW_LIMIT].rstrip() + "..."
    return preview


def _serialize_class(class_info) -> dict:
    methods = []
    for method in sorted(
        class_info.methods,
        key=lambda item: (
            item.name,
            tuple(parameter.type or "" for parameter in item.parameters),
            item.start_line or 0
        )
    ):
        methods.append({
            "name": method.name,
            "signature": _method_signature(method),
            "return_type": method.return_type,
            "parameters": [
                {
                    "name": parameter.name,
                    "type": parameter.type
                }
                for parameter in method.parameters
            ],
            "body_available": method.body is not None,
            "body_preview": _body_preview(method.body),
            "comment": method.comment,
            "start_line": method.start_line,
            "end_line": method.end_line
        })

    return {
        "name": class_info.name,
        "comment": class_info.comment,
        "method_count": len(methods),
        "methods": methods
    }


@timed("repository.full_analysis")
def analyze_full_repository(repository_path: str) -> dict:
    repository_info = scan_repository(repository_path)
    root = Path(repository_info.root_path)
    java_files = [
        file_path
        for file_path in repository_info.source_files
        if Path(file_path).suffix.lower() == ".java"
    ]

    files = []
    errors = []
    class_count = 0
    method_count = 0
    total_java_source_lines = 0
    files_analyzed = 0
    line_count_unavailable = 0

    for relative_path in java_files:
        file_result = {
            "file": relative_path,
            "package": None,
            "line_count": None,
            "class_count": 0,
            "method_count": 0,
            "classes": []
        }
        source_path = root / relative_path

        try:
            source_code = source_path.read_bytes()
            file_result["line_count"] = len(source_code.splitlines())
            total_java_source_lines += file_result["line_count"]
            file_result["package"] = _extract_package(source_code)
            code_file = analyze_java_file(
                relative_path,
                source_code=source_code
            )
        except Exception as error:
            if file_result["line_count"] is None:
                line_count_unavailable += 1
            errors.append({
                "file": relative_path,
                "stage": "java_analysis",
                "message": str(error)
            })
            files.append(file_result)
            continue

        serialized_classes = [
            _serialize_class(class_info)
            for class_info in sorted(
                code_file.classes,
                key=lambda item: item.name
            )
        ]
        file_result["classes"] = serialized_classes
        file_result["class_count"] = len(serialized_classes)
        file_result["method_count"] = sum(
            class_info["method_count"]
            for class_info in serialized_classes
        )
        class_count += file_result["class_count"]
        method_count += file_result["method_count"]
        files_analyzed += 1
        files.append(file_result)

    return {
        "repository": repository_info.project_name,
        "summary": {
            "java_file_count": len(java_files),
            "files_analyzed": files_analyzed,
            "files_with_errors": len(errors),
            "class_count": class_count,
            "method_count": method_count,
            "total_java_source_lines": total_java_source_lines,
            "line_count_unavailable": line_count_unavailable
        },
        "files": files,
        "documentation_files": repository_info.documentation_files,
        "errors": errors
    }
