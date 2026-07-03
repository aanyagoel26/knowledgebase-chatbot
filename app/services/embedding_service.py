import requests

from app.config.settings import (
    EMBEDDING_MODEL,
    OLLAMA_EMBED_URL
)


def generate_embedding(text):
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={
            "model": EMBEDDING_MODEL,
            "prompt": text
        },
        timeout=120
    )

    if response.status_code != 200:
        print(response.text)
        raise Exception("Embedding API failed")

    return response.json()["embedding"]


def generate_embeddings_batch(texts):
    if not texts:
        return []

    try:
        response = requests.post(
            OLLAMA_EMBED_URL,
            json={
                "model": EMBEDDING_MODEL,
                "input": texts
            },
            timeout=300
        )

        if response.status_code == 200:
            data = response.json()

            if "embeddings" in data:
                return data["embeddings"]

    except Exception as error:
        print("Batch embedding failed.")
        print(error)

    embeddings = []

    for text in texts:
        embeddings.append(generate_embedding(text))

    return embeddings