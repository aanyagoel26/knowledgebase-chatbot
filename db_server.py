import os
import re
import time
import json
import psycopg2
import requests

# ============================================================
# DATABASE CONFIG
# ============================================================

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "kb_chatbot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Aanya2612")

# ============================================================
# MODEL CONFIG
# ============================================================

CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:7b")
OLLAMA_CHAT_URL = os.getenv(
    "OLLAMA_CHAT_URL",
    "http://localhost:11434/api/chat"
)

MAX_ROWS = 100


# ============================================================
# DATABASE CONNECTION
# ============================================================

class DatabaseConnection:
    def get_connection(self):
        return psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )


# ============================================================
# SCHEMA READER
# ============================================================

class SchemaReader:
    def __init__(self):
        self.db = DatabaseConnection()

    def read_schema(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name;
            """
        )

        table_rows = cursor.fetchall()
        schema = []

        for table_row in table_rows:
            table_name = table_row[0]

            cursor.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position;
                """,
                (table_name,)
            )

            column_rows = cursor.fetchall()

            schema.append(
                {
                    "table_name": table_name,
                    "columns": [
                        {
                            "column_name": col[0],
                            "data_type": col[1]
                        }
                        for col in column_rows
                    ]
                }
            )

        cursor.close()
        conn.close()

        return schema

    def schema_as_text(self, schema):
        lines = []

        for table in schema:
            columns = []

            for column in table["columns"]:
                columns.append(
                    f"{column['column_name']} {column['data_type']}"
                )

            lines.append(
                f"{table['table_name']}({', '.join(columns)})"
            )

        return "\n".join(lines)


# ============================================================
# SQL GENERATOR
# ============================================================

class SQLGenerator:
    def generate_sql(self, question, schema_text):
        system_prompt = """
You are a PostgreSQL SQL generator.

Rules:
- Generate only one SQL query.
- Use only SELECT queries.
- Do not generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE.
- Use only the tables and columns provided in the schema.
- If the user asks for all records, still add LIMIT 100.
- Prefer readable column aliases.
- Do not include markdown.
- Do not explain the query.
"""

        user_prompt = f"""
Database schema:
{schema_text}

User question:
{question}

Return only the SQL query.
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
            raise Exception("SQL generation failed: " + response.text)

        sql = response.json()["message"]["content"].strip()
        sql = sql.replace("```sql", "")
        sql = sql.replace("```", "")
        sql = sql.strip()

        return sql


# ============================================================
# SQL VALIDATOR
# ============================================================

class SQLValidator:
    def validate(self, sql):
        sql_clean = sql.strip().lower()

        if not sql_clean:
            raise Exception("Empty SQL query generated.")

        if ";" in sql_clean[:-1]:
            raise Exception("Multiple SQL statements are not allowed.")

        blocked_words = [
            "insert",
            "update",
            "delete",
            "drop",
            "alter",
            "create",
            "truncate",
            "grant",
            "revoke",
            "copy",
            "execute"
        ]

        for word in blocked_words:
            pattern = r"\b" + word + r"\b"
            if re.search(pattern, sql_clean):
                raise Exception(f"Blocked unsafe SQL keyword: {word}")

        if not (
            sql_clean.startswith("select")
            or sql_clean.startswith("with")
        ):
            raise Exception("Only SELECT queries are allowed.")

        return True

    def add_limit_if_missing(self, sql):
        sql_clean = sql.strip().rstrip(";")

        if re.search(r"\blimit\b", sql_clean, re.IGNORECASE):
            return sql_clean

        return sql_clean + f" LIMIT {MAX_ROWS}"


# ============================================================
# SQL EXECUTOR
# ============================================================

class SQLExecutor:
    def __init__(self):
        self.db = DatabaseConnection()

    def execute(self, sql):
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SET statement_timeout = 10000;")
            cursor.execute(sql)

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            cursor.close()
            conn.close()

            return columns, rows

        except Exception as error:
            cursor.close()
            conn.close()
            raise error


# ============================================================
# ANSWER FORMATTER
# ============================================================

class AnswerFormatter:
    def generate_answer(self, question, columns, rows):
        if not rows:
            return "No matching records were found."

        row_count = len(rows)

        if row_count == 1 and len(columns) == 1:
            value = rows[0][0]
            return f"The result is {value}."

        if row_count == 1:
            return "Found 1 matching record. The details are shown below."

        return f"Found {row_count} matching records. The details are shown below."


# ============================================================
# DATABASE ASSISTANT
# ============================================================

class DatabaseAssistant:
    def __init__(self):
        self.schema_reader = SchemaReader()
        self.sql_generator = SQLGenerator()
        self.sql_validator = SQLValidator()
        self.sql_executor = SQLExecutor()
        self.answer_formatter = AnswerFormatter()
        self.cached_schema = None
        self.cached_schema_text = None

    def get_schema(self):
        if self.cached_schema is None:
            self.cached_schema = self.schema_reader.read_schema()
            self.cached_schema_text = self.schema_reader.schema_as_text(
                self.cached_schema
            )

        return self.cached_schema

    def get_schema_text(self):
        if self.cached_schema_text is None:
            self.get_schema()

        return self.cached_schema_text

    def refresh_schema(self):
        self.cached_schema = self.schema_reader.read_schema()
        self.cached_schema_text = self.schema_reader.schema_as_text(
            self.cached_schema
        )

        return self.cached_schema

    def answer_question(self, question: str):
        start_time = time.time()

        try:
            schema_text = self.get_schema_text()

            sql = self.sql_generator.generate_sql(
                question,
                schema_text
            )

            self.sql_validator.validate(sql)

            safe_sql = self.sql_validator.add_limit_if_missing(sql)

            columns, rows = self.sql_executor.execute(safe_sql)

            formatted_rows = [
                [str(value) if value is not None else "" for value in row]
                for row in rows
            ]

            answer = self.answer_formatter.generate_answer(
                question,
                columns,
                rows
            )

            return {
                "answer": answer,
                "columns": columns,
                "rows": formatted_rows,
                "row_count": len(rows),
                "execution_time": round(time.time() - start_time, 3),
                # kept for backend debugging only; frontend will not display it
                "sql": safe_sql
            }

        except Exception as error:
            return {
                "answer": "I could not answer this database question. Please try asking it more clearly.",
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_time": round(time.time() - start_time, 3),
                "error": str(error)
            }


# Single object imported by kb_server.py
database_assistant = DatabaseAssistant()
