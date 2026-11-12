from models.code_model import CodeFile


def normalizeMethodBody(body):
    tokens = []
    index = 0
    operators = (
        ">>>=", "<<=", ">>=", "...", ">>>", "::", "->", "++", "--",
        "&&", "||", "==", "!=", "<=", ">=", "+=", "-=", "*=", "/=",
        "%=", "&=", "|=", "^=", "<<", ">>", ">>>", "?."
    )

    while index < len(body):
        character = body[index]
        if character.isspace():
            index += 1
            continue

        if body.startswith("//", index):
            newline = body.find("\n", index)
            index = len(body) if newline == -1 else newline + 1
            continue

        if body.startswith("/*", index):
            comment_end = body.find("*/", index + 2)
            index = len(body) if comment_end == -1 else comment_end + 2
            continue

        if body.startswith('"""', index):
            end = body.find('"""', index + 3)
            end = len(body) if end == -1 else end + 3
            tokens.append(body[index:end])
            index = end
            continue

        if character in {'"', "'"}:
            quote = character
            end = index + 1
            while end < len(body):
                if body[end] == "\\":
                    end += 2
                elif body[end] == quote:
                    end += 1
                    break
                else:
                    end += 1
            tokens.append(body[index:end])
            index = end
            continue

        if character.isalnum() or character in {"_", "$"}:
            end = index + 1
            while end < len(body) and (
                body[end].isalnum() or body[end] in {"_", "$"}
            ):
                end += 1
            tokens.append(body[index:end])
            index = end
            continue

        operator = next(
            (item for item in operators if body.startswith(item, index)),
            None
        )
        if operator is not None:
            tokens.append(operator)
            index += len(operator)
        else:
            tokens.append(character)
            index += 1

    return tuple(tokens)


def getMethodPosition(method, oldPosition=False):
    position = {}
    if oldPosition:
        if method.start_line is not None:
            position["old_start_line"] = method.start_line
        if method.end_line is not None:
            position["old_end_line"] = method.end_line
    else:
        if method.start_line is not None:
            position["start_line"] = method.start_line
        if method.end_line is not None:
            position["end_line"] = method.end_line
    return position


def getMethodMatchCost(oldMethod, newMethod):
    oldTypes = [parameter.type for parameter in oldMethod.parameters]
    newTypes = [parameter.type for parameter in newMethod.parameters]
    sharedTypes = min(len(oldTypes), len(newTypes))
    typeChanges = sum(
        oldTypes[index] != newTypes[index]
        for index in range(sharedTypes)
    )
    countChanges = abs(len(oldTypes) - len(newTypes))
    return (
        countChanges,
        typeChanges,
        oldMethod.return_type != newMethod.return_type
    )


def matchMethods(oldMethods, newMethods):
    unmatchedOld = set(range(len(oldMethods)))
    unmatchedNew = set(range(len(newMethods)))
    matches = []

    for oldIndex, oldMethod in enumerate(oldMethods):
        for newIndex, newMethod in enumerate(newMethods):
            oldTypes = tuple(
                parameter.type for parameter in oldMethod.parameters
            )
            newTypes = tuple(
                parameter.type for parameter in newMethod.parameters
            )
            if oldTypes == newTypes and newIndex in unmatchedNew:
                matches.append((oldIndex, newIndex))
                unmatchedOld.remove(oldIndex)
                unmatchedNew.remove(newIndex)
                break

    possibleMatches = sorted(
        (
            getMethodMatchCost(oldMethods[oldIndex], newMethods[newIndex]),
            oldIndex,
            newIndex
        )
        for oldIndex in unmatchedOld
        for newIndex in unmatchedNew
    )
    for _, oldIndex, newIndex in possibleMatches:
        if oldIndex in unmatchedOld and newIndex in unmatchedNew:
            matches.append((oldIndex, newIndex))
            unmatchedOld.remove(oldIndex)
            unmatchedNew.remove(newIndex)

    return matches, unmatchedOld, unmatchedNew


def compare_code_models(
    old_model: CodeFile,
    new_model: CodeFile
):
    changes = []

    old_classes = {
        class_info.name: class_info
        for class_info in old_model.classes
    }

    new_classes = {
        class_info.name: class_info
        for class_info in new_model.classes
    }

    # --------------------------------
    # CLASS ADDITIONS
    # --------------------------------

    for class_name in new_classes:

        if class_name not in old_classes:

            changes.append({
                "type": "class_added",
                "class": class_name
            })

    # --------------------------------
    # CLASS REMOVALS
    # --------------------------------

    for class_name in old_classes:

        if class_name not in new_classes:

            changes.append({
                "type": "class_removed",
                "class": class_name
            })

    # --------------------------------
    # METHOD COMPARISON
    # --------------------------------

    for class_name in old_classes.keys() & new_classes.keys():

        old_class = old_classes[class_name]
        new_class = new_classes[class_name]

        oldMethodsByName = {}
        newMethodsByName = {}
        for method in old_class.methods:
            oldMethodsByName.setdefault(method.name, []).append(method)
        for method in new_class.methods:
            newMethodsByName.setdefault(method.name, []).append(method)

        for method_name in oldMethodsByName.keys() | newMethodsByName.keys():
            oldMethods = oldMethodsByName.get(method_name, [])
            newMethods = newMethodsByName.get(method_name, [])
            methodMatches, unmatchedOld, unmatchedNew = matchMethods(
                oldMethods,
                newMethods
            )

            for newIndex in unmatchedNew:
                newMethod = newMethods[newIndex]
                changes.append({
                    "type": "method_added",
                    "class": class_name,
                    "method": method_name,
                    **getMethodPosition(newMethod)
                })

            for oldIndex in unmatchedOld:
                oldMethod = oldMethods[oldIndex]
                changes.append({
                    "type": "method_removed",
                    "class": class_name,
                    "method": method_name,
                    **getMethodPosition(oldMethod, oldPosition=True)
                })

            for oldIndex, newIndex in methodMatches:
                old_method = oldMethods[oldIndex]
                new_method = newMethods[newIndex]
                newPosition = getMethodPosition(new_method)
                oldPosition = getMethodPosition(
                    old_method,
                    oldPosition=True
                )

                # Return type changed
                if old_method.return_type != new_method.return_type:
                    changes.append({
                        "type": "return_type_changed",
                        "class": class_name,
                        "method": method_name,
                        "old_return_type": old_method.return_type,
                        "new_return_type": new_method.return_type,
                        **newPosition,
                        **oldPosition
                    })

                # Parameter count changed
                if len(old_method.parameters) != len(new_method.parameters):
                    changes.append({
                        "type": "parameters_changed",
                        "class": class_name,
                        "method": method_name,
                        "reason": "Parameter count changed",
                        **newPosition,
                        **oldPosition
                    })

                # Parameter type and name changes
                for oldParameter, newParameter in zip(
                    old_method.parameters,
                    new_method.parameters
                ):
                    if oldParameter.type != newParameter.type:
                        changes.append({
                            "type": "parameter_type_changed",
                            "class": class_name,
                            "method": method_name,
                            "parameter": newParameter.name,
                            "old_type": oldParameter.type,
                            "new_type": newParameter.type,
                            **newPosition,
                            **oldPosition
                        })

                    if oldParameter.name != newParameter.name:
                        changes.append({
                            "type": "parameter_name_changed",
                            "class": class_name,
                            "method": method_name,
                            "old_parameter": oldParameter.name,
                            "new_parameter": newParameter.name,
                            **newPosition,
                            **oldPosition
                        })

                if (
                    old_method.body is not None
                    and new_method.body is not None
                    and normalizeMethodBody(old_method.body)
                    != normalizeMethodBody(new_method.body)
                ):
                    changes.append({
                        "type": "method_body_changed",
                        "class": class_name,
                        "method": method_name,
                        "review_candidate": True,
                        "reason": (
                            "Method implementation changed; review related "
                            "documentation."
                        ),
                        **newPosition,
                        **oldPosition
                    })

    return changes