import os
from dotenv import load_dotenv

load_dotenv()

APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "kb_chatbot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

OLLAMA_CHAT_URL = os.getenv("OLLAMA_CHAT_URL", "http://localhost:11434/api/chat")
OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")

CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:7b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

KNOWLEDGE_BASE_FOLDER = os.getenv("KNOWLEDGE_BASE_FOLDER", "knowledge_base")
UI_FILE = os.getenv("UI_FILE", "static/kb_chat.html")

AUTH_MODE = os.getenv("AUTH_MODE", "local")
COMPANY_EMPLOYEE_VERIFY_URL = os.getenv("COMPANY_EMPLOYEE_VERIFY_URL", "")

AUTO_SCAN_INTERVAL_SECONDS = int(os.getenv("AUTO_SCAN_INTERVAL_SECONDS", "3600"))

MAX_CHUNK_SIZE = int(os.getenv("MAX_CHUNK_SIZE", "1500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

PER_DOCUMENT_VECTOR_TOP_K = int(os.getenv("PER_DOCUMENT_VECTOR_TOP_K", "6"))
PER_DOCUMENT_KEYWORD_TOP_K = int(os.getenv("PER_DOCUMENT_KEYWORD_TOP_K", "6"))
PER_DOCUMENT_DIRECT_TOP_K = int(os.getenv("PER_DOCUMENT_DIRECT_TOP_K", "2"))
PER_DOCUMENT_CONTEXT_LIMIT = int(os.getenv("PER_DOCUMENT_CONTEXT_LIMIT", "5"))

NEIGHBOR_WINDOW = int(os.getenv("NEIGHBOR_WINDOW", "1"))
MAX_CONTEXT_CHUNKS_TOTAL = int(os.getenv("MAX_CONTEXT_CHUNKS_TOTAL", "14"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

MAX_ROWS = int(os.getenv("MAX_ROWS", "100"))
QUERY_TIMEOUT_MS = int(os.getenv("QUERY_TIMEOUT_MS", "10000"))

ALLOWED_EMPLOYEE_EMAIL_DOMAINS = [
    domain.strip()
    for domain in os.getenv(
        "ALLOWED_EMPLOYEE_EMAIL_DOMAINS",
        "@motherson.com,@mtsl.com"
    ).split(",")
    if domain.strip()
]

SENSITIVE_COLUMN_KEYWORDS = [
    "password", "pass", "pwd", "hash", "token", "secret",
    "api_key", "apikey", "key", "salt", "otp", "pin",
    "reset", "auth", "credential"
]