
from pathlib import Path
import re

from approval.generation_markdown import atomic_write_markdown


def update_method_documentation(
    repository_path: str,
    documentation_file: str,
    class_name: str,
    method_name: str,
    new_documentation: str
):
    repository = Path(repository_path).expanduser().resolve()
    if not repository.exists():
        raise FileNotFoundError("Repository path does not exist.")
    if not repository.is_dir():
        raise NotADirectoryError("Repository path must be a directory.")

    relative_path = Path(documentation_file)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("Documentation file must be repository-relative.")
    documentation_path = (repository / relative_path).resolve()
    if not documentation_path.is_relative_to(repository):
        raise ValueError("Documentation file escapes the repository.")
    if documentation_path.suffix.casefold() != ".md":
        raise ValueError("Documentation target must be a Markdown file.")

    if not documentation_path.exists():
        raise FileNotFoundError(
            f"Documentation file not found: {documentation_path}"
        )
    if not documentation_path.is_file():
        raise ValueError("Documentation target must be a regular file.")

    if not new_documentation or not new_documentation.strip():
        raise ValueError("Documentation cannot be empty.")

    content = documentation_path.read_text(encoding="utf-8")

    # Find the class heading.
    class_pattern = re.compile(
        rf"(?m)^##\s+{re.escape(class_name)}\s*$"
    )
    class_match = class_pattern.search(content)

    if not class_match:
        raise ValueError(f"Class section '{class_name}' was not found.")

    class_start = class_match.start()

    # Find the end of this class section.
    next_class = re.search(
        r"(?m)^##\s+",
        content[class_match.end():]
    )

    class_end = (
        class_match.end() + next_class.start()
        if next_class
        else len(content)
    )

    class_content = content[class_start:class_end]

    # Match headings with or without method parameters.
    method_pattern = re.compile(
        rf"(?m)^###\s+{re.escape(method_name)}\s*(?:\(.*\))?\s*$",
        re.IGNORECASE
    )

    matches = list(method_pattern.finditer(class_content))
    replacement = new_documentation.strip()

    if matches:
        # Replace the first matching method section.
        first = matches[0]

        next_heading = re.search(
            r"(?m)^#{1,3}\s+",
            class_content[first.end():]
        )

        method_end = (
            first.end() + next_heading.start()
            if next_heading
            else len(class_content)
        )

        updated_class = (
            class_content[:first.start()]
            + replacement
            + "\n\n"
            + class_content[method_end:].lstrip("\n")
        )

        # Remove duplicate entries for this same method.
        duplicate_matches = list(
            method_pattern.finditer(updated_class)
        )

        if len(duplicate_matches) > 1:
            for duplicate in reversed(duplicate_matches[1:]):
                following = re.search(
                    r"(?m)^#{1,3}\s+",
                    updated_class[duplicate.end():]
                )

                end = (
                    duplicate.end() + following.start()
                    if following
                    else len(updated_class)
                )

                updated_class = (
                    updated_class[:duplicate.start()]
                    + updated_class[end:].lstrip("\n")
                )

    else:
        # New method: append it inside the class section.
        updated_class = (
            class_content.rstrip()
            + "\n\n"
            + replacement
            + "\n"
        )

    updated_content = (
        content[:class_start]
        + updated_class
        + content[class_end:]
    )

    atomic_write_markdown(documentation_path, updated_content)

    return True
