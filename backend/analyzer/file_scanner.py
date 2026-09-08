from pathlib import Path

SOURCE_EXTENSIONS={
    ".java",".python",".js",".ts",".jsx",".tsx"
}

DOCUMENTATION_EXTENSIONS = {
    ".md",".txt",".rst"
}

CONFIGURATION_FILES = {
    "pom.xml",
    "build.gradle",
    "package.json",
    "Dockerfile",
    "docker-compose.yml",
    "application.properties",
    "application.yml"
}

def scan_file(file_path: Path) -> str:
    if file_path.suffix.lower() in SOURCE_EXTENSIONS:
        return "source"
    if file_path.suffix.lower() in DOCUMENTATION_EXTENSIONS:
        return "documentation"
    if file_path.name.lower() in CONFIGURATION_FILES:
        return "configuration"
    return "other"