from pathlib import Path


def show_documentation_suggestion(
    suggestion: str
):

    print("\n========================================")
    print("      DOCUMENTATION UPDATE SUGGESTION")
    print("========================================")

    print(suggestion)

    print("\n========================================")
    print("Options:")
    print("1. Approve")
    print("2. Reject")
    print("3. Edit")
    print("========================================")

    choice = input("Enter your choice: ").strip()

    if choice == "1":
        return "approved", suggestion

    elif choice == "2":
        return "rejected", None

    elif choice == "3":

        print("\nEnter the edited documentation.")
        print("Type END on a new line when finished.\n")

        lines = []

        while True:

            line = input()

            if line == "END":
                break

            lines.append(line)

        edited_documentation = "\n".join(lines)

        return "edited", edited_documentation

    else:

        print("Invalid choice.")

        return "rejected", None