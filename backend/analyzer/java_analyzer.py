from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_java

from models.code_model import (
    Parameter,
    Method,
    Class,
    CodeFile
)


JAVA_LANGUAGE = Language(tree_sitter_java.language())

parser = Parser(JAVA_LANGUAGE)


def get_node_text(node, source_code):
    return source_code[
        node.start_byte:node.end_byte
    ].decode("utf-8")


def analyze_java_file(file_path: str) -> CodeFile:

    path = Path(file_path)

    source_code = path.read_bytes()

    tree = parser.parse(source_code)

    root_node = tree.root_node

    classes = []

    for node in root_node.children:

        if node.type != "class_declaration":
            continue

        class_name = None
        methods = []

        for child in node.children:

            if child.type == "identifier":

                class_name = get_node_text(
                    child,
                    source_code
                )

            elif child.type == "class_body":

                for class_member in child.children:

                    if class_member.type != "method_declaration":
                        continue

                    method_name = None
                    return_type = None
                    parameters = []

                    for method_child in class_member.children:

                        if method_child.type == "identifier":

                            method_name = get_node_text(
                                method_child,
                                source_code
                            )

                        elif method_child.type == "void_type":

                            return_type = get_node_text(
                                method_child,
                                source_code
                            )

                        elif method_child.type == "type_identifier":

                            return_type = get_node_text(
                                method_child,
                                source_code
                            )

                        elif method_child.type == "formal_parameters":

                            for parameter in method_child.children:

                                if parameter.type == "formal_parameter":

                                    parameter_name = None
                                    parameter_type = None

                                    for parameter_child in parameter.children:

                                        if parameter_child.type == "identifier":

                                            parameter_name = get_node_text(
                                                parameter_child,
                                                source_code
                                            )

                                        elif parameter_child.type == "type_identifier":

                                            parameter_type = get_node_text(
                                                parameter_child,
                                                source_code
                                            )

                                        elif parameter_child.type == "integral_type":

                                            parameter_type = get_node_text(
                                                parameter_child,
                                                source_code
                                            )

                                    parameters.append(
                                        Parameter(
                                            name=parameter_name,
                                            type=parameter_type
                                        )
                                    )

                    methods.append(
                        Method(
                            name=method_name,
                            return_type=return_type,
                            parameters=parameters
                        )
                    )

        classes.append(
            Class(
                name=class_name,
                methods=methods
            )
        )

    return CodeFile(
        file_path=str(path),
        language="Java",
        classes=classes
    )