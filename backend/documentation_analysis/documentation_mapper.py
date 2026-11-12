from pathlib import Path
from timing import timed


@timed("documentation.mapping_scan")
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
            ".md", ".txt", ".rst"
        }:
            continue

        # Ignore Git and virtual environment documentation.
        if any(
            part in {".git", ".venv", "venv", "node_modules"}
            for part in file_path.parts
        ):
            continue

        documentation_files.append(file_path)

    matches = []

    for documentation_file in documentation_files:

        try:
            content = documentation_file.read_text(
                encoding="utf-8"
            )
        except (UnicodeDecodeError, OSError):
            continue

        # Match by content when possible.
        if code_name in content.lower():
            matches.append(
                str(documentation_file.relative_to(repository))
            )

    # Important: retain empty documentation files as candidates.
    # An empty API.md cannot mention OrderService, but it still
    # needs to be checked for documentation drift.
    if not matches:
        matches = [
            str(file.relative_to(repository))
            for file in documentation_files
        ]

    return matches