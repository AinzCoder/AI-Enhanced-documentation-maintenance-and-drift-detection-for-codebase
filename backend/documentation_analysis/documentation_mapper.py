from pathlib import Path


def map_code_to_documentation(
    repository_path: str,
    code_file: str
):
    repository = Path(repository_path)

    code_path = Path(code_file)

    code_name = code_path.stem.lower()

    documentation_files = []

    for file_path in repository.rglob("*"):

        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in {
            ".md",
            ".txt",
            ".rst"
        }:
            continue

        documentation_files.append(file_path)

    matches = []

    for documentation_file in documentation_files:

        try:
            content = documentation_file.read_text(
                encoding="utf-8"
            )

        except UnicodeDecodeError:
            continue

        if code_name in content.lower():

            matches.append(
                str(documentation_file.relative_to(repository))
            )

    return matches