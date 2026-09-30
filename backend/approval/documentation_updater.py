from pathlib import Path


def update_method_documentation(
    repository_path: str,
    documentation_file: str,
    class_name: str,
    method_name: str,
    new_documentation: str
):
    repository = Path(repository_path)

    documentation_path = (
        repository / documentation_file
    )

    if not documentation_path.exists():
        raise FileNotFoundError(
            f"Documentation file not found: {documentation_path}"
        )

    content = documentation_path.read_text(
        encoding="utf-8"
    )

    # Prevent duplicate documentation
    if method_name in content:
        print(
            f"{method_name} already exists "
            "in documentation."
        )
        return False

    # Find the class section
    class_heading = f"## {class_name}"

    if class_heading not in content:
        print(
            f"Class section '{class_heading}' "
            "was not found."
        )
        return False

    # Find the beginning of the class section
    class_start = content.index(
        class_heading
    )

    # Find the next major section
    next_section = content.find(
        "\n## ",
        class_start + len(class_heading)
    )

    if next_section == -1:
        next_section = len(content)

    # Insert method documentation
    updated_content = (
        content[:next_section]
        + "\n\n"
        + new_documentation.strip()
        + "\n"
        + content[next_section:]
    )

    documentation_path.write_text(
        updated_content,
        encoding="utf-8"
    )

    return True