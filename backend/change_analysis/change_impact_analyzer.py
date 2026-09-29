from models.code_model import CodeFile


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

        old_methods = {
            method.name: method
            for method in old_class.methods
        }

        new_methods = {
            method.name: method
            for method in new_class.methods
        }

        # --------------------------------
        # METHOD ADDED
        # --------------------------------

        for method_name in new_methods.keys() - old_methods.keys():

            changes.append({
                "type": "method_added",
                "class": class_name,
                "method": method_name
            })

        # --------------------------------
        # METHOD REMOVED
        # --------------------------------

        for method_name in old_methods.keys() - new_methods.keys():

            changes.append({
                "type": "method_removed",
                "class": class_name,
                "method": method_name
            })

        # --------------------------------
        # EXISTING METHOD CHANGES
        # --------------------------------

        for method_name in old_methods.keys() & new_methods.keys():

            old_method = old_methods[method_name]
            new_method = new_methods[method_name]

            # Return type changed
            if old_method.return_type != new_method.return_type:

                changes.append({
                    "type": "return_type_changed",
                    "class": class_name,
                    "method": method_name,
                    "old_return_type": old_method.return_type,
                    "new_return_type": new_method.return_type
                })

            # Parameter count changed
            if len(old_method.parameters) != len(
                new_method.parameters
            ):

                changes.append({
                    "type": "parameters_changed",
                    "class": class_name,
                    "method": method_name,
                    "reason": "Parameter count changed"
                })

                continue

            # Parameter type changed
            for old_parameter, new_parameter in zip(
                old_method.parameters,
                new_method.parameters
            ):

                if old_parameter.type != new_parameter.type:

                    changes.append({
                        "type": "parameter_type_changed",
                        "class": class_name,
                        "method": method_name,
                        "parameter": new_parameter.name,
                        "old_type": old_parameter.type,
                        "new_type": new_parameter.type
                    })

    return changes