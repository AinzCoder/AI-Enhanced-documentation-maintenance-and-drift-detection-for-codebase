from analyzer.java_analyzer import analyze_java_file

java_file = "../test_repositories/OrderManagement/src/OrderService.java"
result = analyze_java_file(java_file)
print("File:", result.file_path)
print("Language:", result.language)

for class_info in result.classes:

    print("\nClass:", class_info.name)

    for method in class_info.methods:

        print("  Method:", method.name)
        print("    Return type:", method.return_type)

        for parameter in method.parameters:

            print(
                "    Parameter:",
                parameter.type,
                parameter.name
            )