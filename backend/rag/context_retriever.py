from pathlib import Path


def retrieve_context(
    repository_path: str,
    code_file: str,
    documentation_files: list[str],
    class_name: str,
    method_name: str
):
    repository = Path(repository_path)

    context = {
        "code": None,
        "documentation": [],
        "method": method_name,
        "class": class_name
    }

    # --------------------------------
    # Retrieve source code
    # --------------------------------

    code_path = repository / code_file

    if code_path.exists():

        try:

            code_content = code_path.read_text(
                encoding="utf-8"
            )

            context["code"] = code_content

        except UnicodeDecodeError:
            pass

    # --------------------------------
    # Retrieve documentation
    # --------------------------------

    for documentation_file in documentation_files:

        documentation_path = (
            repository / documentation_file
        )

        if not documentation_path.exists():
            continue

        try:

            documentation_content = (
                documentation_path.read_text(
                    encoding="utf-8"
                )
            )

            context["documentation"].append({
                "file": documentation_file,
                "content": documentation_content
            })

        except UnicodeDecodeError:
            continue

    return context