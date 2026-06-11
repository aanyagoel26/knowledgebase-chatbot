from fastapi import FastAPI
from fastapi.responses import FileResponse
import psycopg2
import os

app = FastAPI()

DB_HOST = "localhost"
DB_NAME = "kb_chatbot"
DB_USER = "postgres"
DB_PASSWORD = "Aanya2612"

UI_FILE = "kb_chat.html"


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


@app.get("/")
def home():
    return FileResponse(UI_FILE)


@app.get("/health")
def health_check():
    return {
        "status": "Backend is running"
    }


@app.get("/db-check")
def db_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            "database": "connected",
            "tables": [row[0] for row in rows]
        }

    except Exception as error:
        return {
            "database": "connection failed",
            "error": str(error)
        }