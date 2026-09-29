from pathlib import Path


def detect_documentation_drift(
    repository_path: str,
    documentation_files: list[str],
    changes: list[dict]
):
    repository = Path(repository_path)

    drift_results = []

    for change in changes:

        change_type = change["type"]

        class_name = change.get("class")
        method_name = change.get("method")

        # --------------------------------
        # METHODS THAT MUST BE DOCUMENTED
        # --------------------------------

        if change_type in {
            "method_added",
            "method_removed",
            "return_type_changed",
            "parameters_changed",
            "parameter_type_changed"
        }:

            method_documented = False

            for documentation_file in documentation_files:

                documentation_path = (
                    repository / documentation_file
                )

                try:
                    content = documentation_path.read_text(
                        encoding="utf-8"
                    )

                except UnicodeDecodeError:
                    continue

                if method_name.lower() in content.lower():

                    method_documented = True

                    break

            # --------------------------------
            # DOCUMENTATION MISSING
            # --------------------------------

            if not method_documented:

                drift_results.append({
                    "type": "documentation_drift",
                    "change_type": change_type,
                    "class": class_name,
                    "method": method_name,
                    "reason": "Method is not documented"
                })

            # --------------------------------
            # DOCUMENTATION MAY BE OUTDATED
            # --------------------------------

            elif change_type in {
                "return_type_changed",
                "parameters_changed",
                "parameter_type_changed"
            }:

                drift_results.append({
                    "type": "documentation_drift",
                    "change_type": change_type,
                    "class": class_name,
                    "method": method_name,
                    "reason": "Existing documentation may be outdated"
                })

    return drift_results