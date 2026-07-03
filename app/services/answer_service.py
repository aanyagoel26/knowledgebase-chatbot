import requests

from app.config.settings import (
    CHAT_MODEL,
    OLLAMA_CHAT_URL
)


def build_context(chunks):
    context_parts = []

    for index, chunk in enumerate(chunks, start=1):
        context_parts.append(
            f"Source {index}\n"
            f"Document ID: {chunk['document_id']}\n"
            f"File: {chunk['filename']}\n"
            f"Chunk: {chunk['chunk_number']}\n"
            f"Content:\n{chunk['content']}"
        )

    return "\n\n-------------------------\n\n".join(context_parts)


def generate_answer(question, chunks):
    context = build_context(chunks)

    system_prompt = """
You are a strict enterprise knowledge-base assistant.

Use only the given knowledge base content.

Rules:
- Answer only from the given content.
- Do not use outside knowledge.
- Do not guess missing facts.
- Do not invent names, numbers, dates, policies, rules, or facts.
- If multiple documents are provided, consider all documents.
- Do not ignore a document unless no relevant content from that document is present.
- If different documents provide different information, mention it document-wise.
- If multiple related points are present, include all relevant points.
- If the exact answer is spread across multiple chunks, combine them into one complete answer.
- If the question is vague, summarize the most relevant information from all provided documents.
- Keep the answer clear, professional, and structured.
- Do not say "based on context" or "retrieved chunks".
"""

    user_prompt = f"""
Knowledge base content:
{context}

User question:
{question}

Give the final answer only.
"""

    response = requests.post(
        OLLAMA_CHAT_URL,
        json={
            "model": CHAT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            "stream": False
        },
        timeout=180
    )

    if response.status_code != 200:
        print(response.text)
        raise Exception("Chat model failed")

    return response.json()["message"]["content"].strip()