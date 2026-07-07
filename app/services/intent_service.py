import json

import requests

from app.config.settings import CHAT_MODEL, OLLAMA_CHAT_URL


INTENT_BASIC_CHAT = "basic_chat"
INTENT_SUMMARY = "summary"
INTENT_KNOWLEDGE_QUERY = "knowledge_query"
INTENT_DATABASE_QUERY = "database_query"


def detect_intent(question, assistant_mode="knowledge"):
    system_prompt = """
You are an intent classifier for an enterprise assistant.

Classify the user's message into exactly one intent.

Available intents:
- basic_chat: greetings, thanks, goodbye, casual conversation, readiness checks, small talk, general assistant conversation.
- summary: user asks to summarize, give overview, brief, short note, explain selected document.
- knowledge_query: user asks something that should be answered from uploaded/indexed documents.
- database_query: user asks something that requires querying database tables, records, counts, employees, departments, rows, stored data.

Rules:
- Return only valid JSON.
- Do not explain.
- JSON format: {"intent": "..."}
"""

    user_prompt = f"""
Assistant mode: {assistant_mode}
User message: {question}
"""

    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False
            },
            timeout=60
        )

        if response.status_code != 200:
            return fallback_intent(question, assistant_mode)

        content = response.json()["message"]["content"].strip()
        content = content.replace("```json", "").replace("```", "").strip()

        data = json.loads(content)
        intent = data.get("intent", "").strip()

        allowed = {
            INTENT_BASIC_CHAT,
            INTENT_SUMMARY,
            INTENT_KNOWLEDGE_QUERY,
            INTENT_DATABASE_QUERY
        }

        if intent in allowed:
            return intent

        return fallback_intent(question, assistant_mode)

    except Exception:
        return fallback_intent(question, assistant_mode)


def fallback_intent(question, assistant_mode="knowledge"):
    q = question.lower().strip()

    summary_words = [
        "summary",
        "summarize",
        "summarise",
        "overview",
        "brief",
        "short note"
    ]

    if any(word in q for word in summary_words):
        return INTENT_SUMMARY

    if assistant_mode == "database":
        return INTENT_DATABASE_QUERY

    return INTENT_KNOWLEDGE_QUERY


def generate_basic_chat_answer(question, assistant_mode="knowledge"):
    system_prompt = """
You are a helpful enterprise assistant.

Reply naturally to casual/basic conversation.
Do not mention sources.
Do not mention database.
Do not mention documents unless the user asks what you can help with.
Keep response short and professional.
"""

    user_prompt = f"""
Assistant mode: {assistant_mode}
User message: {question}
"""

    try:
        response = requests.post(
            OLLAMA_CHAT_URL,
            json={
                "model": CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False
            },
            timeout=60
        )

        if response.status_code != 200:
            return "I'm here and ready to help."

        return response.json()["message"]["content"].strip()

    except Exception:
        return "I'm here and ready to help."


def is_basic_chat_intent(intent):
    return intent == INTENT_BASIC_CHAT


def is_summary_intent(intent):
    return intent == INTENT_SUMMARY