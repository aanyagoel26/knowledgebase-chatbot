import os

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "kb_chatbot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Aanya2612")

CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:7b")
OLLAMA_CHAT_URL = os.getenv(
    "OLLAMA_CHAT_URL",
    "http://localhost:11434/api/chat"
)

MAX_ROWS = 100
QUERY_TIMEOUT_MS = 10000

SENSITIVE_COLUMN_KEYWORDS = [
    "password",
    "pass",
    "pwd",
    "hash",
    "token",
    "secret",
    "api_key",
    "apikey",
    "key",
    "salt",
    "otp",
    "pin",
    "reset",
    "auth",
    "credential"
]