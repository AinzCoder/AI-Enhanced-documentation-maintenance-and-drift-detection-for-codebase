from llm.ollama_client import generate_response


prompt = """
You are an AI documentation assistant.

Explain the purpose of a Java class called OrderService
in two short paragraphs.
"""

response = generate_response(prompt)

print("AI RESPONSE:")
print(response)