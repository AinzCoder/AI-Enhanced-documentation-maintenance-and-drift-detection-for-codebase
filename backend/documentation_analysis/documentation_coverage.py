import re
from pathlib import Path
from timing import timed


DEFAULT_DOCUMENTATION_TARGET = "docs/API.md"
DOCUMENTATION_SUFFIXES = {".md", ".txt", ".rst"}


def _plain_heading(title: str) -> str:
    title = re.sub(r"`([^`]*)`", r"\1", title)
    title = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", title)
    title = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", title)
    title = re.sub(r"(\*\*|__|~~)(.*?)\1", r"\2", title)
    title = re.sub(r"(?<!\w)[*_]([^*_]+)[*_](?!\w)", r"\1", title)
    title = re.sub(r"\s+\{#[^}]+\}\s*$", "", title)
    return title.strip()


def _parse_headings(content: str, documentation_file: str) -> list[dict]:
    content = re.sub(
        r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$",
        "",
        content
    )
    headings = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match is None:
            continue
        headings.append({
            "level": len(match.group(1)),
            "title": _plain_heading(match.group(2)),
            "line": line_number,
            "documentation_file": documentation_file
        })
    return headings


def _load_documentation(
    repository_path: str,
    documentation_files: list[str]
) -> tuple[list[dict], list[dict], list[dict]]:
    root = Path(repository_path).resolve()
    documents = []
    empty_findings = []
    errors = []

    for relative_path in sorted(set(documentation_files)):
        file_path = Path(relative_path)
        if file_path.is_absolute() or ".." in file_path.parts:
            errors.append({
                "file": str(relative_path),
                "stage": "documentation_coverage",
                "message": "Documentation path is not repository-relative."
            })
            continue

        resolved_path = (root / file_path).resolve()
        if not resolved_path.is_relative_to(root):
            errors.append({
                "file": str(relative_path),
                "stage": "documentation_coverage",
                "message": "Documentation path escapes the repository."
            })
            continue

        try:
            content = resolved_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            errors.append({
                "file": str(relative_path),
                "stage": "documentation_coverage",
                "message": str(error)
            })
            continue

        document = {
            "path": str(relative_path),
            "content": content,
            "headings": (
                _parse_headings(content, str(relative_path))
                if resolved_path.suffix.lower() == ".md"
                else []
            ),
            "empty": not content.strip(),
            "markdown": resolved_path.suffix.lower() == ".md"
        }
        documents.append(document)
        if document["empty"]:
            empty_findings.append({
                "finding_type": "empty_documentation",
                "documentation_target": str(relative_path),
                "reason": "Documentation file contains no non-whitespace content.",
                "evidence": {
                    "documentation_file": str(relative_path),
                    "content_length": len(content)
                }
            })

    return documents, empty_findings, errors


def _class_title_matches(title: str, class_info: dict, source_file: str) -> bool:
    class_name = class_info.get("name")
    if title == class_name:
        return True

    package_name = class_info.get("package")
    if package_name and title == f"{package_name}.{class_name}":
        return True

    normalized_title = title.replace("\\", "/").lstrip("./")
    normalized_file = source_file.replace("\\", "/")
    qualified_path_titles = {
        f"{normalized_file}::{class_name}",
        f"{normalized_file}#{class_name}",
        f"{class_name} — {normalized_file}"
    }
    if package_name:
        qualified_path_titles.add(f"{package_name}.{class_name} — {normalized_file}")
    if Path(normalized_file).stem == class_name:
        qualified_path_titles.add(normalized_file)
    return normalized_title in qualified_path_titles


def _class_sections(
    documents: list[dict],
    class_info: dict,
    source_file: str,
    all_classes: list[dict]
) -> list[dict]:
    matches = []
    for document in documents:
        if not document["markdown"]:
            continue
        for heading_index, heading in enumerate(document["headings"]):
            if not _class_title_matches(heading["title"], class_info, source_file):
                continue

            duplicate_identity = sum(
                _class_title_matches(
                    heading["title"],
                    {**item["class"], "package": item["file"].get("package")},
                    item["file"].get("file", "")
                )
                for item in all_classes
            ) > 1
            end_index = len(document["headings"])
            for next_index in range(heading_index + 1, end_index):
                if document["headings"][next_index]["level"] <= heading["level"]:
                    end_index = next_index
                    break

            nested_class_headings = set()
            for nested_index in range(heading_index + 1, end_index):
                nested_heading = document["headings"][nested_index]
                if any(
                    (
                        item["class"].get("name")
                        != class_info.get("name")
                        or item["file"].get("file") != source_file
                    )
                    and _class_title_matches(
                        nested_heading["title"],
                        {**item["class"], "package": item["file"].get("package")},
                        item["file"].get("file", "")
                    )
                    for item in all_classes
                ):
                    nested_class_headings.add(nested_index)

            matches.append({
                "document": document,
                "heading": heading,
                "heading_index": heading_index,
                "end_index": end_index,
                "ambiguous": duplicate_identity,
                "class_info": class_info,
                "nested_class_headings": nested_class_headings
            })
    return matches


def _signature_parameter_types(
    title: str, method_name: str, class_name: str | None = None,
    package_name: str | None = None
):
    match = re.match(
        rf"^(?:(?P<prefix>[\w$.\[\]<>?, ]+)\s+)?"
        rf"(?:(?P<class>[\w$.]+)\.)?{re.escape(method_name)}"
        r"\s*\((?P<parameters>.*)\)\s*(?::.*)?$",
        title
    )
    if match is None:
        return None

    qualifier = match.group("class")
    if qualifier:
        allowed = {class_name}
        if class_name and package_name:
            allowed.add(f"{package_name}.{class_name}")
        if qualifier not in allowed:
            return None

    raw_parameters = match.group("parameters").strip()
    if not raw_parameters:
        return []

    parameters = []
    depth = 0
    start = 0
    for index, character in enumerate(raw_parameters):
        if character in "<([":
            depth += 1
        elif character in ">)]":
            depth -= 1
        elif character == "," and depth == 0:
            parameters.append(raw_parameters[start:index].strip())
            start = index + 1
    parameters.append(raw_parameters[start:].strip())

    parameter_types = []
    for parameter in parameters:
        parameter = re.sub(r"`([^`]*)`", r"\1", parameter).strip()
        if ":" in parameter and not parameter.startswith("?"):
            left, right = parameter.split(":", 1)
            if re.fullmatch(r"[A-Za-z_$][\w$]*", left.strip()):
                parameter = right.strip()
        else:
            words = parameter.rsplit(None, 1)
            if len(words) == 2 and re.fullmatch(
                r"[A-Za-z_$][\w$]*(?:\[\])*",
                words[1].strip()
            ):
                suffix = words[1].strip()[len(words[1].strip().rstrip("[]")):]
                parameter = words[0].strip() + suffix
        parameter_types.append(_normalize_type(parameter))
    return parameter_types


def _normalize_type(type_name: str) -> str:
    return re.sub(r"\s+", "", type_name).replace("...", "[]")


def _method_heading_matches(
    title: str,
    method_name: str,
    parameter_types: tuple[str, ...],
    class_name: str | None = None,
    package_name: str | None = None
) -> str:
    if title == method_name or (
        class_name and title in {
            f"{class_name}.{method_name}",
            f"{package_name}.{class_name}.{method_name}" if package_name else ""
        }
    ):
        return "bare"

    heading_types = _signature_parameter_types(
        title, method_name, class_name, package_name
    )
    if heading_types is None:
        return "none"

    expected_types = tuple(_normalize_type(item) for item in parameter_types)
    if tuple(heading_types) == expected_types:
        return "exact"
    return "different"


def _is_method_heading_scope(ancestors: list[dict]) -> bool:
    return all(
        ancestor["title"].casefold() in {
            "methods", "method documentation", "operations"
        }
        for ancestor in ancestors
    )


def _method_mapping(
    class_sections: list[dict],
    method: dict,
    overload_count: int
) -> tuple[str, list[str], list[dict]]:
    exact_matches = []
    bare_matches = []
    uncertain_matches = []
    parameter_types = tuple(
        parameter.get("type") or "?"
        for parameter in method.get("parameters", [])
    )

    for section in class_sections:
        if section["ambiguous"]:
            uncertain_matches.append(section)
            continue

        headings = section["document"]["headings"]
        nested_class_depth = None
        ancestors = []
        for heading_index in range(
            section["heading_index"] + 1,
            section["end_index"]
        ):
            heading = headings[heading_index]
            if nested_class_depth is not None:
                if heading["level"] <= nested_class_depth:
                    nested_class_depth = None
                else:
                    continue

            if heading["level"] <= section["heading"]["level"]:
                break
            while ancestors and ancestors[-1]["level"] >= heading["level"]:
                ancestors.pop()
            if heading_index in section["nested_class_headings"]:
                nested_class_depth = heading["level"]
                continue

            if not _is_method_heading_scope(ancestors):
                ancestors.append(heading)
                continue

            title = heading["title"]
            status = _method_heading_matches(
                title,
                method.get("name", ""),
                parameter_types,
                section["class_info"].get("name"),
                section["class_info"].get("package")
            )
            if status == "exact":
                exact_matches.append((section, heading))
            elif status == "bare":
                bare_matches.append((section, heading))
            ancestors.append(heading)

    if exact_matches and bare_matches:
        return "ambiguous", [], [
            item[1] for item in exact_matches + bare_matches
        ]
    if len(exact_matches) == 1 and not uncertain_matches:
        return "documented", [exact_matches[0][0]["document"]["path"]], [
            exact_matches[0][1]
        ]
    if len(exact_matches) > 1:
        return "ambiguous", [], [item[1] for item in exact_matches]

    if bare_matches:
        if overload_count == 1 and len(bare_matches) == 1 and not uncertain_matches:
            return "documented", [bare_matches[0][0]["document"]["path"]], [
                bare_matches[0][1]
            ]
        return "ambiguous", [], [item[1] for item in bare_matches]

    if uncertain_matches:
        headings = [
            item[1] if isinstance(item, tuple) else item["heading"]
            for item in uncertain_matches
        ]
        return "ambiguous", [], headings

    return "missing", [], []


def _finding(
    finding_type: str,
    reason: str,
    source_file: str | None = None,
    class_name: str | None = None,
    method: dict | None = None,
    documentation_target: str | None = None,
    evidence: dict | None = None
) -> dict:
    finding = {
        "finding_type": finding_type,
        "source_file": source_file,
        "class": class_name,
        "method": method.get("name") if method else None,
        "reason": reason,
        "review_classification": (
            "review_required"
            if finding_type == "documentation_review_required"
            else "action_required"
        ),
        "documentation_target": documentation_target,
        "evidence": evidence or {}
    }
    if method:
        line_range = {}
        if method.get("start_line") is not None:
            line_range["start_line"] = method["start_line"]
        if method.get("end_line") is not None:
            line_range["end_line"] = method["end_line"]
        if line_range:
            finding["source_line_range"] = line_range
    return finding


def _default_target(documents: list[dict]) -> str:
    empty_markdown = [
        document["path"]
        for document in documents
        if document["markdown"] and document["empty"]
    ]
    if len(empty_markdown) == 1:
        return empty_markdown[0]
    return DEFAULT_DOCUMENTATION_TARGET


@timed("documentation.coverage")
def analyze_documentation_coverage(
    repository_path: str,
    full_analysis: dict,
    git_changes: list[dict] | None = None
) -> dict:
    documentation_files = full_analysis.get("documentation_files", [])
    documents, empty_findings, errors = _load_documentation(
        repository_path,
        documentation_files
    )
    markdown_documents = [
        document for document in documents if document["markdown"]
    ]
    all_classes = [
        {"file": file_info, "class": class_info}
        for file_info in full_analysis.get("files", [])
        for class_info in file_info.get("classes", [])
    ]
    findings = []
    class_results = []
    covered_classes = []
    covered_methods = []
    proposed_targets = set()

    if not documentation_files:
        missing_file_finding = _finding(
            "missing_documentation_file",
            "No documentation files were found in the repository.",
            documentation_target=DEFAULT_DOCUMENTATION_TARGET,
            evidence={"documentation_files": []}
        )
        findings.append(missing_file_finding)
        proposed_targets.add(DEFAULT_DOCUMENTATION_TARGET)

    if documentation_files and not markdown_documents:
        findings.append(_finding(
            "missing_documentation_file",
            "No Markdown documentation file is available for heading-based coverage.",
            documentation_target=DEFAULT_DOCUMENTATION_TARGET,
            evidence={"documentation_files": documentation_files}
        ))
        proposed_targets.add(DEFAULT_DOCUMENTATION_TARGET)

    for empty_finding in empty_findings:
        findings.append(_finding(
            "empty_documentation",
            empty_finding["reason"],
            documentation_target=empty_finding["documentation_target"],
            evidence=empty_finding["evidence"]
        ))

    default_target = _default_target(documents)

    for class_entry in all_classes:
        file_info = class_entry["file"]
        class_info = {
            **class_entry["class"],
            "package": file_info.get("package")
        }
        source_file = file_info.get("file")
        class_name = class_info.get("name")
        sections = _class_sections(
            markdown_documents,
            class_info,
            source_file or "",
            all_classes
        )
        class_is_ambiguous = any(section["ambiguous"] for section in sections)
        class_status = (
            "ambiguous" if class_is_ambiguous
            else "documented" if len(sections) == 1
            else "ambiguous" if len(sections) > 1
            else "unsupported"
            if (
                documentation_files
                and (
                    not markdown_documents
                    or (errors and not sections)
                )
            )
            else "missing"
        )
        section_paths = sorted({
            section["document"]["path"]
            for section in sections
        })
        class_target = (
            section_paths[0]
            if class_status == "documented"
            else None
            if class_status == "ambiguous"
            else default_target
        )

        if class_status == "documented":
            covered_classes.append({
                "source_file": source_file,
                "class": class_name,
                "documentation_file": class_target
            })
        elif class_status == "missing":
            proposed_targets.add(class_target)
            findings.append(_finding(
                "missing_class_documentation",
                "No class heading was found in the available Markdown documentation.",
                source_file=source_file,
                class_name=class_name,
                documentation_target=class_target,
                evidence={"class_name": class_name}
            ))
        elif class_status == "unsupported":
            findings.append(_finding(
                "documentation_review_required",
                "Class coverage could not be determined from the available documentation format.",
                source_file=source_file,
                class_name=class_name,
                documentation_target=None,
                evidence={"documentation_files": documentation_files}
            ))
        else:
            findings.append(_finding(
                "ambiguous_documentation_mapping",
                "The class heading maps to multiple code or documentation locations.",
                source_file=source_file,
                class_name=class_name,
                documentation_target=None,
                evidence={"documentation_files": section_paths}
            ))

        methods = class_info.get("methods", [])
        overload_counts = {}
        for method in methods:
            overload_counts[method.get("name")] = (
                overload_counts.get(method.get("name"), 0) + 1
            )

        method_results = []
        for method in methods:
            if class_status == "ambiguous":
                method_status, method_paths, matching_headings = (
                    "ambiguous",
                    [],
                    []
                )
            elif not markdown_documents and documentation_files:
                method_status, method_paths, matching_headings = (
                    "unsupported",
                    [],
                    []
                )
            elif class_status == "missing":
                method_status, method_paths, matching_headings = (
                    "missing",
                    [],
                    []
                )
            elif errors and not sections:
                method_status, method_paths, matching_headings = (
                    "unsupported",
                    [],
                    []
                )
            else:
                method_status, method_paths, matching_headings = _method_mapping(
                    sections,
                    method,
                    overload_counts.get(method.get("name"), 1)
                )

            signature = method.get("signature")
            method_result = {
                **method,
                "coverage": method_status,
                "documentation_file": (
                    method_paths[0] if len(method_paths) == 1 else None
                )
            }
            method_results.append(method_result)

            if method_status == "documented":
                covered_methods.append({
                    "source_file": source_file,
                    "class": class_name,
                    "method": method.get("name"),
                    "signature": signature,
                    "source_line_range": {
                        key: method[key]
                        for key in ("start_line", "end_line")
                        if method.get(key) is not None
                    },
                    "documentation_file": method_paths[0]
                })
            elif method_status == "missing":
                target = class_target or default_target
                proposed_targets.add(target)
                findings.append(_finding(
                    "missing_method_documentation",
                    "No matching method heading was found in the class documentation section.",
                    source_file=source_file,
                    class_name=class_name,
                    method=method,
                    documentation_target=target,
                    evidence={"expected_signature": signature}
                ))
            elif method_status == "ambiguous":
                findings.append(_finding(
                    "ambiguous_documentation_mapping",
                    "Method headings do not identify a unique overload or class section.",
                    source_file=source_file,
                    class_name=class_name,
                    method=method,
                    documentation_target=None,
                    evidence={
                        "expected_signature": signature,
                        "matching_headings": [
                            heading["title"]
                            for heading in matching_headings
                        ]
                    }
                ))
            elif method_status == "unsupported":
                findings.append(_finding(
                    "documentation_review_required",
                    "Coverage could not be determined from the available documentation format or unreadable files.",
                    source_file=source_file,
                    class_name=class_name,
                    method=method,
                    documentation_target=None,
                    evidence={"expected_signature": signature}
                ))

        class_results.append({
            "source_file": source_file,
            "package": file_info.get("package"),
            "class": class_name,
            "coverage": class_status,
            "documentation_file": class_target,
            "methods": method_results
        })

    for change in git_changes or []:
        change_type = change.get("type")
        if change_type in {"class_removed", "method_removed"}:
            mapping = find_documentation_mapping(
                repository_path,
                documentation_files,
                change.get("class", ""),
                change.get("method"),
                tuple(change.get("parameter_types", ())),
                change.get("source_file")
            )
            if mapping["status"] == "documented":
                obsolete_type = (
                    "obsolete_class_documentation"
                    if change_type == "class_removed"
                    else "obsolete_method_documentation"
                )
                findings.append(_finding(
                    obsolete_type,
                    "Documentation remains for code removed by the Git comparison.",
                    source_file=change.get("source_file"),
                    class_name=change.get("class"),
                    method={
                        "name": change.get("method"),
                        "start_line": change.get("old_start_line"),
                        "end_line": change.get("old_end_line")
                    } if change.get("method") else None,
                    documentation_target=(
                        mapping["documentation_files"][0]
                        if mapping["documentation_files"]
                        else None
                    ),
                    evidence={"change": change, **mapping["evidence"]}
                ))
            elif mapping["status"] == "ambiguous":
                findings.append(_finding(
                    "ambiguous_documentation_mapping",
                    "Removed code maps to ambiguous documentation headings.",
                    source_file=change.get("source_file"),
                    class_name=change.get("class"),
                    method={
                        "name": change.get("method"),
                        "start_line": change.get("old_start_line"),
                        "end_line": change.get("old_end_line")
                    } if change.get("method") else None,
                    documentation_target=None,
                    evidence={"change": change, **mapping["evidence"]}
                ))
            continue
        if change_type not in {
            "return_type_changed",
            "parameters_changed",
            "parameter_type_changed",
            "parameter_name_changed",
            "method_body_changed"
        }:
            continue
        findings.append(_finding(
            "documentation_review_required",
            "A source signature or implementation changed; documentation should be reviewed.",
            source_file=change.get("source_file"),
            class_name=change.get("class"),
            method={
                "name": change.get("method"),
                "start_line": change.get("start_line"),
                "end_line": change.get("end_line")
            } if change.get("method") else None,
            documentation_target=change.get("documentation_target"),
            evidence={"change": change}
        ))

    for file_info in full_analysis.get("files", []):
        if file_info.get("classes") or not file_info.get("file"):
            continue
        if any(error.get("file") == file_info.get("file")
               for error in full_analysis.get("errors", [])):
            findings.append({
                "finding_type": "documentation_review_required",
                "source_file": file_info["file"],
                "class": None,
                "method": None,
                "reason": "Java analysis failed; documentation coverage is unsupported for this file.",
                "review_classification": "review_required",
                "documentation_target": None,
                "evidence": {"analysis_status": "failed"}
            })

    class_statuses = [
        item["coverage"]
        for item in class_results
    ]
    method_statuses = [
        method["coverage"]
        for item in class_results
        for method in item["methods"]
    ]
    return {
        "summary": {
            "java_file_count": full_analysis.get("summary", {}).get(
                "java_file_count", 0
            ),
            "class_count": len(class_results),
            "method_count": len(method_statuses),
            "documented_class_count": class_statuses.count("documented"),
            "missing_class_count": class_statuses.count("missing"),
            "ambiguous_class_count": class_statuses.count("ambiguous"),
            "unsupported_class_count": class_statuses.count("unsupported"),
            "documented_method_count": method_statuses.count("documented"),
            "missing_method_count": method_statuses.count("missing"),
            "ambiguous_method_count": method_statuses.count("ambiguous"),
            "unsupported_method_count": method_statuses.count("unsupported"),
            "documentation_file_count": len(documentation_files),
            "empty_documentation_file_count": len(empty_findings)
        },
        "classes": class_results,
        "covered_classes": covered_classes,
        "covered_methods": covered_methods,
        "missing_documentation_findings": [
            finding for finding in findings
            if finding["finding_type"] in {
                "missing_class_documentation",
                "missing_method_documentation",
                "missing_documentation_file"
            }
        ],
        "empty_documentation_findings": [
            finding for finding in findings
            if finding["finding_type"] == "empty_documentation"
        ],
        "ambiguous_mappings": [
            finding for finding in findings
            if finding["finding_type"] == "ambiguous_documentation_mapping"
        ],
        "proposed_documentation_targets": sorted(
            target for target in proposed_targets if target
        ),
        "findings": findings,
        "errors": errors
    }


def find_documentation_mapping(
    repository_path: str,
    documentation_files: list[str],
    class_name: str,
    method_name: str | None = None,
    parameter_types: tuple[str, ...] | None = None,
    source_file: str | None = None
) -> dict:
    documents, _, errors = _load_documentation(
        repository_path,
        documentation_files
    )
    class_info = {"name": class_name, "package": None}
    classes = [{"class": class_info, "file": {"file": source_file or ""}}]
    sections = _class_sections(
        documents,
        class_info,
        source_file or "",
        classes
    )
    if len(sections) != 1 or sections[0]["ambiguous"]:
        return {
            "status": "ambiguous" if sections else "missing",
            "documentation_files": [],
            "evidence": {
                "class_headings": [
                    section["heading"]["title"] for section in sections
                ]
            },
            "errors": errors
        }

    section = sections[0]
    if method_name is None:
        return {
            "status": "documented",
            "documentation_files": [section["document"]["path"]],
            "evidence": {"class_heading": section["heading"]["title"]},
            "errors": errors
        }

    types = None if parameter_types is None else tuple(parameter_types)
    heading_matches = []
    headings = section["document"]["headings"]
    nested_class_depth = None
    for heading_index in range(
        section["heading_index"] + 1,
        section["end_index"]
    ):
        heading = headings[heading_index]
        if nested_class_depth is not None:
            if heading["level"] <= nested_class_depth:
                nested_class_depth = None
            else:
                continue
        if heading["level"] <= section["heading"]["level"]:
            break
        if (
            heading["level"] > section["heading"]["level"]
            and re.fullmatch(r"[A-Z_$][\w$]*", heading["title"])
            and heading["title"] != class_name
        ):
            nested_class_depth = heading["level"]
            continue
        if types is None:
            title_match = re.match(
                rf"^(?:.*\s)?{re.escape(method_name)}\s*(?:\(.*\))?$",
                heading["title"]
            )
            status = "unknown" if title_match else "none"
        else:
            status = _method_heading_matches(
                heading["title"],
                method_name,
                types,
                class_name
            )
        if status in {"exact", "bare"}:
            heading_matches.append((status, heading))
        elif status == "unknown":
            heading_matches.append((status, heading))

    exact = [item for item in heading_matches if item[0] == "exact"]
    if exact:
        status = "documented" if len(exact) == 1 else "ambiguous"
        matching = [item[1] for item in exact]
    else:
        same_name = [item for item in heading_matches if item[0] == "bare"]
        unknown = [item for item in heading_matches if item[0] == "unknown"]
        if unknown:
            status = "documented" if len(unknown) == 1 else "ambiguous"
            matching = [item[1] for item in unknown]
        elif same_name:
            status = "ambiguous"
            matching = [item[1] for item in same_name]
        else:
            status = "missing"
            matching = []

    return {
        "status": status,
        "documentation_files": (
            [section["document"]["path"]]
            if status in {"documented", "missing"}
            else []
        ),
        "evidence": {
            "class_heading": section["heading"]["title"],
            "method_headings": [item["title"] for item in matching]
        },
        "errors": errors
    }
