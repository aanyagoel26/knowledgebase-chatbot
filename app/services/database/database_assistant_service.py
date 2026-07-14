import json
import re
import time

import requests

from app.config.settings import (
    CHAT_MODEL,
    MAX_ROWS,
    OLLAMA_CHAT_URL,
    QUERY_TIMEOUT_MS,
    SENSITIVE_COLUMN_KEYWORDS
)
from app.database.connection import get_db_connection
from app.services.database.conversation_memory import conversation_memory

# ============================================================
# SCHEMA READER
# ============================================================

class SchemaReader:

    def read_schema(self):
        conn = get_db_connection()
        cursor = conn.cursor()

        tables = self._read_tables(cursor)
        schema = []

        for table_name in tables:
            columns = self._read_columns(cursor, table_name)
            primary_keys = self._read_primary_keys(cursor, table_name)
            foreign_keys = self._read_foreign_keys(cursor, table_name)
            sample_rows = self._read_sample_rows(cursor, table_name, columns)

            schema.append(
                {
                    "table_name": table_name,
                    "columns": columns,
                    "primary_keys": primary_keys,
                    "foreign_keys": foreign_keys,
                    "sample_rows": sample_rows
                }
            )

        cursor.close()
        conn.close()

        return schema

    def _read_tables(self, cursor):
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
              AND table_type='BASE TABLE'
            ORDER BY table_name;
            """
        )

        return [row[0] for row in cursor.fetchall()]

    def _read_columns(self, cursor, table_name):
        cursor.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name=%s
            ORDER BY ordinal_position;
            """,
            (table_name,)
        )

        rows = cursor.fetchall()
        safe_columns = []

        for row in rows:
            column_name = row[0]

            if self.is_sensitive_column(column_name):
                continue

            safe_columns.append(
                {
                    "column_name": column_name,
                    "data_type": row[1],
                    "is_nullable": row[2],
                    "column_default": row[3]
                }
            )

        return safe_columns

    def _read_primary_keys(self, cursor, table_name):
        cursor.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name = %s;
            """,
            (table_name,)
        )

        return [row[0] for row in cursor.fetchall()]

    def _read_foreign_keys(self, cursor, table_name):
        cursor.execute(
            """
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
              AND tc.table_name = %s;
            """,
            (table_name,)
        )

        return [
            {
                "column_name": row[0],
                "foreign_table_name": row[1],
                "foreign_column_name": row[2]
            }
            for row in cursor.fetchall()
        ]

    def _read_sample_rows(self, cursor, table_name, columns):
        try:
            column_names = [column["column_name"] for column in columns]

            if not column_names:
                return []

            safe_table = self._quote_identifier(table_name)
            safe_columns = ", ".join(
                [self._quote_identifier(column) for column in column_names]
            )

            cursor.execute(
                f"SELECT {safe_columns} FROM {safe_table} LIMIT 3;"
            )

            rows = cursor.fetchall()
            sample_rows = []

            for row in rows:
                sample = {}

                for index, value in enumerate(row):
                    sample[column_names[index]] = (
                        str(value) if value is not None else None
                    )

                sample_rows.append(sample)

            return sample_rows

        except Exception:
            return []

    def _quote_identifier(self, identifier):
        safe_identifier = identifier.replace('"', '""')
        return f'"{safe_identifier}"'

    def schema_as_text(self, schema):
        lines = []

        for table in schema:
            table_name = table["table_name"]
            column_parts = []

            for column in table["columns"]:
                column_text = (
                    f"{column['column_name']} {column['data_type']}"
                )

                if column["column_name"] in table["primary_keys"]:
                    column_text += " PRIMARY KEY"

                column_parts.append(column_text)

            lines.append(
                f"TABLE {table_name}: " + ", ".join(column_parts)
            )

            for fk in table["foreign_keys"]:
                if self.is_sensitive_column(fk["column_name"]):
                    continue

                lines.append(
                    f"RELATION {table_name}.{fk['column_name']} -> "
                    f"{fk['foreign_table_name']}.{fk['foreign_column_name']}"
                )

            if table["sample_rows"]:
                lines.append(
                    f"SAMPLE {table_name}: "
                    + json.dumps(table["sample_rows"], default=str)
                )

            lines.append("")

        return "\n".join(lines)

    def is_sensitive_column(self, column_name):
        column_name = column_name.lower()

        for keyword in SENSITIVE_COLUMN_KEYWORDS:
            if keyword in column_name:
                return True

        return False


# ============================================================
# SIMPLE SQL ROUTER
# ============================================================

class SimpleSQLRouter:
    """
    Deterministic SQL generator for common employee-table questions.
    This prevents the LLM from adding hidden filters such as is_active = TRUE
    when the user did not explicitly ask for active employees.
    """

    DEPARTMENT_ALIASES = {
        "aiml": "AIML",
        "ai ml": "AIML",
        "ai/ml": "AIML",
        "ai-ml": "AIML",
        "artificial intelligence": "AIML",
        "machine learning": "AIML",
        "hr": "HR",
        "human resource": "HR",
        "human resources": "HR",
        "it": "IT",
        "information technology": "IT",
        "finance": "Finance",
        "fin": "Finance"
    }

    def generate_sql(self, question):
        q = self._normalize(question)

        if not self._is_employee_question(q):
            return None

        selected_columns = self._selected_columns(q)
        where_conditions = []

        department = self._extract_department(q)
        if department:
            where_conditions.append(
                f"department ILIKE '{self._escape_literal(department)}'"
            )

        role = self._extract_role(q)
        if role:
            where_conditions.append(
                f"role ILIKE '{self._escape_literal(role)}'"
            )

        status_condition = self._extract_status_condition(q)
        if status_condition:
            where_conditions.append(status_condition)

        where_sql = ""
        if where_conditions:
            where_sql = " WHERE " + " AND ".join(where_conditions)

        if self._wants_count(q):
            return f"SELECT COUNT(*) AS count FROM employees{where_sql}"

        order_sql = ""
        if "name" in selected_columns:
            order_sql = " ORDER BY name ASC"

        return f"SELECT {', '.join(selected_columns)} FROM employees{where_sql}{order_sql}"

    def _normalize(self, question):
        return re.sub(r"\s+", " ", question.lower().strip())

    def _is_employee_question(self, q):
        employee_words = [
            "employee", "employees", "staff", "worker", "workers",
            "people", "users", "person", "persons"
        ]

        if any(word in q for word in employee_words):
            return True

        if self._extract_department(q):
            return True

        if self._extract_role(q):
            return True

        if self._wants_name_only(q):
            return True

        return False

    def _selected_columns(self, q):
        if self._wants_count(q):
            return ["COUNT(*) AS count"]

        if self._wants_name_only(q):
            return ["name"]

        if self._wants_email_only(q):
            return ["email"]

        return ["name", "email", "role", "department", "is_active"]

    def _wants_count(self, q):
        return (
            "how many" in q
            or "count" in q
            or "number of" in q
            or "total" in q
        )

    def _wants_name_only(self, q):
        has_name = "name" in q or "names" in q
        only_words = [
            "only", "just", "no other detail", "do not show any other",
            "not detail", "not details", "without detail", "without details"
        ]
        return has_name and any(word in q for word in only_words)

    def _wants_email_only(self, q):
        has_email = "email" in q or "emails" in q or "mail" in q
        only_words = ["only", "just", "no other detail", "without details"]
        return has_email and any(word in q for word in only_words)

    def _extract_department(self, q):
        for alias, department in self.DEPARTMENT_ALIASES.items():
            if re.search(r"\b" + re.escape(alias) + r"\b", q):
                return department
        return None

    def _extract_role(self, q):
        if re.search(r"\b(admin|administrator)\b", q):
            return "admin"

        if re.search(r"\b(manager|managers)\b", q):
            return "manager"

        # Do not treat the word employee as a role automatically because
        # users often say "show employees" to mean the table, not role='employee'.
        if "role employee" in q or "employee role" in q:
            return "employee"

        return None

    def _extract_status_condition(self, q):
        # Never add an active-status filter unless the user explicitly asks.
        explicit_all_status = [
            "irrespective of status", "irrespective of their status",
            "whether active or not", "active or not", "all status",
            "all statuses", "any status"
        ]
        if any(text in q for text in explicit_all_status):
            return None

        if re.search(r"\b(inactive|not active|disabled|deactivated)\b", q):
            return "is_active = FALSE"

        if re.search(r"\b(active|enabled)\b", q):
            return "is_active = TRUE"

        return None

    def _escape_literal(self, value):
        return value.replace("'", "''")

# ============================================================
# FOLLOW-UP SQL BUILDER
# ============================================================

class FollowUpSQLBuilder:
    """Applies short follow-up instructions to the previous safe SELECT query."""

    FOLLOW_UP_HINTS = (
        "only", "just", "now", "then", "also", "instead", "sort",
        "order", "active", "inactive", "names", "emails", "count"
    )

    def generate_sql(self, question, context):
        previous_sql = (context or {}).get("previous_sql")

        if not previous_sql:
            return None

        q = re.sub(r"\s+", " ", question.lower().strip())

        if not self._looks_like_follow_up(q):
            return None

        sql = previous_sql.strip().rstrip(";")
        sql = re.sub(r"\s+LIMIT\s+\d+\s*$", "", sql, flags=re.IGNORECASE)

        if not re.match(r"^SELECT\s+", sql, flags=re.IGNORECASE):
            return None

        sql = self._change_projection(sql, q)
        sql = self._change_status_filter(sql, q)
        sql = self._change_sort(sql, q)

        return sql

    def _looks_like_follow_up(self, q):
        if len(q.split()) <= 6 and any(hint in q for hint in self.FOLLOW_UP_HINTS):
            return True

        phrases = (
            "show only", "give only", "what about", "from them",
            "among them", "those employees", "these employees"
        )
        return any(phrase in q for phrase in phrases)

    def _change_projection(self, sql, q):
        projection = None

        if self._asks_count(q):
            projection = "COUNT(*) AS count"
        elif re.search(r"\b(names?|only names?|just names?)\b", q):
            projection = "name"
        elif re.search(r"\b(emails?|mails?|only emails?|just emails?)\b", q):
            projection = "email"
        elif "name and email" in q or "names and emails" in q:
            projection = "name, email"
        elif "all details" in q or "full details" in q:
            projection = "name, email, role, department, is_active"

        if not projection:
            return sql

        return re.sub(
            r"^SELECT\s+.+?\s+FROM\s+",
            f"SELECT {projection} FROM ",
            sql,
            count=1,
            flags=re.IGNORECASE | re.DOTALL
        )

    def _change_status_filter(self, sql, q):
        wants_inactive = bool(re.search(r"\b(inactive|not active|disabled|deactivated)\b", q))
        wants_active = bool(re.search(r"\b(active|enabled)\b", q)) and not wants_inactive
        wants_all = any(
            phrase in q
            for phrase in (
                "all statuses", "any status", "active or inactive",
                "active and inactive", "irrespective of status"
            )
        )

        if not (wants_active or wants_inactive or wants_all):
            return sql

        sql = re.sub(
            r"\s+AND\s+is_active\s*=\s*(TRUE|FALSE)",
            "",
            sql,
            flags=re.IGNORECASE
        )
        sql = re.sub(
            r"\s+WHERE\s+is_active\s*=\s*(TRUE|FALSE)\s*(?=ORDER\s+BY|$)",
            " ",
            sql,
            flags=re.IGNORECASE
        )

        if wants_all:
            return re.sub(r"\s+", " ", sql).strip()

        condition = "is_active = TRUE" if wants_active else "is_active = FALSE"
        order_match = re.search(r"\s+ORDER\s+BY\s+.+$", sql, flags=re.IGNORECASE)
        order_sql = order_match.group(0) if order_match else ""
        base_sql = sql[:order_match.start()] if order_match else sql

        connector = " AND " if re.search(r"\bWHERE\b", base_sql, flags=re.IGNORECASE) else " WHERE "
        return f"{base_sql.rstrip()}{connector}{condition}{order_sql}"

    def _change_sort(self, sql, q):
        if not any(word in q for word in ("sort", "order", "alphabetical", "alphabetically")):
            return sql

        descending = any(word in q for word in ("descending", "desc", "reverse", "z to a"))
        direction = "DESC" if descending else "ASC"

        sql = re.sub(r"\s+ORDER\s+BY\s+.+$", "", sql, flags=re.IGNORECASE)
        return f"{sql.rstrip()} ORDER BY name {direction}"

    def _asks_count(self, q):
        return any(phrase in q for phrase in ("how many", "count", "number of", "total"))


# ============================================================
# SQL GENERATOR
# ============================================================

class SQLGenerator:

    def generate_sql(self, question, schema_text):
        system_prompt = """
You are an expert PostgreSQL SQL generator for an enterprise database assistant.

Rules:
- Generate exactly one PostgreSQL SELECT query.
- Only generate SELECT or WITH queries.
- Never generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, COPY, EXECUTE.
- Use only tables and columns present in the provided schema.
- Prefer explicit column names instead of SELECT *.
- Never select password, token, hash, secret, credential, otp, api key, or authentication-related columns.
- If user asks for password, credentials, token, or login secret, do not generate SQL for that sensitive data.
- If user asks for employees, return employee records from the employees table.
- Department filters such as AIML, HR, IT, and Finance must filter the department column only.
- For text matching on department, role, name, or email, use ILIKE.
- Never filter by is_active unless the user explicitly asks for active or inactive records.
- If the user says all employees, return all matching employees regardless of active status.
- Do not exclude admin users unless the user explicitly asks to exclude admin users.
- If user asks only for names, return only the name column.
- If user asks for all records, still add LIMIT 100.
- For counts, use COUNT(*).
- For department-wise or category-wise questions, use GROUP BY.
- For latest/recent questions, use ORDER BY created_at DESC if such a column exists.
- Do not use markdown.
- Do not explain the query.
- Return only SQL.
"""

        user_prompt = f"""
Database schema:
{schema_text}

User question:
{question}

Return only the PostgreSQL SQL query.
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
            "execute",
            "call",
            "do"
        ]

        for keyword in SENSITIVE_COLUMN_KEYWORDS:
            pattern = (
                r"\b[a-zA-Z0-9_]*"
                + re.escape(keyword)
                + r"[a-zA-Z0-9_]*\b"
            )

            if re.search(pattern, sql_clean):
                raise Exception("Query contains sensitive column reference.")

        for word in blocked_words:
            if re.search(r"\b" + word + r"\b", sql_clean):
                raise Exception(f"Unsafe SQL keyword blocked: {word}")

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

    def execute(self, sql):
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                f"SET statement_timeout = {QUERY_TIMEOUT_MS};"
            )

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
            return f"The result is {rows[0][0]}."

        if row_count == 1:
            return "Found 1 matching record. The details are shown below."

        return f"Found {row_count} matching records. The details are shown below."


# ============================================================
# DATABASE ASSISTANT
# ============================================================

class DatabaseAssistant:

    SCHEMA_CACHE_SECONDS = 300

    def __init__(self):
        self.schema_reader = SchemaReader()
        self.simple_sql_router = SimpleSQLRouter()
        self.follow_up_sql_builder = FollowUpSQLBuilder()
        self.sql_generator = SQLGenerator()
        self.sql_validator = SQLValidator()
        self.sql_executor = SQLExecutor()
        self.answer_formatter = AnswerFormatter()

        self.cached_schema = None
        self.cached_schema_text = None
        self.cached_at = None

    def get_schema(self):
        if self.should_refresh_schema():
            self.refresh_schema()

        return self.cached_schema

    def get_schema_text(self):
        if self.should_refresh_schema():
            self.refresh_schema()

        return self.cached_schema_text

    def should_refresh_schema(self):
        if self.cached_schema is None or self.cached_schema_text is None:
            return True

        if self.cached_at is None:
            return True

        return (time.time() - self.cached_at) > self.SCHEMA_CACHE_SECONDS

    def refresh_schema(self):
        self.cached_schema = self.schema_reader.read_schema()
        self.cached_schema_text = self.schema_reader.schema_as_text(
            self.cached_schema
        )
        self.cached_at = time.time()

        return self.cached_schema

    def get_schema_summary(self):
        schema = self.get_schema()

        return {
            "table_count": len(schema),
            "tables": [
                {
                    "table_name": table["table_name"],
                    "column_count": len(table["columns"]),
                    "primary_keys": table["primary_keys"],
                    "foreign_keys": table["foreign_keys"]
                }
                for table in schema
            ],
            "cached_at": self.cached_at
        }

    def answer_question(self, question: str, session_id=None):
        start_time = time.time()

        if self.is_sensitive_question(question):
            return {
                "answer": (
                    "For security reasons, passwords, password hashes, tokens, "
                    "and credentials cannot be viewed through the assistant. "
                    "If someone forgets their password, they should use the password reset process."
                ),
                "sql": None,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_time": round(time.time() - start_time, 3)
            }

        try:
            context = conversation_memory.get_context(session_id)

            sql = self.follow_up_sql_builder.generate_sql(
                question,
                context
            )

            if sql is None:
                sql = self.simple_sql_router.generate_sql(question)

            if sql is None:
                schema_text = self.get_schema_text()
                contextual_question = self.build_contextual_question(
                    question,
                    context
                )

                sql = self.sql_generator.generate_sql(
                    contextual_question,
                    schema_text
                )

            self.sql_validator.validate(sql)

            safe_sql = self.sql_validator.add_limit_if_missing(sql)

            columns, rows = self.sql_executor.execute(safe_sql)

            formatted_rows = self.format_rows(rows)

            answer = self.answer_formatter.generate_answer(
                question,
                columns,
                rows
            )

            return {
                "answer": answer,
                "sql": safe_sql,
                "columns": columns,
                "rows": formatted_rows,
                "row_count": len(rows),
                "execution_time": round(time.time() - start_time, 3)
            }

        except Exception as error:
            return {
                "answer": (
                    "I could not answer this database question. "
                    "Please try asking it more clearly."
                ),
                "sql": None,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "execution_time": round(time.time() - start_time, 3),
                "error": str(error)
            }

    def build_contextual_question(self, question, context):
        previous_question = (context or {}).get("previous_question")
        previous_sql = (context or {}).get("previous_sql")

        if not previous_sql:
            return question

        return (
            f"Previous user question: {previous_question or 'Not available'}\n"
            f"Previous generated SQL: {previous_sql}\n"
            f"Current user question: {question}\n"
            "Use the previous query only when the current question is a follow-up. "
            "Do not preserve filters that the current question explicitly changes."
        )

    def format_rows(self, rows):
        formatted_rows = []

        for row in rows:
            formatted_row = []

            for value in row:
                if value is None:
                    formatted_row.append("")
                else:
                    formatted_row.append(str(value))

            formatted_rows.append(formatted_row)

        return formatted_rows

    def is_sensitive_question(self, question):
        question = question.lower()

        sensitive_words = [
            "password",
            "pass",
            "pwd",
            "hash",
            "token",
            "secret",
            "credential",
            "otp",
            "pin",
            "api key",
            "apikey",
            "login secret"
        ]

        for word in sensitive_words:
            if word in question:
                return True

        return False


# ============================================================
# SINGLE IMPORTABLE OBJECT
# ============================================================

database_assistant = DatabaseAssistant()