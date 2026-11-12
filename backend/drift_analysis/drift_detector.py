
from pathlib import Path
import re
from timing import timed

from documentation_analysis.documentation_coverage import (
    DEFAULT_DOCUMENTATION_TARGET,
    find_documentation_mapping
)


def is_method_documented(
    content: str,
    method_name: str
) -> bool:
    """
    Return True only when the method has its own Markdown heading.

    Supported examples:
        ### setOrder
        ### setOrder(int orderId)
        #### getOrder(int orderId)
    """

    # Remove fenced code blocks so code examples don't count
    # as actual documentation.
    content = re.sub(
        r"```.*?```",
        "",
        content,
        flags=re.DOTALL
    )

    headings = re.findall(
        r"(?m)^#{1,6}\s+(.+?)\s*$",
        content
    )

    for heading in headings:
        match = re.match(
            r"^([A-Za-z_$][A-Za-z0-9_$]*)\s*(?:\(.*\))?$",
            heading.strip()
        )

        if match and match.group(1).lower() == method_name.lower():
            return True

    return False


@timed("documentation.drift")
def detect_documentation_drift(
    repository_path: str,
    documentation_files: list[str],
    changes: list[dict]
):
    drift_results = []
    reported_errors = set()

    for change in changes:
        change_type = change.get("type")
        class_name = change.get("class")
        method_name = change.get("method")
        if not class_name:
            continue

        parameter_types = change.get("parameter_types")
        if parameter_types is None:
            signature = change.get("method_signature", "")
            signature_match = re.search(r"\((.*)\)$", signature)
            parameter_types = (
                tuple(
                    item.strip()
                    for item in signature_match.group(1).split(",")
                    if item.strip()
                )
                if signature_match
                else None
            )
        elif not isinstance(parameter_types, tuple):
            parameter_types = tuple(parameter_types)

        mapping = find_documentation_mapping(
            repository_path=repository_path,
            documentation_files=documentation_files,
            class_name=class_name,
            method_name=method_name,
            parameter_types=parameter_types,
            source_file=change.get("source_file")
        )

        for error in mapping["errors"]:
            error_path = error["file"]
            if error_path in reported_errors:
                continue
            reported_errors.add(error_path)
            drift_results.append({
                "type": "documentation_error",
                "finding_type": "documentation_read_error",
                "documentation_file": error_path,
                "reason": error["message"]
            })

        mapping_status = mapping["status"]
        finding_type = None
        reason = None
        review_classification = "action_required"

        if change_type == "class_added":
            if mapping_status == "missing":
                finding_type = "missing_class_documentation"
                reason = "New class has no matching class heading."
            elif mapping_status == "ambiguous":
                finding_type = "ambiguous_documentation_mapping"
                reason = "Class documentation maps to multiple locations."
        elif change_type == "class_removed":
            if mapping_status == "documented":
                finding_type = "obsolete_class_documentation"
                reason = (
                    "Documentation remains for a class removed by the "
                    "Git comparison."
                )
        elif change_type == "method_added":
            if mapping_status == "missing":
                finding_type = "missing_method_documentation"
                reason = "New method has no matching heading in its class section."
            elif mapping_status == "ambiguous":
                finding_type = "ambiguous_documentation_mapping"
                reason = "Method documentation does not identify a unique overload."
        elif change_type == "method_removed":
            if mapping_status == "documented":
                finding_type = "obsolete_method_documentation"
                reason = (
                    "Documentation remains for a method removed by the "
                    "Git comparison."
                )
            elif mapping_status == "ambiguous":
                finding_type = "ambiguous_documentation_mapping"
                reason = "Removed method documentation maps ambiguously."
        elif change_type in {
            "return_type_changed",
            "parameters_changed",
            "parameter_type_changed",
            "parameter_name_changed",
            "method_body_changed"
        }:
            finding_type = "documentation_review_required"
            reason = (
                "A method signature or implementation changed; review the "
                "related documentation."
            )
            review_classification = "review_required"
        else:
            continue

        if finding_type is None:
            continue

        start_line = change.get("start_line")
        end_line = change.get("end_line")
        if start_line is None:
            start_line = change.get("old_start_line")
        if end_line is None:
            end_line = change.get("old_end_line")
        source_line_range = {}
        if start_line is not None:
            source_line_range["start_line"] = start_line
        if end_line is not None:
            source_line_range["end_line"] = end_line

        target = (
            mapping["documentation_files"][0]
            if len(mapping["documentation_files"]) == 1
            else None
        )
        if target is None and mapping_status == "missing":
            target = DEFAULT_DOCUMENTATION_TARGET

        drift_result = {
            "type": "documentation_drift",
            "change_type": change_type,
            "class": class_name,
            "method": method_name,
            "reason": reason,
            "source_file": change.get("source_file"),
            "finding_type": finding_type,
            "review_classification": review_classification,
            "documentation_target": target,
            "evidence": {
                **mapping["evidence"],
                "change": change
            }
        }
        if source_line_range:
            drift_result["source_line_range"] = source_line_range
        drift_results.append(drift_result)

    return drift_results
@timed("documentation.empty_check")
def find_empty_documentation_files(
    repository_path: str,
    documentation_files: list[str]
):
    repository = Path(repository_path)
    results = []

    for documentation_file in documentation_files:
        path = repository / documentation_file

        if not path.exists():
            results.append({
                "type": "documentation_drift",
                "reason": "Documentation file is missing",
                "documentation_file": documentation_file
            })
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as error:
            results.append({
                "type": "documentation_error",
                "finding_type": "documentation_read_error",
                "documentation_file": documentation_file,
                "reason": str(error)
            })
            continue

        if not content.strip():
            results.append({
                "type": "documentation_drift",
                "reason": "Documentation file is empty",
                "documentation_file": documentation_file
            })

    return results