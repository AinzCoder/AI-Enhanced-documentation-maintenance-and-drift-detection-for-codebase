from dataclasses import dataclass, field


@dataclass
class Parameter:
    name: str
    type: str


@dataclass
class Method:
    name: str
    return_type: str
    parameters: list[Parameter] = field(default_factory=list)


@dataclass
class Class:
    name: str
    methods: list[Method] = field(default_factory=list)


@dataclass
class CodeFile:
    file_path: str
    language: str
    classes: list[Class] = field(default_factory=list)