from analyzer.java_analyzer import analyze_java_file

java_file = "../test_repositories/OrderManagement/src/OrderService.java"
result = analyze_java_file(java_file)
print("File:", result.file_path)
print("Language:", result.language)

for class_info in result.classes:

    print("\nClass:", class_info.name)

    for method in class_info.methods:
        print(f"  Method: {method.name}")
        print(f"    Return type: {method.return_type}")
        print(f"    Comment: {method.comment}")

        for parameter in method.parameters:
            print(
                f"    Parameter: "
                f"{parameter.type} {parameter.name}"
            )