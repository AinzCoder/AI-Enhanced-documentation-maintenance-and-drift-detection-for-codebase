from pathlib import Path
from bisect import bisect_right

from tree_sitter import Language, Parser
import tree_sitter_java
from timing import timed

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


def clean_comment(comment: str):
    """
    Converts Java comments/Javadoc into clean text.
    """

    comment = comment.strip()

    if comment.startswith("/**"):
        comment = comment[3:]

    elif comment.startswith("/*"):
        comment = comment[2:]

    if comment.endswith("*/"):
        comment = comment[:-2]

    lines = comment.splitlines()

    cleaned_lines = []

    for line in lines:
        line = line.strip()

        if line.startswith("*"):
            line = line[1:].strip()

        if line.startswith("@"):
            continue

        if line:
            cleaned_lines.append(line)

    return " ".join(cleaned_lines).strip()


def get_previous_comment(node, source_code):
    """
    Finds the comment immediately before a class or method.
    """

    previous = node.prev_sibling

    if previous is None:
        return None

    if previous.type in {
        "comment",
        "line_comment",
        "block_comment"
    }:
        comment = get_node_text(
            previous,
            source_code
        )

        return clean_comment(comment)

    return None


def getFieldText(node, fieldName, sourceCode):
    fieldNode = node.child_by_field_name(fieldName)
    if fieldNode is None:
        return None
    return get_node_text(fieldNode, sourceCode)


def getParameterName(parameterNode, sourceCode):
    name = getFieldText(parameterNode, "name", sourceCode)
    if name is not None:
        return name

    for child in parameterNode.children:
        if child.type == "variable_declarator":
            nameNode = child.child_by_field_name("name")
            if nameNode is not None:
                return get_node_text(nameNode, sourceCode)

    return None


def getParameterType(parameterNode, sourceCode):
    typeNode = parameterNode.child_by_field_name("type")
    if typeNode is not None:
        parameterType = get_node_text(typeNode, sourceCode)
    else:
        typeNode = next(
            (
                child
                for child in parameterNode.children
                if child.type not in {
                    "variable_declarator",
                    "modifiers",
                    "annotation"
                }
            ),
            None
        )
        parameterType = (
            get_node_text(typeNode, sourceCode)
            if typeNode is not None
            else None
        )

    if parameterType and parameterNode.type == "spread_parameter":
        parameterType += "..."

    return parameterType


def source_line_starts(source_code):
    # Avoid Tree-sitter Point access, which can crash the Windows Python binding.
    return [0] + [
        index + 1 for index, byte in enumerate(source_code) if byte == 10
    ]


def source_line_range(node, line_starts):
    startLine = bisect_right(line_starts, node.start_byte)
    endLine = bisect_right(line_starts, node.end_byte)
    if node.end_byte == line_starts[endLine - 1] and endLine > startLine:
        endLine -= 1
    return startLine, endLine


def getSyntaxError(node):
    if node.type == "ERROR" or node.is_missing:
        return node

    for child in node.children:
        syntaxError = getSyntaxError(child)
        if syntaxError is not None:
            return syntaxError

    return None


def analyzeClassNode(classNode, sourceCode, lineStarts, enclosingName=None):
    simpleName = getFieldText(classNode, "name", sourceCode)
    className = (
        f"{enclosingName}.{simpleName}"
        if enclosingName
        else simpleName
    )
    classBody = classNode.child_by_field_name("body")
    methods = []
    nestedClasses = []

    if classBody is not None:
        for member in classBody.children:
            if member.type == "method_declaration":
                methodName = getFieldText(member, "name", sourceCode)
                returnType = getFieldText(member, "type", sourceCode)
                parameterNode = member.child_by_field_name("parameters")
                parameters = []

                if parameterNode is not None:
                    for parameterNodeChild in parameterNode.children:
                        if parameterNodeChild.type not in {
                            "formal_parameter",
                            "spread_parameter"
                        }:
                            continue

                        parameters.append(
                            Parameter(
                                name=getParameterName(
                                    parameterNodeChild,
                                    sourceCode
                                ),
                                type=getParameterType(
                                    parameterNodeChild,
                                    sourceCode
                                )
                            )
                        )

                bodyNode = member.child_by_field_name("body")
                startLine, endLine = source_line_range(member, lineStarts)
                methods.append(
                    Method(
                        name=methodName,
                        return_type=returnType,
                        parameters=parameters,
                        comment=get_previous_comment(member, sourceCode),
                        body=(
                            get_node_text(bodyNode, sourceCode)
                            if bodyNode is not None
                            else None
                        ),
                        start_line=startLine,
                        end_line=endLine
                    )
                )
            elif member.type in {
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "record_declaration",
                "annotation_type_declaration"
            }:
                nestedClasses.append(
                    analyzeClassNode(
                        member,
                        sourceCode,
                        lineStarts,
                        className
                    )
                )

    return [
        Class(
            name=className,
            methods=methods,
            comment=get_previous_comment(classNode, sourceCode)
        ),
        *(
            nestedClass
            for nestedClassTree in nestedClasses
            for nestedClass in nestedClassTree
        )
    ]


@timed("tree_sitter.java_analysis")
def analyze_java_file(
    file_path: str,
    source_code: bytes | None = None
) -> CodeFile:

    path = Path(file_path)

    if source_code is None:
        source_code = path.read_bytes()

    tree = parser.parse(source_code)
    root_node = tree.root_node
    line_starts = source_line_starts(source_code)
    if root_node.has_error:
        syntaxError = getSyntaxError(root_node)
        if syntaxError is None:
            raise ValueError(
                f"Java parsing failed for '{path}'; Tree-sitter reported "
                "a syntax error without an error node."
            )
        error_line = bisect_right(line_starts, syntaxError.start_byte)
        error_column = syntaxError.start_byte - line_starts[error_line - 1] + 1
        raise ValueError(
            f"Java syntax error in '{path}' at line "
            f"{error_line}, column {error_column} "
            f"(Tree-sitter node: {syntaxError.type})."
        )

    classNodeTypes = {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "annotation_type_declaration"
    }
    classes = [
        classInfo
        for classNode in root_node.children
        if classNode.type in classNodeTypes
        for classInfo in analyzeClassNode(classNode, source_code, line_starts)
    ]

    return CodeFile(
        file_path=str(path),
        language="Java",
        classes=classes
    )