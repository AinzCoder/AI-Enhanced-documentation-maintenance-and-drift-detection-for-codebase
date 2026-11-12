import re
import tempfile
from pathlib import Path

from documentation_analysis.documentation_coverage import (
    _class_title_matches,
    _is_method_heading_scope,
    _plain_heading,
    _signature_parameter_types
)


class AmbiguousDocumentationMapping(ValueError):
    pass


def _headings(content: str) -> list[dict]:
    result = []
    fence_character = None
    fence_length = 0
    offset = 0
    for line_number, line in enumerate(content.splitlines(keepends=True), 1):
        fence = re.match(r"^[ \t]*(`{3,}|~{3,})", line)
        if fence:
            marker = fence.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
        elif fence_character is None:
            match = re.match(
                r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*(?:\r?\n)?$",
                line
            )
            if match:
                result.append({
                    "level": len(match.group(1)),
                    "title": _plain_heading(match.group(2)),
                    "line": line_number,
                    "start": offset,
                    "end": offset + len(line)
                })
        offset += len(line)
    return result


def _class_heading_matches(title: str, class_item: dict) -> bool:
    class_name = class_item["class"]
    package_name = class_item.get("package")
    candidates = {class_name, class_item.get("identity", "")}
    if package_name:
        candidates.add(f"{package_name}.{class_name}")
    return title.strip() in candidates or _class_title_matches(
        title.strip(),
        {"name": class_name, "package": package_name},
        class_item.get("source_file", "")
    )


def _class_section(
    content: str,
    class_item: dict
) -> tuple[dict | None, list[dict], int]:
    headings = _headings(content)
    matches = [
        heading for heading in headings
        if _class_heading_matches(heading["title"], class_item)
    ]
    if len(matches) > 1:
        raise AmbiguousDocumentationMapping(
            f"Multiple documentation sections match class "
            f"'{class_item['class']}'."
        )
    if not matches:
        return None, headings, len(content)

    class_heading = matches[0]
    section_end = len(content)
    for heading in headings:
        if (
            heading["start"] > class_heading["start"]
            and heading["level"] <= class_heading["level"]
        ):
            section_end = heading["start"]
            break
    children = [
        heading for heading in headings
        if class_heading["start"] < heading["start"] < section_end
        and heading["level"] > class_heading["level"]
    ]
    return class_heading, children, section_end


def _method_types(title: str, method_name: str):
    return _signature_parameter_types(title, method_name)


def _has_method_heading(
    content: str,
    class_heading: dict,
    class_children: list[dict],
    section_end: int,
    method_item: dict,
    class_item: dict
) -> bool:
    signature = method_item.get("signature", "")
    match = re.match(r"^([A-Za-z_$][\w$]*)\s*\((.*)\)$", signature)
    if match is None:
        raise ValueError(
            f"Generated method signature is invalid: {signature!r}."
        )
    method_name = match.group(1)
    expected_types = _method_types(signature, method_name)
    if expected_types is None:
        raise ValueError(
            f"Generated method signature is invalid: {signature!r}."
        )

    matching = []
    ancestors = []
    for heading in class_children:
        if heading["level"] <= class_heading["level"]:
            continue
        while ancestors and ancestors[-1]["level"] >= heading["level"]:
            ancestors.pop()
        if not _is_method_heading_scope(ancestors):
            ancestors.append(heading)
            continue
        heading_types = _signature_parameter_types(
            heading["title"], method_name,
            class_item.get("class"), class_item.get("package")
        )
        if heading_types is not None and tuple(heading_types) == tuple(
            expected_types
        ):
            matching.append(heading)
        ancestors.append(heading)
    if len(matching) > 1:
        raise AmbiguousDocumentationMapping(
            f"Multiple documentation headings match method '{signature}'."
        )
    return bool(matching)


def _source_line(item: dict) -> str:
    start_line = item.get("start_line")
    end_line = item.get("end_line")
    if start_line is None or end_line is None:
        return f"- `{item.get('source_file')}`"
    return (
        f"- `{item.get('source_file')}` lines "
        f"{start_line}–{end_line}"
    )


def _append_block(content: str, block: str) -> str:
    content = content.rstrip()
    if not content:
        return block.strip() + "\n"
    return content + "\n\n" + block.strip() + "\n"


def _insert_class_description(
    content: str,
    class_heading: dict,
    section_end: int,
    class_item: dict
) -> str:
    description = class_item.get("description", "").strip()
    source = _source_line(class_item)
    block = f"{description}\n\n**Source**\n{source}"
    insertion_point = class_heading["end"]
    content = (
        content[:insertion_point]
        + "\n"
        + block
        + "\n"
        + content[insertion_point:]
    )
    return content


def _append_methods(
    content: str,
    class_heading: dict,
    section_end: int,
    class_children: list[dict],
    methods: list[dict]
) -> str:
    method_level = class_heading["level"] + 1
    if method_level > 6:
        raise ValueError(
            "The existing class heading is too deep to add method headings."
        )

    blocks = []
    for method in methods:
        blocks.extend([
            f"{'#' * method_level} {method['signature']}",
            method["documentation"].strip(),
            "**Source**",
            _source_line(method)
        ])
    block = "\n\n".join(blocks)
    insertion_point = section_end
    prefix = content[:insertion_point].rstrip()
    suffix = content[insertion_point:].lstrip("\r\n")
    if suffix:
        return prefix + "\n\n" + block + "\n\n" + suffix
    return prefix + "\n\n" + block + "\n"


def merge_generated_documentation(
    existing_content: str,
    record: dict
) -> str:
    content = existing_content
    if not content.strip():
        content = "# Repository Documentation\n"

    overview = record.get("repository_overview")
    if overview and not any(
        heading["level"] == 2
        and heading["title"].strip().lower() == "overview"
        for heading in _headings(content)
    ):
        content = _append_block(
            content,
            f"## Overview\n\n{overview.strip()}"
        )

    generated_classes = record.get("generated_classes", [])
    generated_methods = record.get("generated_methods", [])
    class_keys = {
        (item.get("source_file"), item.get("class"))
        for item in generated_classes
    }
    identities = {}
    for item in generated_classes:
        key = item.get("class")
        identity = (
            item.get("source_file"),
            item.get("identity")
            or item.get("package")
            or item.get("class")
        )
        identities.setdefault(key, set()).add(identity)
    for item in generated_methods:
        class_key = (item.get("source_file"), item.get("class"))
        if class_key not in class_keys:
            identities.setdefault(item.get("class"), set()).add(class_key)
    duplicate_class_names = [
        name for name, items in identities.items()
        if len(items) > 1
    ]
    if duplicate_class_names:
        raise AmbiguousDocumentationMapping(
            "Generated class names are not unique in the target: "
            + ", ".join(sorted(duplicate_class_names))
        )

    classes_by_key = {
        (item.get("source_file"), item.get("class")): item
        for item in generated_classes
    }
    methods_by_key = {}
    for method in generated_methods:
        methods_by_key.setdefault(
            (method.get("source_file"), method.get("class")),
            []
        ).append(method)

    ordered_keys = list(dict.fromkeys(
        [
            (item.get("source_file"), item.get("class"))
            for item in generated_classes
        ] + [
            (item.get("source_file"), item.get("class"))
            for item in generated_methods
        ]
    ))

    for class_key in ordered_keys:
        source_file, class_name = class_key
        class_item = classes_by_key.get(class_key)
        methods = methods_by_key.get(class_key, [])
        class_item = dict(class_item or {})
        class_item.setdefault("class", class_name)
        class_item.setdefault("source_file", source_file)
        if methods:
            class_item.setdefault("package", methods[0].get("package"))

        class_heading, class_children, section_end = _class_section(
            content,
            class_item
        )
        if class_heading is None:
            classes_heading = next(
                (
                    heading for heading in _headings(content)
                    if heading["level"] == 2
                    and heading["title"].strip().lower() == "classes"
                ),
                None
            )
            heading_level = 3
            class_block = [f"{'#' * heading_level} {class_name}"]
            if class_item.get("description"):
                class_block.extend([
                    "",
                    class_item["description"].strip(),
                    "",
                    "**Source**",
                    _source_line(class_item)
                ])
            else:
                class_block.extend([
                    "",
                    f"**Source file:** `{source_file}`"
                ])
            parent_block = "\n".join(class_block)
            if classes_heading is None:
                content = _append_block(
                    content,
                    "## Classes\n\n" + parent_block
                )
            else:
                _, _, classes_end = _class_section(
                    content,
                    {
                        "class": "Classes",
                        "identity": "Classes"
                    }
                )
                content = _append_block(
                    content[:classes_end],
                    parent_block
                ) + (
                    "\n" + content[classes_end:].lstrip("\r\n")
                    if content[classes_end:].strip()
                    else ""
                )
            class_heading, class_children, section_end = _class_section(
                content,
                class_item
            )

        if class_heading is None:
            raise ValueError(
                f"Unable to create a section for class '{class_name}'."
            )

        if class_item.get("description"):
            first_child_start = min(
                (
                    heading["start"]
                    for heading in class_children
                    if heading["start"] > class_heading["start"]
                ),
                default=section_end
            )
            class_description = content[
                class_heading["end"]:first_child_start
            ]
            if not class_description.strip():
                content = _insert_class_description(
                    content,
                    class_heading,
                    section_end,
                    class_item
                )
                class_heading, class_children, section_end = _class_section(
                    content,
                    class_item
                )

        new_methods = [
            method for method in methods
            if not _has_method_heading(
                content,
                class_heading,
                class_children,
                section_end,
                method,
                class_item
            )
        ]
        if new_methods:
            content = _append_methods(
                content,
                class_heading,
                section_end,
                class_children,
                new_methods
            )

    result = content.rstrip() + "\n"
    result.encode("utf-8").decode("utf-8")
    if not result.strip():
        raise ValueError("Approved Markdown must not be empty.")
    if sum(
        1 for heading in _headings(result)
        if heading["level"] == 1
        and heading["title"].strip() == "Repository Documentation"
    ) > 1:
        raise ValueError("Document contains duplicate repository title headings.")
    return result


def atomic_write_markdown(destination: Path, content: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            import os
            os.fsync(temporary_file.fileno())

        written_content = temporary_path.read_text(encoding="utf-8")
        if written_content != content or not written_content.strip():
            raise OSError("Temporary Markdown validation failed.")
        temporary_path.replace(destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
