from dataclasses import dataclass, field

@dataclass
class RepositoryInfo:
    project_name:str
    root_path:str

    source_files: list[str] = field(default_factory=list)
    documentation_files: list[str] = field(default_factory=list)
    configuration_files: list[str] = field(default_factory=list)