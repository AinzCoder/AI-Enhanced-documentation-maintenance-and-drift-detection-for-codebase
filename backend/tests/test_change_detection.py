from analyzer.java_analyzer import analyze_java_file
from change_analysis.change_impact_analyzer import compare_code_models


def parse_java(tmp_path, file_name, source):
    java_file = tmp_path / file_name
    java_file.write_text(source, encoding="utf-8")
    return analyze_java_file(str(java_file))


def compare_java_sources(tmp_path, old_source, new_source):
    old_model = parse_java(tmp_path, "Old.java", old_source)
    new_model = parse_java(tmp_path, "New.java", new_source)
    return compare_code_models(old_model, new_model)


def find_event(changes, event_type, method=None, class_name=None):
    matches = [
        change
        for change in changes
        if change["type"] == event_type
        and (method is None or change.get("method") == method)
        and (class_name is None or change.get("class") == class_name)
    ]
    assert len(matches) == 1, (
        f"Expected one {event_type} event for "
        f"class={class_name!r}, method={method!r}; got {matches!r}"
    )
    return matches[0]


def test_method_addition_includes_new_source_position(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n}\n",
        "class Sample {\n    int added() { return 1; }\n}\n"
    )

    event = find_event(changes, "method_added", "added", "Sample")
    assert event["start_line"] == 2
    assert event["end_line"] == 2


def test_method_removal_includes_old_source_position(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int removed() { return 1; }\n}\n",
        "class Sample {\n}\n"
    )

    event = find_event(changes, "method_removed", "removed", "Sample")
    assert event["old_start_line"] == 2
    assert event["old_end_line"] == 2


def test_return_type_change_reports_old_and_new_types_and_positions(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int value() { return 1; }\n}\n",
        "class Sample {\n    long value() { return 1; }\n}\n"
    )

    event = find_event(changes, "return_type_changed", "value", "Sample")
    assert event["old_return_type"] == "int"
    assert event["new_return_type"] == "long"
    assert event["start_line"] == 2
    assert event["old_start_line"] == 2


def test_parameter_count_change_is_detected(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int sum(int left) { return left; }\n}\n",
        "class Sample {\n    int sum(int left, int right) { return left + right; }\n}\n"
    )

    event = find_event(changes, "parameters_changed", "sum", "Sample")
    assert event["reason"] == "Parameter count changed"
    assert event["start_line"] == 2
    assert event["old_start_line"] == 2


def test_parameter_type_change_reports_old_and_new_types(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int value(String input) { return 1; }\n}\n",
        "class Sample {\n    int value(Integer input) { return 1; }\n}\n"
    )

    event = find_event(
        changes,
        "parameter_type_changed",
        "value",
        "Sample"
    )
    assert event["parameter"] == "input"
    assert event["old_type"] == "String"
    assert event["new_type"] == "Integer"
    assert event["start_line"] == 2
    assert event["old_start_line"] == 2


def test_parameter_rename_reports_old_and_new_names(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int value(int before) { return before; }\n}\n",
        "class Sample {\n    int value(int after) { return after; }\n}\n"
    )

    event = find_event(
        changes,
        "parameter_name_changed",
        "value",
        "Sample"
    )
    assert event["old_parameter"] == "before"
    assert event["new_parameter"] == "after"
    assert event["start_line"] == 2
    assert event["old_start_line"] == 2


def test_changed_return_expression_reports_body_change(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int value() { return 1; }\n}\n",
        "class Sample {\n    int value() { return 2; }\n}\n"
    )

    event = find_event(changes, "method_body_changed", "value", "Sample")
    assert event["review_candidate"] is True
    assert event["start_line"] == 2
    assert event["old_start_line"] == 2


def test_changed_if_condition_reports_body_change(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int value(int input) { if (input > 0) return 1; return 0; }\n}\n",
        "class Sample {\n    int value(int input) { if (input >= 0) return 1; return 0; }\n}\n"
    )

    find_event(changes, "method_body_changed", "value", "Sample")


def test_changed_method_call_reports_body_change(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int value() { return first(); }\n}\n",
        "class Sample {\n    int value() { return second(); }\n}\n"
    )

    find_event(changes, "method_body_changed", "value", "Sample")


def test_class_addition_is_detected(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Existing {}\n",
        "class Existing {}\nclass Added {}\n"
    )

    event = find_event(changes, "class_added", class_name="Added")
    assert set(event) == {"type", "class"}


def test_class_removal_is_detected(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Existing {}\nclass Removed {}\n",
        "class Existing {}\n"
    )

    event = find_event(changes, "class_removed", class_name="Removed")
    assert set(event) == {"type", "class"}


def test_overloaded_methods_are_compared_independently(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        (
            "class Sample {\n"
            "    int value(int input) { return input; }\n"
            "    int value(String input) { return 1; }\n"
            "}\n"
        ),
        (
            "class Sample {\n"
            "    int value(int input) { return input + 1; }\n"
            "    int value(String input) { return 1; }\n"
            "}\n"
        )
    )

    body_changes = [
        change
        for change in changes
        if change["type"] == "method_body_changed"
        and change["method"] == "value"
    ]
    assert len(body_changes) == 1
    assert body_changes[0]["class"] == "Sample"
    assert body_changes[0]["start_line"] == 2


def test_multiple_java_classes_are_analyzed(tmp_path):
    model = parse_java(
        tmp_path,
        "Multiple.java",
        (
            "class First { int one() { return 1; } }\n"
            "class Second { int two() { return 2; } }\n"
        )
    )

    assert [class_info.name for class_info in model.classes] == [
        "First",
        "Second"
    ]
    assert [method.name for method in model.classes[0].methods] == ["one"]
    assert [method.name for method in model.classes[1].methods] == ["two"]


def test_added_and_modified_methods_report_new_source_positions(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int modified() { return 1; }\n}\n",
        (
            "class Sample {\n"
            "\n"
            "    int modified() { return 2; }\n"
            "    int added() { return 3; }\n"
            "}\n"
        )
    )

    modified = find_event(
        changes,
        "method_body_changed",
        "modified",
        "Sample"
    )
    added = find_event(changes, "method_added", "added", "Sample")
    assert modified["start_line"] == 3
    assert added["start_line"] == 4
    assert added["end_line"] == 4


def test_whitespace_only_body_change_is_ignored(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int value() { int result=1; return result+2; }\n}\n",
        "class Sample {\n    int value() { int result = 1; return result + 2; }\n}\n"
    )

    assert not any(
        change["type"] == "method_body_changed"
        for change in changes
    )


def test_comment_only_body_change_is_ignored(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int value() { return 1; }\n}\n",
        "class Sample {\n    int value() { /* explanatory note */ return 1; }\n}\n"
    )

    assert not any(
        change["type"] == "method_body_changed"
        for change in changes
    )


def test_string_literal_change_is_detected(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        'class Sample {\n    String value() { return "before"; }\n}\n',
        'class Sample {\n    String value() { return "after"; }\n}\n'
    )

    find_event(changes, "method_body_changed", "value", "Sample")


def test_parameter_count_change_does_not_suppress_body_change(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int sum(int left) { return left; }\n}\n",
        "class Sample {\n    int sum(int left, int right) { return left - right; }\n}\n"
    )

    find_event(changes, "parameters_changed", "sum", "Sample")
    find_event(changes, "method_body_changed", "sum", "Sample")


def test_unchanged_java_source_produces_no_changes(tmp_path):
    source = (
        "class Sample {\n"
        "    int value(int input) {\n"
        "        return input + 1;\n"
        "    }\n"
        "}\n"
    )

    assert compare_java_sources(tmp_path, source, source) == []


def test_change_events_keep_fastapi_compatible_list_of_dicts(tmp_path):
    changes = compare_java_sources(
        tmp_path,
        "class Sample {\n    int value() { return 1; }\n}\n",
        "class Sample {\n    long value() { return 2; }\n}\n"
    )

    assert isinstance(changes, list)
    assert all(isinstance(change, dict) for change in changes)
    return_change = find_event(changes, "return_type_changed", "value")
    body_change = find_event(changes, "method_body_changed", "value")
    assert return_change["class"] == "Sample"
    assert return_change["old_return_type"] == "int"
    assert return_change["new_return_type"] == "long"
    assert return_change["start_line"] == 2
    assert return_change["old_start_line"] == 2
    assert body_change["class"] == "Sample"
    assert body_change["review_candidate"] is True
    assert body_change["start_line"] == 2
    assert body_change["old_start_line"] == 2
