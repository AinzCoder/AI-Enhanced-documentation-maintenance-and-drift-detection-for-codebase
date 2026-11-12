from rag.chunker import chunk_file


file_path = "../test_repositories/OrderManagement/docs/API.md"


chunks = chunk_file(
    file_path,
    chunk_size=100
)


print("===== CHUNKS =====")

for index, chunk in enumerate(chunks):

    print(f"\n--- Chunk {index + 1} ---")

    print(chunk)