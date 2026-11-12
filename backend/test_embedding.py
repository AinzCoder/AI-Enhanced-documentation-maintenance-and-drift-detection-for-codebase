from rag.embedding_generator import generate_embedding


text = "Provides order management functionality."


embedding = generate_embedding(text)


print("===== EMBEDDING =====")

print("Vector length:", len(embedding))

print("\nFirst 10 values:")

print(embedding[:10])