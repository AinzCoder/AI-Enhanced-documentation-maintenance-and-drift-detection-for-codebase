import hashlib
import re
from pathlib import Path

from tree_sitter import Parser

from analyzer.java_analyzer import JAVA_LANGUAGE, source_line_range, source_line_starts
from analyzer.repository_analyzer import analyze_full_repository
from documentation_analysis.documentation_coverage import (
    analyze_documentation_coverage
)
from llm.groq_client import GroqClientError, generate_response, generation_deadline
from llm.markdown_response import normalize_markdown_response
from rag.indexer import index_repository_documentation
from rag.repository_context_retriever import retrieve_repository_context
from timing import timed


MAX_METHOD_SOURCE_CHARS = 12000
MAX_CLASS_SOURCE_CHARS = 8000
MAX_RETRIEVED_DOCUMENT_CHARS = 4000
MAX_OVERVIEW_CONTEXT_CHARS = 12000
CLASS_NODE_TYPES = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration"
}


def _relative_path(root: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Repository file path must be relative.")
    resolved_path = (root / path).resolve()
    if not resolved_path.is_relative_to(root):
        raise ValueError("Repository file path escapes the repository.")
    return resolved_path


def _bounded_source(source: str, limit: int) -> tuple[str, bool]:
    if len(source) <= limit:
        return source, True
    head_length = limit * 2 // 3
    tail_length = limit - head_length
    return (
        source[:head_length]
        + "\n/* ... SOURCE CONTEXT TRUNCATED ... */\n"
        + source[-tail_length:],
        False
    )


def _class_nodes(source_code: bytes) -> dict[str, dict]:
    parser = Parser(JAVA_LANGUAGE)
    tree = parser.parse(source_code)
    result = {}
    line_starts = source_line_starts(source_code)

    def visit(node, enclosing_name=None):
        for child in node.children:
            if child.type not in CLASS_NODE_TYPES:
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            simple_name = source_code[
                name_node.start_byte:name_node.end_byte
            ].decode("utf-8")
            class_name = (
                f"{enclosing_name}.{simple_name}"
                if enclosing_name
                else simple_name
            )
            start_line, end_line = source_line_range(child, line_starts)
            result[class_name] = {
                "declaration": source_code[
                    child.start_byte:(
                        child.child_by_field_name("body").start_byte
                        if child.child_by_field_name("body") is not None
                        else child.end_byte
                    )
                ].decode("utf-8"),
                "start_line": start_line,
                "end_line": end_line
            }
            visit(child, class_name)

    visit(tree.root_node)
    return result


def _read_source_file(
    repository_root: Path,
    relative_file: str
) -> tuple[str | None, dict[str, dict] | None, str | None, dict | None]:
    try:
        source_code = _relative_path(
            repository_root,
            relative_file
        ).read_bytes()
        return (
            source_code.decode("utf-8"),
            _class_nodes(source_code),
            hashlib.sha256(source_code).hexdigest(),
            None
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return None, None, None, {
            "stage": "source_read",
            "file": relative_file,
            "message": str(error)
        }


def _method_source(source: str, method: dict) -> tuple[str | None, bool]:
    start_line = method.get("start_line")
    end_line = method.get("end_line")
    if start_line is None or end_line is None or end_line < start_line:
        return None, False
    lines = source.splitlines()
    if start_line < 1 or end_line > len(lines):
        return None, False
    source_segment = "\n".join(lines[start_line - 1:end_line])
    return _bounded_source(source_segment, MAX_METHOD_SOURCE_CHARS)


def _class_implementation_context(
    source: str,
    class_info: dict,
    class_node: dict
) -> tuple[str, bool]:
    context_parts = [class_node.get("declaration", "")]
    source_complete = True
    context_length = sum(len(part) for part in context_parts)
    for method in class_info.get("methods", []):
        if not method.get("body_available"):
            continue
        method_source, method_complete = _method_source(source, method)
        if method_source:
            context_parts.append(method_source)
            context_length += len(method_source) + 2
            source_complete = source_complete and method_complete
            if context_length > MAX_CLASS_SOURCE_CHARS * 2:
                source_complete = False
                break
    bounded_context, bounded_complete = _bounded_source(
        "\n\n".join(part for part in context_parts if part.strip()),
        MAX_CLASS_SOURCE_CHARS
    )
    return bounded_context, source_complete and bounded_complete


def _signature_context(class_info: dict) -> str:
    lines = []
    for method in class_info.get("methods", []):
        comment = method.get("comment")
        line = (
            f"- {method.get('signature')}: "
            f"returns {method.get('return_type') or 'unspecified'}"
        )
        if comment:
            line += f"; source comment: {comment}"
        lines.append(line)
    if not lines:
        return "(No methods were extracted.)"
    bounded_context, is_complete = _bounded_source("\n".join(lines), 2000)
    if not is_complete:
        return bounded_context + "\n... method signature context truncated ..."
    return bounded_context


def _class_implementation_evidence(
    source: str | None,
    class_info: dict
) -> str:
    if source is None:
        return "(Java source is unavailable.)"
    evidence = []
    current_length = 0
    for method in class_info.get("methods", []):
        method_source, _ = _method_source(source, method)
        if method_source:
            snippet = f"{method.get('signature')}:\n{method_source}"
            evidence.append(snippet)
            current_length += len(snippet) + 2
            if current_length >= 4000:
                break
    if not evidence:
        return "(No method implementation evidence was extracted.)"
    bounded_evidence, _ = _bounded_source(
        "\n\n".join(evidence),
        4000
    )
    return bounded_evidence


def _extract_class_documentation(
    repository_root: Path,
    documentation_file: str | None,
    class_name: str,
    package_name: str | None
) -> tuple[str, list[dict]]:
    if not documentation_file:
        return "", []

    try:
        document_path = _relative_path(repository_root, documentation_file)
        if not document_path.exists():
            return "", []
        content = document_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return "", [{
            "stage": "documentation_retrieval",
            "file": documentation_file,
            "message": str(error)
        }]

    headings = list(re.finditer(
        r"(?m)^(#{1,6})\s+(.+?)\s*#*\s*$",
        content
    ))
    expected_names = {class_name}
    if package_name:
        expected_names.add(f"{package_name}.{class_name}")
    for index, heading in enumerate(headings):
        title = heading.group(2).strip().replace("`", "")
        if title not in expected_names:
            continue
        end = len(content)
        for next_heading in headings[index + 1:]:
            if len(next_heading.group(1)) <= len(heading.group(1)):
                end = next_heading.start()
                break
        section = content[heading.start():end].strip()
        return _bounded_source(
            section,
            MAX_RETRIEVED_DOCUMENT_CHARS
        )[0], []
    return "", []


def _safe_class_documentation(
    repository_root: Path,
    documentation_file: str | None,
    class_result: dict,
    errors: list[dict],
    source_file: str
) -> str:
    try:
        context, retrieval_errors = _extract_class_documentation(
            repository_root,
            documentation_file,
            class_result.get("class", ""),
            class_result.get("package")
        )
    except Exception as error:
        context = ""
        retrieval_errors = [{
            "stage": "documentation_retrieval",
            "file": documentation_file,
            "message": str(error)
        }]

    for retrieval_error in retrieval_errors:
        errors.append({
            **retrieval_error,
            "source_file": source_file,
            "class": class_result.get("class")
        })
    return context


def _ensure_generation_index(repository_root: Path, retrieval_state: dict) -> None:
    if retrieval_state["indexing"] is not None:
        return
    try:
        indexing_summary = index_repository_documentation(str(repository_root))
        retrieval_state["indexing"] = {
            "indexed_files": len(indexing_summary.get("indexed_files", [])),
            "skipped_files": len(indexing_summary.get("skipped_files", [])),
            "deleted_files": len(indexing_summary.get("deleted_files", [])),
            "indexed_chunks": indexing_summary.get("indexed_chunks", 0),
            "error_count": len(indexing_summary.get("errors", []))
        }
        if indexing_summary.get("errors"):
            retrieval_state["errors"].append({
                "stage": "vector_indexing",
                "message": (
                    "Some repository documentation could not be indexed; "
                    "repository-local Markdown fallback remains available."
                )
            })
    except Exception as error:
        retrieval_state["indexing"] = {
            "indexed_files": 0,
            "skipped_files": 0,
            "deleted_files": 0,
            "indexed_chunks": 0,
            "error_count": 1
        }
        retrieval_state["errors"].append({
            "stage": "vector_indexing",
            "message": (
                "Repository documentation indexing was unavailable "
                f"({type(error).__name__}); repository-local Markdown "
                "fallback remains available."
            )
        })


def _generation_documentation_context(
    repository_root: Path,
    query: str,
    local_fallback: str,
    retrieval_state: dict
) -> str:
    _ensure_generation_index(repository_root, retrieval_state)
    retrieval_state["query_count"] += 1
    try:
        result = retrieve_repository_context(
            repository_path=str(repository_root),
            query=query,
            top_k=2
        )
    except Exception as error:
        result = {
            "available": False,
            "error": f"retrieval_failed_{type(error).__name__}",
            "documents": [],
            "metadatas": []
        }

    parts = []
    seen = set()
    if result.get("available"):
        for document, metadata in zip(
            result.get("documents", []),
            result.get("metadatas", [])
        ):
            if not document or document in seen:
                continue
            seen.add(document)
            parts.append(
                "Repository-scoped retrieved documentation "
                "(supporting context, not proof of current behavior):\n"
                f"File: {metadata.get('documentation_file', '(unknown)')}\n"
                f"Section: {metadata.get('section_heading', '(document)')}\n"
                f"{document}"
            )
        if parts:
            retrieval_state["vector_store_used"] = True
            retrieval_state["retrieved_chunks"] += len(parts)
    else:
        retrieval_state["errors"].append({
            "stage": "vector_retrieval",
            "message": (
                "Repository-scoped vector retrieval was unavailable; "
                "bounded repository-local Markdown context was used."
            )
        })

    if local_fallback.strip() and local_fallback.strip() not in seen:
        for document in seen:
            local_fallback = local_fallback.replace(document, "")
    if local_fallback.strip():
        parts.append(
            "Repository-local Markdown fallback (supporting context only):\n"
            + local_fallback.strip()
        )
    retrieval_state["fallback_used"] = retrieval_state["fallback_used"] or (
        not result.get("available") or not result.get("documents")
    )
    if not result.get("available") or not result.get("documents"):
        retrieval_state["fallback_count"] += 1

    if not parts:
        return ""
    bounded_context, _ = _bounded_source(
        "\n\n".join(parts),
        MAX_RETRIEVED_DOCUMENT_CHARS
    )
    return bounded_context


def _validate_model_markdown(
    response: str,
    stage: str,
    expected_heading: str | None = None
) -> str:
    markdown = normalize_markdown_response(response)
    if not re.search(r"[A-Za-z0-9]", markdown):
        raise ValueError("Groq returned no usable Markdown content.")
    if stage == "method_generation":
        required_sections = (
            "Purpose and behavior",
            "Parameters",
            "Returns",
            "Behavior"
        )
        if any(section.lower() not in markdown.lower()
               for section in required_sections):
            raise ValueError(
                "Groq returned invalid method Markdown; required sections "
                "are missing."
            )
    if expected_heading:
        lines = markdown.splitlines()
        if lines:
            heading_match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", lines[0])
            if (
                heading_match
                and heading_match.group(1).strip().lower()
                == expected_heading.strip().lower()
            ):
                lines = lines[1:]
                while lines and not lines[0].strip():
                    lines.pop(0)
                markdown = "\n".join(lines).strip()
                if not markdown:
                    raise ValueError(
                        "Groq returned an empty documentation section."
                    )
    return markdown


def _flatten_generated_headings(
    markdown: str,
    duplicate_titles: set[str]
) -> str:
    lines = markdown.splitlines()
    result = []
    fence_character = None
    fence_length = 0
    duplicate_keys = {title.strip().lower() for title in duplicate_titles}

    for line in lines:
        fence_match = re.match(r"^[ \t]*(`{3,}|~{3,})(.*)$", line)
        if fence_match:
            fence = fence_match.group(1)
            if fence_character is None:
                fence_character = fence[0]
                fence_length = len(fence)
            elif fence[0] == fence_character and len(fence) >= fence_length:
                fence_character = None
                fence_length = 0
            result.append(line)
            continue

        heading_match = (
            None
            if fence_character is not None
            else re.match(r"^(#{1,6})[ \t]+(.+?)\s*#*\s*$", line)
        )
        if heading_match is None:
            result.append(line)
            continue

        title = heading_match.group(2).strip()
        normalized_title = re.sub(r"`", "", title).strip().lower()
        if normalized_title in duplicate_keys:
            continue

        result.append(f"**{title}**")

    return "\n".join(result).strip()


def _call_model(
    prompt: str,
    stage: str,
    expected_heading: str | None = None,
    provider_state: dict[str, str] | None = None
) -> tuple[str | None, str | None]:
    if provider_state and provider_state.get("error"):
        return None, provider_state["error"]
    try:
        markdown = _validate_model_markdown(
            generate_response(prompt),
            stage,
            expected_heading
        )
    except GroqClientError as error:
        if provider_state is not None:
            provider_state["error"] = error.public_message
        return None, error.public_message
    except ValueError as error:
        return None, str(error)
    except Exception as error:
        return None, (
            f"{stage}: model generation failed "
            f"({type(error).__name__})."
        )
    if stage == "class_generation":
        return _flatten_generated_headings(
            markdown,
            {expected_heading or ""}
        ), None
    if stage == "method_generation":
        return _flatten_generated_headings(
            markdown,
            {expected_heading or ""}
        ), None
    if stage == "overview_generation":
        return _flatten_generated_headings(
            markdown,
            {"Overview"}
        ), None
    return markdown, None


def _class_identity(file_info: dict, class_info: dict) -> str:
    package_name = file_info.get("package")
    qualified_name = class_info.get(
        "name",
        class_info.get("class", "")
    )
    if package_name and not qualified_name.startswith(package_name + "."):
        qualified_name = f"{package_name}.{qualified_name}"
    return f"{qualified_name} — {file_info.get('file', '')}"


def _class_prompt(
    file_info: dict,
    class_info: dict,
    class_source: str,
    existing_documentation: str,
    source_context_complete: bool
) -> str:
    bounded_class_source, prompt_complete = _bounded_source(
        class_source,
        MAX_CLASS_SOURCE_CHARS
    )
    source_complete = source_context_complete and prompt_complete
    prompt = f"""Write factual Markdown documentation for this Java class.

Use only evidence in the supplied source. Do not invent business rules,
endpoints, exceptions, side effects, or behavior. Do not document constructors
or fields. If the implementation does not provide enough evidence, state that
clearly instead of guessing. Return only a concise class description without
a class heading.

Package: {file_info.get('package') or 'not declared'}
Class: {class_info.get('name')}
Source file: {file_info.get('file')}
Class source lines: {class_info.get('start_line')}–{class_info.get('end_line')}
Class source context complete: {source_complete}
Extracted class comment: {class_info.get('comment') or 'none'}
Extracted method context:
{_signature_context(class_info)}

Existing documentation context (supporting context, not implementation proof):
{existing_documentation or '(No matching existing class documentation.)'}

Java class source evidence:
{bounded_class_source}
"""
    return prompt


def _method_prompt(
    file_info: dict,
    class_info: dict,
    method: dict,
    method_source: str,
    source_complete: bool,
    existing_documentation: str
) -> str:
    if source_complete:
        source_note = "The complete method source range is included."
    else:
        source_note = (
            "The method source was bounded and is INCOMPLETE. Do not claim "
            "behavior that depends on omitted code."
        )

    parameter_context = "\n".join(
        f"- {parameter.get('name')}: {parameter.get('type')}"
        for parameter in method.get("parameters", [])
    ) or "- None"
    return f"""Write factual Markdown documentation for this Java method.

Use only behavior evidenced by the implementation. Do not infer behavior
from names alone. Do not invent API endpoints, business rules, side effects,
or exceptions. Mention exceptions only when the included source explicitly
throws, catches, or declares them. If a detail is not evident, say so.
Respect Java integer overflow; do not claim arithmetic is always exact.
Return the section body only, without a method heading or source heading.
Use these exact labels: **Purpose and behavior**, **Parameters**,
**Returns**, and **Behavior**. Include a short bullet under Parameters and
Returns even when the method has no parameters or returns void.

Class: {_class_identity(file_info, class_info)}
Method signature: {method.get('signature')}
Return type: {method.get('return_type') or 'unspecified'}
Parameters:
{parameter_context}
Source file: {file_info.get('file')}
Source line range: {method.get('start_line')}–{method.get('end_line')}
Extracted source comment: {method.get('comment') or 'none'}
Source context completeness: {source_note}

Class context:
{_signature_context(class_info)}

Existing class documentation context (supporting context, not implementation proof):
{existing_documentation or '(No matching class documentation.)'}

Java method implementation:
{method_source}
"""


def _overview_prompt(class_summaries: list[dict]) -> str:
    context = "\n".join(
        (
            f"- {item['identity']}: {item['summary']}"
            + (
                f" Evidence: {item['evidence']}"
                if item.get("evidence")
                else ""
            )
        )
        for item in class_summaries
    )
    bounded_context, complete = _bounded_source(
        context,
        MAX_OVERVIEW_CONTEXT_CHARS
    )
    completeness_note = (
        "All collected class summaries are included."
        if complete
        else "The overview evidence is truncated; do not imply completeness."
    )
    return f"""Write a concise repository overview in Markdown using only the
class summaries and evidence below. Do not invent system purpose, business
rules, APIs, or behavior. Do not claim completeness when evidence is partial.
Return only the overview text, without a heading.

Evidence completeness: {completeness_note}
Class summaries:
{bounded_context}
"""


def _default_target(full_analysis: dict, coverage: dict) -> str:
    targets = coverage.get("proposed_documentation_targets", [])
    if len(targets) == 1:
        return targets[0]
    markdown_files = [
        item for item in full_analysis.get("documentation_files", [])
        if Path(item).suffix.lower() == ".md"
    ]
    empty_findings = coverage.get("empty_documentation_findings", [])
    empty_targets = sorted({
        item["documentation_target"]
        for item in empty_findings
        if item.get("documentation_target")
        and Path(item["documentation_target"]).suffix.lower() == ".md"
    })
    if len(empty_targets) == 1:
        return empty_targets[0]
    if len(markdown_files) == 1:
        return markdown_files[0]
    return "docs/API.md"


def _render_markdown(
    overview: str | None,
    generated_classes: list[dict],
    generated_methods: list[dict],
    coverage_classes: list[dict]
) -> str:
    lines = ["# Repository Documentation"]
    if overview:
        lines.extend(["", "## Overview", "", overview])
    lines.extend(["", "## Classes"])

    generated_class_by_key = {
        (item["source_file"], item["class"]): item
        for item in generated_classes
    }
    methods_by_key = {}
    for item in generated_methods:
        methods_by_key.setdefault(
            (item["source_file"], item["class"]),
            []
        ).append(item)

    for class_result in coverage_classes:
        source_file = class_result.get("source_file")
        class_name = class_result.get("class")
        key = (source_file, class_name)
        class_item = generated_class_by_key.get(key)
        class_methods = methods_by_key.get(key, [])
        if class_item is None and not class_methods:
            continue

        identity = class_item["identity"] if class_item else (
            f"{class_result.get('package') + '.' if class_result.get('package') else ''}"
            f"{class_name} — {source_file}"
        )
        lines.extend(["", f"### {identity}", ""])
        if class_item:
            lines.append(class_item["description"])
            lines.extend([
                "",
                "**Source**",
                f"- `{source_file}` lines "
                f"{class_item.get('start_line')}–{class_item.get('end_line')}"
            ])
        elif class_result.get("coverage") == "documented":
            lines.append(
                "Class documentation already exists; only the missing "
                "method sections below are previewed."
            )
        else:
            lines.append(
                "Class-level documentation was not generated; see the "
                "generation errors for details."
            )

        for method_item in class_methods:
            lines.extend([
                "",
                f"#### {method_item['signature']}",
                "",
                method_item["documentation"],
                "",
                "**Source**",
                f"- `{source_file}` lines "
                f"{method_item.get('start_line')}–{method_item.get('end_line')}"
            ])
            if not method_item["source_context_complete"]:
                lines.append(
                    "- Implementation context was truncated; review the "
                    "complete source before approval."
                )
    if len(lines) == 3 and not generated_classes and not generated_methods:
        lines.extend(["", "No missing class or method documentation was found."])
    return "\n".join(lines).rstrip() + "\n"


@timed("documentation.generate_full")
@generation_deadline
def generate_full_documentation(
    repository_path: str,
    target_documentation_file: str | None = None,
    include_repository_overview: bool = True,
    max_methods: int | None = None
) -> dict:
    repository_root = Path(repository_path).expanduser().resolve()
    if not repository_root.exists():
        raise FileNotFoundError("Repository path does not exist.")
    if not repository_root.is_dir():
        raise NotADirectoryError("Repository path must be a directory.")

    full_analysis = analyze_full_repository(str(repository_root))
    coverage = analyze_documentation_coverage(
        str(repository_root),
        full_analysis
    )
    documentation_target = (
        target_documentation_file
        or _default_target(full_analysis, coverage)
    )
    target_path = _relative_path(repository_root, documentation_target)
    if target_path.suffix.lower() != ".md":
        raise ValueError("target_documentation_file must have a .md extension.")
    if target_path.exists():
        target_hash_at_generation = hashlib.sha256(
            target_path.read_bytes()
        ).hexdigest()
    else:
        target_hash_at_generation = "__missing__"

    errors = [
        *full_analysis.get("errors", []),
        *coverage.get("errors", [])
    ]
    errors.extend({
        "stage": "documentation_coverage",
        "file": item.get("source_file"),
        "message": (
            f"{item.get('class')} has {item.get('coverage')} documentation "
            "mapping; generation was skipped to avoid duplicating uncertain content."
        )
    } for item in coverage.get("classes", [])
        if item.get("coverage") in {"ambiguous", "unsupported"})

    generated_classes = []
    generated_methods = []
    provider_state: dict[str, str] = {}
    skipped_documented_methods = []
    class_summaries = []
    source_hashes = {}
    retrieval_state = {
        "strategy": "repository_scoped_chromadb_with_local_markdown_fallback",
        "vector_store_used": False,
        "repository_scoped": True,
        "fallback_used": False,
        "fallback_count": 0,
        "query_count": 0,
        "retrieved_chunks": 0,
        "indexing": None,
        "errors": []
    }
    file_results_by_path = {
        item.get("file"): item
        for item in full_analysis.get("files", [])
    }
    classes_by_file = {}
    for class_result in coverage.get("classes", []):
        classes_by_file.setdefault(
            class_result.get("source_file"),
            []
        ).append(class_result)

    for class_result in coverage.get("classes", []):
        for method in class_result.get("methods", []):
            if method.get("coverage") == "documented":
                skipped_documented_methods.append({
                    "source_file": class_result.get("source_file"),
                    "class": class_result.get("class"),
                    "signature": method.get("signature"),
                    "documentation_file": method.get("documentation_file")
                })

    missing_methods = [
        (class_result, method)
        for class_result in coverage.get("classes", [])
        if class_result.get("coverage") not in {"ambiguous", "unsupported"}
        for method in class_result.get("methods", [])
        if method.get("coverage") == "missing"
    ]
    selected_methods = missing_methods
    if max_methods is not None:
        selected_methods = missing_methods[:max_methods]
        if len(selected_methods) < len(missing_methods):
            errors.append({
                "stage": "method_limit",
                "file": None,
                "message": (
                    f"Generated {len(selected_methods)} of "
                    f"{len(missing_methods)} missing methods because "
                    "max_methods was reached."
                )
            })

    missing_classes = [
        class_result
        for class_result in coverage.get("classes", [])
        if class_result.get("coverage") == "missing"
    ]

    missing_class_keys = {
        (item.get("source_file"), item.get("class"))
        for item in missing_classes
    }
    selected_methods_by_class = {}
    for class_result, method in selected_methods:
        selected_methods_by_class.setdefault(
            (class_result.get("source_file"), class_result.get("class")),
            []
        ).append((class_result, method))

    for file_info in full_analysis.get("files", []):
        source_file = file_info.get("file")
        class_results = classes_by_file.get(source_file, [])
        if not source_file or not class_results:
            continue

        source, class_nodes, source_hash, source_error = _read_source_file(
            repository_root,
            source_file
        )
        if source_error:
            errors.append(source_error)
            continue
        if source is None or class_nodes is None:
            errors.append({
                "stage": "source_read",
                "file": source_file,
                "message": "Java source could not be decoded."
            })
            continue
        if source_hash:
            source_hashes[source_file] = source_hash

        for class_result in class_results:
            class_name = class_result.get("class")
            class_key = (source_file, class_name)
            class_node = class_nodes.get(class_name)
            generated_description = None

            if class_key in missing_class_keys:
                if class_node is None:
                    errors.append({
                        "stage": "class_context",
                        "file": source_file,
                        "class": class_name,
                        "message": (
                            "Parsed class source context is unavailable; "
                            "class documentation was not generated."
                        )
                    })
                else:
                    existing_docs = _safe_class_documentation(
                        repository_root,
                        class_result.get("documentation_file"),
                        class_result,
                        errors,
                        source_file
                    )
                    existing_docs = _generation_documentation_context(
                        repository_root,
                        (
                            f"Java class {class_name}, source file "
                            f"{source_file}, full documentation generation"
                        ),
                        existing_docs,
                        retrieval_state
                    )
                    class_context, class_context_complete = (
                        _class_implementation_context(
                            source,
                            class_result,
                            class_node
                        )
                    )
                    if (
                        class_context.strip()
                        == class_node.get("declaration", "").strip()
                        and not class_result.get("comment")
                    ):
                        errors.append({
                            "stage": "class_context",
                            "file": source_file,
                            "class": class_name,
                            "message": (
                                "No extracted method implementation or "
                                "class comment provides evidence for class "
                                "documentation."
                            )
                        })
                    else:
                        prompt = _class_prompt(
                            file_info,
                            class_result,
                            class_context,
                            existing_docs,
                            class_context_complete
                        )
                        generated_description, error_message = _call_model(
                            prompt,
                            "class_generation",
                            class_name,
                            provider_state
                        )
                        if error_message:
                            errors.append({
                                "stage": "class_generation",
                                "file": source_file,
                                "class": class_name,
                                "message": error_message
                            })
                            generated_description = None
                        else:
                            generated_classes.append({
                                "source_file": source_file,
                                "package": class_result.get("package"),
                                "class": class_name,
                                "identity": _class_identity(
                                    file_info,
                                    class_result
                                ),
                                "description": generated_description,
                                "start_line": class_node["start_line"],
                                "end_line": class_node["end_line"],
                                "source_context_complete": (
                                    class_context_complete
                                )
                            })
                            if not class_context_complete:
                                errors.append({
                                    "stage": "class_context",
                                    "file": source_file,
                                    "class": class_name,
                                    "message": (
                                        "Class source context was "
                                        "truncated; generated class "
                                        "description requires review."
                                    )
                                })

            for selected_class, method in selected_methods_by_class.get(
                class_key,
                []
            ):
                method_source, source_complete = _method_source(
                    source,
                    method
                )
                if method_source is None:
                    errors.append({
                        "stage": "method_context",
                        "file": source_file,
                        "class": class_name,
                        "method": method.get("signature"),
                        "message": (
                            "Method source line range is unavailable or "
                            "invalid."
                        )
                    })
                    continue

                existing_docs = _safe_class_documentation(
                    repository_root,
                    selected_class.get("documentation_file"),
                    selected_class,
                    errors,
                    source_file
                )
                existing_docs = _generation_documentation_context(
                    repository_root,
                    (
                        f"Java class {class_name}, method "
                        f"{method.get('signature')}, source file "
                        f"{source_file}, documentation for a source change"
                    ),
                    existing_docs,
                    retrieval_state
                )
                prompt = _method_prompt(
                    file_info,
                    selected_class,
                    method,
                    method_source,
                    source_complete,
                    existing_docs
                )
                documentation, error_message = _call_model(
                    prompt,
                    "method_generation",
                    f"{method.get('name')}({', '.join(
                        item.get('type') or '?'
                        for item in method.get('parameters', [])
                    )})",
                    provider_state
                )
                if error_message:
                    errors.append({
                        "stage": "method_generation",
                        "file": source_file,
                        "class": class_name,
                        "method": method.get("signature"),
                        "message": error_message
                    })
                    continue

                generated_methods.append({
                    "source_file": source_file,
                    "package": selected_class.get("package"),
                    "class": class_name,
                    "signature": method.get("signature"),
                    "method": method.get("name"),
                    "documentation": documentation,
                    "start_line": method.get("start_line"),
                    "end_line": method.get("end_line"),
                    "source_context_complete": source_complete
                })
                if not source_complete:
                    errors.append({
                        "stage": "method_context",
                        "file": source_file,
                        "class": class_name,
                        "method": method.get("signature"),
                        "message": (
                            "Method context was truncated; generated "
                            "documentation must be reviewed against the "
                            "complete implementation."
                        )
                    })

            implementation_evidence = _class_implementation_evidence(
                source,
                class_result
            )
            has_implementation_evidence = (
                implementation_evidence
                != "(No method implementation evidence was extracted.)"
            )
            if has_implementation_evidence or class_result.get("comment"):
                class_summaries.append({
                    "identity": _class_identity(file_info, class_result),
                    "summary": (
                        generated_description
                        or class_result.get("comment")
                        or "Implementation evidence is provided below."
                    ),
                    "evidence": (
                        f"{_signature_context(class_result)}\n"
                        f"Implementation evidence:\n"
                        f"{implementation_evidence}"
                    )
                })

    overview = None
    if include_repository_overview:
        if class_summaries:
            overview, overview_error = _call_model(
                _overview_prompt(class_summaries),
                "overview_generation",
                provider_state=provider_state
            )
            if overview_error:
                errors.append({
                    "stage": "overview_generation",
                    "file": None,
                    "message": overview_error
                })
        else:
            errors.append({
                "stage": "overview_generation",
                "file": None,
                "message": (
                    "No source-backed class summaries were available for "
                    "repository overview generation."
                )
            })

    has_generated_content = bool(
        generated_classes or generated_methods or overview
    )
    has_generation_errors = bool(errors)
    no_missing_documentation = not missing_classes and not missing_methods
    if (
        no_missing_documentation
        and not include_repository_overview
        and not has_generated_content
        and not has_generation_errors
    ):
        generation_status = "partial" if has_generation_errors else "complete"
        generated_markdown = (
            "# Repository Documentation\n\n"
            "No missing class or method documentation was found.\n"
        )
    elif not has_generated_content:
        generation_status = "failed"
        generated_markdown = None
        if not errors:
            errors.append({
                "stage": "generation",
                "file": None,
                "message": "No source-backed documentation could be generated."
            })
    else:
        generation_status = (
            "partial" if has_generation_errors else "complete"
        )
        generated_markdown = _render_markdown(
            overview,
            generated_classes,
            generated_methods,
            coverage.get("classes", [])
        )

    return {
        "repository": full_analysis.get("repository"),
        "documentation_target": documentation_target,
        "generated_markdown": generated_markdown,
        "generated_classes": generated_classes,
        "generated_methods": generated_methods,
        "skipped_documented_methods": skipped_documented_methods,
        "repository_overview": overview,
        "errors": errors,
        "generation_status": generation_status,
        "source_hashes": source_hashes,
        "target_hash_at_generation": target_hash_at_generation,
        "ambiguous_documentation_mappings": coverage.get(
            "ambiguous_mappings",
            []
        ),
        "retrieval": retrieval_state,
        "context_limits": {
            "method_source_characters": MAX_METHOD_SOURCE_CHARS,
            "class_source_characters": MAX_CLASS_SOURCE_CHARS,
            "retrieved_document_characters": MAX_RETRIEVED_DOCUMENT_CHARS,
            "overview_context_characters": MAX_OVERVIEW_CONTEXT_CHARS
        }
    }
