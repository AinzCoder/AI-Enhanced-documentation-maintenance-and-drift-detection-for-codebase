from pathlib import Path

from analyzer.file_scanner import scan_file
from models.repository_model import RepositoryInfo

def scan_repository(repository_path: str) -> RepositoryInfo:
    root = Path(repository_path)
    if not root.exists():
        raise FileNotFoundError(
            f"Repository does not exist: {repository_path}"
        )
    
    if not root.is_dir():
        raise NotADirectoryError(
            f"Path is not a directory: {repository_path}"
        )
    
    repository_info = RepositoryInfo(
        project_name=root.name,
        root_path=str(root)
    )

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        file_type = scan_file(file_path)
        relative_path = str(file_path.relative_to(root))

        if file_type == "source":
            repository_info.source_files.append(relative_path)

        elif file_type == "documentation":
            repository_info.documentation_files.append(relative_path)
        
        elif file_type == "configuration":
            repository_info.configuration_files.append(relative_path)
    return repository_info